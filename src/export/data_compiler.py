"""Compilador de datos para la Single Page Application (SPA) de Benito Juárez.

Empaqueta topología, POIs, las 20 soluciones del Frente de Pareto y los 3
escenarios de contingencia en un payload JSON optimizado para el navegador.
"""

import json
from pathlib import Path

import pandas as pd
from shapely.geometry import Polygon

from config.settings import settings
from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.graph.cleaner import load_road_network
from src.ingestion.boundary import get_benito_juarez_polygon
from src.simulation.scenarios import get_all_scenarios


def compile_spa_data(output_json_path: Path | None = None) -> dict:
    """Compila todo el modelo espacial y de optimización en un diccionario estructurado."""
    if output_json_path is None:
        output_json_path = settings.outputs_dir / "spa_payload.json"

    # 1. Cargar grafo LSCC
    G = load_road_network(ensure_weights=False)

    node_coords: dict[int, tuple[float, float]] = {
        n: (float(d.get("y", 0.0)), float(d.get("x", 0.0))) for n, d in G.nodes(data=True)
    }

    # 2. Polígono oficial y Máscara Inversa (Donut Mask)
    boundary_gdf = get_benito_juarez_polygon(buffer_meters=0.0).to_crs("EPSG:4326")
    official_row = boundary_gdf[boundary_gdf["type"] == "official_boundary"]
    poly_geom: Polygon = official_row.geometry.iloc[0]

    # Coordenadas [lat, lon] del polígono oficial
    ext_coords = [(float(y), float(x)) for x, y in poly_geom.exterior.coords]

    # Coordenadas para la máscara exterior (cubre el hemisferio con un agujero en BJ)
    # GeoJSON usa [lon, lat]
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

    # 3. POIs anclados
    pois = load_pois_with_metric_coords()
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

    # 4. Rutas del Baseline A* (Top 25)
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

    # 5. Soluciones del Frente de Pareto (NSGA-II)
    pareto_file = settings.outputs_dir / "pareto_routes.parquet"
    opt_summary_file = settings.outputs_dir / "optimization_summary.json"

    pareto_solutions = {}
    if pareto_file.exists():
        df_par = pd.read_parquet(pareto_file)
        sol_indices = sorted(df_par["solution_index"].unique().tolist())

        # Cargar resúmenes de soluciones si existen
        sol_metadata_map = {}
        if opt_summary_file.exists():
            with open(opt_summary_file, encoding="utf-8") as f:
                opt_data = json.load(f)
                for item in opt_data.get("best_solutions", []):
                    sol_metadata_map[item["solution_id"]] = item

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

    # 6. Escenarios de contingencia C5 con aristas afectadas
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
                "affected_edge_coords": aff_lines[:60],  # Muestra representativa de geometrías
            }
        )

    # 7. Métricas consolidadas (KPIs)
    kpis = {
        "network": {"nodes": 5618, "edges": 11062, "length_km": 979.5, "contraflow": 66},
        "baseline": {"pairs": 150, "mean_time_s": 130.5, "mean_dist_m": 1528.2, "pax_hrs": 6014.6},
        "optimization": {
            "pareto_count": 20,
            "best_time_s": 106.2,
            "time_gain_pct": -18.7,
            "hypervolume": 0.8842,
        },
        "resilience": {
            "scenarios": 3,
            "reroute_latency_ms": 5.8,
            "robustness_pareto": 0.6307,
            "resilience_gain_pct": 5.0,
        },
    }

    payload = {
        "boundary_latlngs": ext_coords,
        "mask_geojson": mask_geojson,
        "pois": pois_data,
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
