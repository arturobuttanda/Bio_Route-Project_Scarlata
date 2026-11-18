"""Compilador de datos para la Single Page Application (SPA) de Benito Juárez.

Empaqueta topología, POIs reales (hospitales, escuelas, plazas, transporte),
líneas reales (Metro, Metrobús, RTP, Trolebús, Concesionado), accidentes viales,
soluciones del Frente de Pareto y escenarios de contingencia C5 en JSON.
"""

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Polygon

from config.settings import settings
from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.graph.cleaner import load_road_network
from src.ingestion.accidents import enrich_graph_with_accident_risk
from src.ingestion.boundary import get_benito_juarez_polygon
from src.simulation.scenarios import get_all_scenarios


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    """Lee un JSON compacto si existe; retorna diccionario vacío en caso contrario."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _linestring_to_latlngs(geom: object) -> list[list[list[float]]]:
    """Convierte LineString o MultiLineString (EPSG:4326) en listas de [lat, lon]."""
    if isinstance(geom, LineString):
        return [[[round(float(y), 5), round(float(x), 5)] for x, y in geom.coords]]
    if isinstance(geom, MultiLineString):
        return [
            [[round(float(y), 5), round(float(x), 5)] for x, y in part.coords]
            for part in geom.geoms
        ]
    return []


def compile_spa_data(output_json_path: Path | None = None) -> dict[str, Any]:
    """Compila todo el modelo espacial, transporte, siniestralidad y optimización."""
    if output_json_path is None:
        output_json_path = settings.outputs_dir / "spa_payload.json"

    # 1. Cargar grafo LSCC y enriquecer con riesgo de accidentes si aplica
    G = load_road_network(ensure_weights=False)
    G, edges_with_accidents = enrich_graph_with_accident_risk(G)

    node_coords: dict[int, tuple[float, float]] = {
        n: (float(d.get("y", 0.0)), float(d.get("x", 0.0))) for n, d in G.nodes(data=True)
    }

    # 1B. Red vial LSCC jerarquizada para renderizado vectorial minimalista (primary / secondary / local)
    road_network_layers: dict[str, list[list[tuple[float, float]]]] = {
        "primary": [],
        "secondary": [],
        "local": [],
    }
    seen_undirected: set[tuple[int, int]] = set()
    for u, v, d in G.edges(data=True):
        if u not in node_coords or v not in node_coords:
            continue
        pair = (min(u, v), max(u, v))
        if pair in seen_undirected:
            continue
        seen_undirected.add(pair)
        hw = str(d.get("highway", "residential")).lower()
        p1 = (round(node_coords[u][0], 5), round(node_coords[u][1], 5))
        p2 = (round(node_coords[v][0], 5), round(node_coords[v][1], 5))
        if any(k in hw for k in ("motorway", "trunk", "primary")):
            road_network_layers["primary"].append([p1, p2])
        elif any(k in hw for k in ("secondary", "tertiary")):
            road_network_layers["secondary"].append([p1, p2])
        else:
            road_network_layers["local"].append([p1, p2])

    # 2. Polígono oficial y Máscara Inversa (Donut Mask)
    boundary_gdf = get_benito_juarez_polygon(buffer_meters=0.0, use_cache=True).to_crs("EPSG:4326")
    official_row = boundary_gdf[boundary_gdf["type"] == "official_boundary"]
    poly_geom: Polygon = official_row.geometry.iloc[0]

    ext_coords = [(float(y), float(x)) for x, y in poly_geom.exterior.coords]
    mask_geojson = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-180.0, -90.0], [180.0, -90.0], [180.0, 90.0], [-180.0, 90.0], [-180.0, -90.0]],
                [(float(x), float(y)) for x, y in poly_geom.exterior.coords],
            ],
        },
    }

    # 3. POIs reales anclados (Metro, Metrobús, Hospitales, Escuelas, Malls, Colonias)
    pois = load_pois_with_metric_coords(use_real=True)
    pois = snap_pois_to_network(pois, G)
    pois_data = [
        {
            "id": p.id,
            "name": p.name,
            "kind": p.kind.value,
            "lat": p.lat,
            "lon": p.lon,
            "weight": p.weight,
            "node": p.nearest_node,
        }
        for p in pois
    ]

    # 4. Redes reales de Transporte Público (Metro, Metrobús, RTP, Trolebús, Concesionado)
    transit_lines_data: dict[str, list[dict[str, Any]]] = {
        "metro": [],
        "metrobus": [],
        "rtp": [],
        "trolebus": [],
        "concessionaire": [],
    }
    transit_lines_path = settings.processed_data_dir / "transit_lines.geoparquet"
    if transit_lines_path.exists():
        gdf_tl = gpd.read_parquet(transit_lines_path).to_crs("EPSG:4326")
        for _, row in gdf_tl.iterrows():
            mode = str(row.get("mode", "concessionaire"))
            if mode not in transit_lines_data:
                transit_lines_data[mode] = []
            parts = _linestring_to_latlngs(row.geometry)
            for pts in parts:
                if len(pts) >= 2:
                    transit_lines_data[mode].append(
                        {
                            "name": str(row.get("route_name", "Ruta")),
                            "source": str(row.get("source", "")),
                            "coords": pts,
                        }
                    )

    transit_stops_data: list[dict[str, Any]] = []
    transit_stops_path = settings.processed_data_dir / "transit_stops.geoparquet"
    if transit_stops_path.exists():
        gdf_ts = gpd.read_parquet(transit_stops_path).to_crs("EPSG:4326")
        for _, row in gdf_ts.iterrows():
            if row.geometry is None or row.geometry.is_empty:
                continue
            transit_stops_data.append(
                {
                    "name": str(row.get("stop_name", "Parada")),
                    "mode": str(row.get("mode", "concessionaire")),
                    "route": str(row.get("route_name", "")),
                    "lat": round(float(row.geometry.y), 6),
                    "lon": round(float(row.geometry.x), 6),
                }
            )

    # 5. Accidentes Viales (Heatmap + Aristas de Alto Riesgo)
    accidents_heat: list[list[float]] = []
    acc_path = settings.processed_data_dir / "accidents_bj.geoparquet"
    if acc_path.exists():
        gdf_acc = gpd.read_parquet(acc_path)
        for _, row in gdf_acc.iterrows():
            accidents_heat.append(
                [
                    round(float(row["latitud"]), 5),
                    round(float(row["longitud"]), 5),
                    round(float(row.get("severity_weight", 1.0)), 2),
                ]
            )

    high_risk_edges: list[dict[str, Any]] = []
    risk_candidates = []
    for u, v, d in G.edges(data=True):
        cnt = int(d.get("accident_count", 0))
        if cnt > 0 and u in node_coords and v in node_coords:
            risk_candidates.append(
                (
                    float(d.get("risk_score", 0.0)),
                    cnt,
                    str(d.get("name", "Vialidad")),
                    [node_coords[u], node_coords[v]],
                )
            )
    risk_candidates.sort(key=lambda x: x[0], reverse=True)
    for rscore, cnt, ename, coords in risk_candidates[:200]:
        high_risk_edges.append(
            {
                "name": ename,
                "accident_count": cnt,
                "risk_score": rscore,
                "coords": coords,
            }
        )

    # 6. Rutas del Baseline A* (Top 25)
    base_file = settings.processed_data_dir / "baseline_od_routes.parquet"
    baseline_routes = []
    if base_file.exists():
        df_base = pd.read_parquet(base_file)
        for _, row in df_base.head(25).iterrows():
            coords = [node_coords[nid] for nid in row["path_nodes"] if nid in node_coords]
            baseline_routes.append(
                {
                    "origin_id": row["origin_id"],
                    "destination_id": row["destination_id"],
                    "length_m": round(float(row["length_m"]), 1),
                    "travel_time_s": round(float(row["travel_time_s"]), 1),
                    "coords": coords,
                }
            )

    # 7. Soluciones del Frente de Pareto (NSGA-II)
    pareto_file = settings.outputs_dir / "pareto_routes.parquet"
    pareto_solutions = {}
    if pareto_file.exists():
        df_par = pd.read_parquet(pareto_file)
        sol_indices = sorted(df_par["solution_index"].unique().tolist())

        for s_idx in sol_indices:
            sub_df = df_par[df_par["solution_index"] == s_idx]
            routes = []
            for _, r in sub_df.iterrows():
                coords = [node_coords[nid] for nid in r["path_nodes"] if nid in node_coords]
                routes.append(
                    {
                        "route_id": r["route_id"],
                        "origin_id": r["origin_id"],
                        "destination_id": r["destination_id"],
                        "length_m": round(float(r["length_m"]), 1),
                        "travel_time_s": round(float(r["travel_time_s"]), 1),
                        "coords": coords,
                    }
                )

            avg_time = sum(r["travel_time_s"] for r in routes) / len(routes) if routes else 0.0
            tot_len = sum(r["length_m"] for r in routes) / 1000.0 if routes else 0.0

            pareto_solutions[int(s_idx)] = {
                "solution_index": int(s_idx),
                "solution_id": f"sol_{s_idx}",
                "avg_travel_time_s": round(avg_time, 1),
                "total_length_km": round(tot_len, 1),
                "route_count": len(routes),
                "routes": routes,
            }

    # 8. Escenarios de contingencia C5
    scenarios_list = get_all_scenarios(G, pois)
    contingencies_data = []
    for sc in scenarios_list:
        aff_lines = []
        for u, v in sc.affected_edges:
            if u in node_coords and v in node_coords:
                aff_lines.append([node_coords[u], node_coords[v]])

        contingencies_data.append(
            {
                "scenario_id": sc.scenario_id,
                "name": sc.name,
                "description": sc.description,
                "type": sc.disruption_type.value,
                "friction_multiplier": sc.friction_multiplier,
                "affected_edge_coords": aff_lines[:80],
            }
        )

    # 9. Métricas dinámicas reales desde los resúmenes JSON (sin valores hardcodeados)
    net_sum = _read_json_if_exists(settings.processed_data_dir / "network_summary.json")
    base_sum = _read_json_if_exists(settings.outputs_dir / "baseline_metrics.json")
    opt_sum = _read_json_if_exists(settings.outputs_dir / "optimization_summary.json")
    res_sum = _read_json_if_exists(settings.outputs_dir / "resilience_metrics.json")
    acc_sum = _read_json_if_exists(settings.processed_data_dir / "accidents_summary.json")
    trn_sum = _read_json_if_exists(settings.processed_data_dir / "transit_summary.json")
    poi_sum = _read_json_if_exists(settings.processed_data_dir / "pois_summary.json")
    qa_sum = _read_json_if_exists(settings.processed_data_dir / "qa_report.json")

    kpis = {
        "network": {
            "nodes": net_sum.get("node_count", G.number_of_nodes()),
            "edges": net_sum.get("edge_count", G.number_of_edges()),
            "length_km": net_sum.get("total_length_km", 0.0),
            "contraflow": net_sum.get("metadata", {}).get("contraflow_edges", 0),
        },
        "baseline": {
            "pairs": base_sum.get("total_od_pairs", 0),
            "mean_time_s": round(float(base_sum.get("mean_travel_time_s", 0.0)), 1),
            "mean_dist_m": round(float(base_sum.get("mean_distance_m", 0.0)), 1),
            "pax_hrs": round(float(base_sum.get("total_passenger_hours", 0.0)), 1),
        },
        "optimization": {
            "pareto_count": opt_sum.get("pareto_solutions_count", len(pareto_solutions)),
            "best_time_s": round(float(opt_sum.get("best_time_solution_s", 0.0)), 1),
            "time_gain_pct": round(float(opt_sum.get("time_delta_percent", 0.0)), 1),
            "hypervolume": round(float(opt_sum.get("hypervolume", 0.0)), 4),
        },
        "resilience": {
            "scenarios": res_sum.get("scenarios_evaluated", len(contingencies_data)),
            "reroute_latency_ms": round(float(res_sum.get("mean_rerouting_duration_ms", 0.0)), 2),
            "robustness_pareto": round(float(res_sum.get("pareto_global_robustness", 0.0)), 4),
            "resilience_gain_pct": round(float(res_sum.get("resilience_gain_percent", 0.0)), 1),
        },
        "accidents": {
            "total": acc_sum.get("total_accidents", len(accidents_heat)),
            "injured": acc_sum.get("total_injured", 0),
            "fatalities": acc_sum.get("total_fatalities", 0),
            "date_min": acc_sum.get("date_min", ""),
            "date_max": acc_sum.get("date_max", ""),
            "edges_with_accidents": edges_with_accidents,
            "top_hotspots": acc_sum.get("top_hotspots", []),
        },
        "transit": trn_sum,
        "pois": poi_sum,
        "qa": qa_sum,
    }

    payload = {
        "boundary_latlngs": ext_coords,
        "mask_geojson": mask_geojson,
        "road_network": road_network_layers,
        "pois": pois_data,
        "transit_lines": transit_lines_data,
        "transit_stops": transit_stops_data,
        "accidents_heat": accidents_heat,
        "high_risk_edges": high_risk_edges,
        "baseline_routes": baseline_routes,
        "pareto_solutions": pareto_solutions,
        "contingencies": contingencies_data,
        "kpis": kpis,
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    print(f"==> Payload SPA compilado en: {output_json_path}")
    return payload


if __name__ == "__main__":
    compile_spa_data()
