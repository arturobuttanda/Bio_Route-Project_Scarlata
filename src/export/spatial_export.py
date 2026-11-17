"""Exportador Geoespacial multi-formato para Benito Juárez.

Genera artefactos estándar OGC e interoperables:
1. GeoPackage multi-capa (.gpkg) en EPSG:32614.
2. GeoParquet columnar para DuckDB / Tableau / PowerBI.
3. Web GeoJSON en EPSG:4326 (RFC 7946).
4. Resumen sintético JSON para Blind Data Ingestion.
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from config.settings import settings
from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.export.qgis_styler import generate_pareto_routes_qml, generate_road_network_qml
from src.export.schemas import ExportSummarySchema, LayerSummary
from src.graph.cleaner import load_road_network
from src.ingestion.boundary import get_benito_juarez_polygon
from src.simulation.scenarios import get_all_scenarios


def export_spatial_layers(
    gpkg_path: Path | None = None,
    geoparquet_path: Path | None = None,
    geojson_path: Path | None = None,
    summary_path: Path | None = None,
) -> ExportSummarySchema:
    """Genera todas las capas vectoriales multi-escala y artefactos de analítica espacial."""
    if gpkg_path is None:
        gpkg_path = settings.outputs_dir / "benito_juarez_mobility.gpkg"
    if geoparquet_path is None:
        geoparquet_path = settings.outputs_dir / "analytics_routes.geoparquet"
    if geojson_path is None:
        geojson_path = settings.outputs_dir / "routes_export.geojson"
    if summary_path is None:
        summary_path = settings.outputs_dir / "export_summary.json"

    gpkg_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Cargar Grafo LSCC
    G = load_road_network(ensure_weights=False)

    node_proj: dict[int, tuple[float, float]] = {
        n: (float(d.get("x_proj", 0.0)), float(d.get("y_proj", 0.0))) for n, d in G.nodes(data=True)
    }

    layers_summary: list[LayerSummary] = []
    total_features = 0

    # Si el archivo GPKG ya existe, eliminarlo para reescribir capas limpiamente
    if gpkg_path.exists():
        gpkg_path.unlink()

    # --- Capa 1: boundary_bj (Polígono oficial en EPSG:32614) ---
    boundary_gdf = get_benito_juarez_polygon(buffer_meters=0.0)
    boundary_gdf["name"] = "Benito Juárez"
    boundary_clean = boundary_gdf[["name", "type", "geometry"]].copy()
    boundary_clean.to_file(gpkg_path, layer="boundary_bj", driver="GPKG", engine="pyogrio")
    layers_summary.append(
        LayerSummary(
            name="boundary_bj",
            feature_count=len(boundary_clean),
            geometry_type="Polygon",
            crs="EPSG:32614",
        )
    )
    total_features += len(boundary_clean)

    # --- Capa 2: road_network (Vías de la red LSCC) ---
    edge_rows = []
    for u, v, d in G.edges(data=True):
        if u in node_proj and v in node_proj:
            geom = LineString([node_proj[u], node_proj[v]])
            edge_rows.append(
                {
                    "u": int(u),
                    "v": int(v),
                    "length_m": round(float(d.get("length_m", 0.0)), 2),
                    "speed_kph": round(float(d.get("speed_kph", 30.0)), 1),
                    "free_flow_time_s": round(float(d.get("free_flow_time_s", 0.0)), 2),
                    "highway": str(d.get("highway", "unclassified")),
                    "geometry": geom,
                }
            )
    gdf_roads = gpd.GeoDataFrame(edge_rows, crs="EPSG:32614")
    gdf_roads.to_file(gpkg_path, layer="road_network", driver="GPKG", engine="pyogrio")
    layers_summary.append(
        LayerSummary(
            name="road_network",
            feature_count=len(gdf_roads),
            geometry_type="LineString",
            crs="EPSG:32614",
        )
    )
    total_features += len(gdf_roads)

    # --- Capa 3: transit_stops (POIs snapped) ---
    pois = load_pois_with_metric_coords()
    pois = snap_pois_to_network(pois, G)
    poi_rows = [
        {
            "poi_id": p.id,
            "name": p.name,
            "kind": p.kind.value,
            "weight": p.weight,
            "nearest_node": p.nearest_node,
            "geometry": Point(p.x_m, p.y_m),
        }
        for p in pois
    ]
    gdf_pois = gpd.GeoDataFrame(poi_rows, crs="EPSG:32614")
    gdf_pois.to_file(gpkg_path, layer="transit_stops", driver="GPKG", engine="pyogrio")
    layers_summary.append(
        LayerSummary(
            name="transit_stops",
            feature_count=len(gdf_pois),
            geometry_type="Point",
            crs="EPSG:32614",
        )
    )
    total_features += len(gdf_pois)

    # --- Capa 4: baseline_routes ---
    base_file = settings.processed_data_dir / "baseline_od_routes.parquet"
    gdf_baseline = gpd.GeoDataFrame(
        columns=["origin_id", "destination_id", "length_m", "travel_time_s", "geometry"],
        crs="EPSG:32614",
    )
    if base_file.exists():
        df_base = pd.read_parquet(base_file)
        route_rows = []
        for _, row in df_base.iterrows():
            pts = [node_proj[nid] for nid in row["path_nodes"] if nid in node_proj]
            if len(pts) >= 2:
                route_rows.append(
                    {
                        "origin_id": row["origin_id"],
                        "destination_id": row["destination_id"],
                        "length_m": round(float(row["length_m"]), 2),
                        "travel_time_s": round(float(row["travel_time_s"]), 2),
                        "route_type": "baseline",
                        "solution_index": -1,
                        "geometry": LineString(pts),
                    }
                )
        if route_rows:
            gdf_baseline = gpd.GeoDataFrame(route_rows, crs="EPSG:32614")
            gdf_baseline.to_file(
                gpkg_path, layer="baseline_routes", driver="GPKG", engine="pyogrio"
            )
            layers_summary.append(
                LayerSummary(
                    name="baseline_routes",
                    feature_count=len(gdf_baseline),
                    geometry_type="LineString",
                    crs="EPSG:32614",
                )
            )
            total_features += len(gdf_baseline)

    # --- Capa 5: pareto_optimal_routes ---
    pareto_file = settings.outputs_dir / "pareto_routes.parquet"
    gdf_pareto = gpd.GeoDataFrame(
        columns=[
            "solution_index",
            "origin_id",
            "destination_id",
            "length_m",
            "travel_time_s",
            "geometry",
        ],
        crs="EPSG:32614",
    )
    if pareto_file.exists():
        df_pareto = pd.read_parquet(pareto_file)
        p_rows = []
        for _, row in df_pareto.iterrows():
            pts = [node_proj[nid] for nid in row["path_nodes"] if nid in node_proj]
            if len(pts) >= 2:
                p_rows.append(
                    {
                        "origin_id": row["origin_id"],
                        "destination_id": row["destination_id"],
                        "length_m": round(float(row["length_m"]), 2),
                        "travel_time_s": round(float(row["travel_time_s"]), 2),
                        "route_type": "pareto_nsga2",
                        "solution_index": int(row["solution_index"]),
                        "geometry": LineString(pts),
                    }
                )
        if p_rows:
            gdf_pareto = gpd.GeoDataFrame(p_rows, crs="EPSG:32614")
            gdf_pareto.to_file(
                gpkg_path, layer="pareto_optimal_routes", driver="GPKG", engine="pyogrio"
            )
            layers_summary.append(
                LayerSummary(
                    name="pareto_optimal_routes",
                    feature_count=len(gdf_pareto),
                    geometry_type="LineString",
                    crs="EPSG:32614",
                )
            )
            total_features += len(gdf_pareto)

    # --- Capa 6: contingency_chokepoints ---
    scenarios = get_all_scenarios(G, pois)
    choke_rows = []
    for sc in scenarios:
        for nid in sc.affected_nodes:
            if nid in node_proj:
                choke_rows.append(
                    {
                        "scenario_id": sc.scenario_id,
                        "scenario_name": sc.name,
                        "disruption_type": sc.disruption_type.value,
                        "node_id": nid,
                        "geometry": Point(node_proj[nid]),
                    }
                )
    gdf_choke = gpd.GeoDataFrame(choke_rows, crs="EPSG:32614")
    gdf_choke.to_file(gpkg_path, layer="contingency_chokepoints", driver="GPKG", engine="pyogrio")
    layers_summary.append(
        LayerSummary(
            name="contingency_chokepoints",
            feature_count=len(gdf_choke),
            geometry_type="Point",
            crs="EPSG:32614",
        )
    )
    total_features += len(gdf_choke)

    # --- GeoParquet: Analytics Routes (Baseline + Pareto) ---
    all_routes = []
    if not gdf_baseline.empty:
        all_routes.append(gdf_baseline)
    if not gdf_pareto.empty:
        all_routes.append(gdf_pareto)

    if all_routes:
        gdf_analytics = gpd.GeoDataFrame(pd.concat(all_routes, ignore_index=True), crs="EPSG:32614")
    else:
        gdf_analytics = gpd.GeoDataFrame(
            columns=[
                "origin_id",
                "destination_id",
                "length_m",
                "travel_time_s",
                "route_type",
                "solution_index",
                "geometry",
            ],
            crs="EPSG:32614",
        )

    gdf_analytics.to_parquet(geoparquet_path)

    # --- Web GeoJSON (RFC 7946, EPSG:4326) ---
    gdf_web = gdf_analytics.to_crs("EPSG:4326")
    gdf_web.to_file(geojson_path, driver="GeoJSON")

    # --- QGIS Styles (.qml) ---
    qgis_dir = settings.outputs_dir / "qgis"
    qgis_dir.mkdir(parents=True, exist_ok=True)
    generate_road_network_qml(qgis_dir / "road_network_style.qml")
    generate_pareto_routes_qml(qgis_dir / "pareto_routes_style.qml")

    # --- Resumen sintético JSON ---
    summary = ExportSummarySchema(
        gpkg_path=str(gpkg_path),
        geoparquet_path=str(geoparquet_path),
        geojson_path=str(geojson_path),
        layers=layers_summary,
        total_features=total_features,
    )

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)

    return summary


if __name__ == "__main__":
    print("[+] Ejecutando exportación geoespacial multi-formato...")
    res = export_spatial_layers()
    print(f"==> Exportación completada. Capas generadas en GPKG: {len(res.layers)}")
    for layer_item in res.layers:
        print(
            f"    - {layer_item.name}: {layer_item.feature_count} features ({layer_item.geometry_type}, {layer_item.crs})"
        )
    print(f"==> Total features: {res.total_features}")
    print(f"==> GeoParquet: {res.geoparquet_path}")
    print(f"==> GeoJSON: {res.geojson_path}")
