"""Línea base determinista de ruteo de caminos mínimos (Dijkstra y A*).

Establece el benchmark cuantitativo de tiempo, distancia y horas-pasajero
para comparar la metaheurística bioinspirada de la Fase 3.
"""

import json
import math
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from config.settings import settings
from src.demand.schemas import BaselineMetricsSummary, ODPair, RouteResult

MAX_SPEED_MPS = 80.0 * (1000.0 / 3600.0)  # Cota superior admisible para A*


def make_euclidean_heuristic(G: nx.MultiDiGraph):
    """Crea una heurística euclidiana admisible basada en coordenadas métricas UTM 14N."""
    nodes = G.nodes

    def heuristic(u: int, v: int) -> float:
        node_u = nodes[u]
        node_v = nodes[v]
        dx = node_u.get("x_m", 0.0) - node_v.get("x_m", 0.0)
        dy = node_u.get("y_m", 0.0) - node_v.get("y_m", 0.0)
        dist_m = math.sqrt(dx * dx + dy * dy)
        return dist_m / MAX_SPEED_MPS

    return heuristic


def compute_baseline_routes(
    G: nx.MultiDiGraph,
    od_pairs: list[ODPair],
    algorithm: str = "astar",
    weight_attr: str = "travel_time_s",
) -> tuple[list[RouteResult], BaselineMetricsSummary]:
    """Calcula los caminos mínimos para todos los pares OD y genera métricas agregadas.

    Args:
        G: Grafo fuertemente conexo (LSCC).
        od_pairs: Lista de pares OD.
        algorithm: 'astar' o 'dijkstra'.

    Returns:
        Tupla con lista de RouteResult y el resumen BaselineMetricsSummary.
    """
    heuristic = make_euclidean_heuristic(G) if algorithm == "astar" else None
    results: list[RouteResult] = []
    unreachable = 0

    times_s: list[float] = []
    lengths_m: list[float] = []
    passenger_seconds = 0.0
    total_trips = 0.0

    for pair in od_pairs:
        try:
            u_start = (
                pair.origin_node
                if pair.origin_node in G
                else (
                    int(pair.origin_node) if int(pair.origin_node) in G else str(pair.origin_node)
                )
            )
            v_end = (
                pair.dest_node
                if pair.dest_node in G
                else (int(pair.dest_node) if int(pair.dest_node) in G else str(pair.dest_node))
            )

            if algorithm == "astar":
                path = nx.astar_path(
                    G,
                    u_start,
                    v_end,
                    heuristic=heuristic,
                    weight=weight_attr,
                )
            else:
                path = nx.dijkstra_path(
                    G,
                    u_start,
                    v_end,
                    weight=weight_attr,
                )

            # Sumar longitud y tiempo sobre el camino encontrado
            total_time = 0.0
            total_len = 0.0

            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                # En MultiDiGraph, elegir la arista de menor tiempo si hay paralelas
                edge_dict = G[u][v]
                best_edge = min(edge_dict.values(), key=lambda e: e.get("travel_time_s", 9999.0))
                total_time += best_edge.get("travel_time_s", 0.0)
                total_len += best_edge.get("length_m", 0.0)

            results.append(
                RouteResult(
                    origin_id=pair.origin_id,
                    destination_id=pair.destination_id,
                    path=path,
                    length_m=round(total_len, 2),
                    travel_time_s=round(total_time, 2),
                )
            )

            times_s.append(total_time)
            lengths_m.append(total_len)
            passenger_seconds += total_time * pair.trip_volume
            total_trips += pair.trip_volume

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            unreachable += 1

    # Calcular estadísticas agregadas
    mean_time = float(np.mean(times_s)) if times_s else 0.0
    median_time = float(np.median(times_s)) if times_s else 0.0
    p90_time = float(np.percentile(times_s, 90)) if times_s else 0.0
    mean_dist = float(np.mean(lengths_m)) if lengths_m else 0.0
    passenger_hours = passenger_seconds / 3600.0

    summary = BaselineMetricsSummary(
        algorithm=f"{algorithm.upper()} sobre LSCC vial",
        total_od_pairs=len(od_pairs),
        total_trips_simulated=round(total_trips, 1),
        mean_travel_time_s=round(mean_time, 2),
        median_travel_time_s=round(median_time, 2),
        p90_travel_time_s=round(p90_time, 2),
        mean_distance_m=round(mean_dist, 2),
        total_passenger_hours=round(passenger_hours, 2),
        unreachable_pairs=unreachable,
        metadata={
            "min_travel_time_s": round(float(np.min(times_s)), 2) if times_s else 0.0,
            "max_travel_time_s": round(float(np.max(times_s)), 2) if times_s else 0.0,
        },
    )

    return results, summary


def save_baseline_artifacts(
    routes: list[RouteResult],
    summary: BaselineMetricsSummary,
    output_routes_path: Path | None = None,
    output_summary_path: Path | None = None,
) -> tuple[Path, Path]:
    """Serializa la tabla de rutas en Parquet y el resumen en JSON."""
    if output_routes_path is None:
        output_routes_path = settings.processed_data_dir / "baseline_od_routes.parquet"
    if output_summary_path is None:
        output_summary_path = settings.outputs_dir / "baseline_metrics.json"

    output_routes_path.parent.mkdir(parents=True, exist_ok=True)
    output_summary_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Rutas tabulares en Parquet (excluido de contexto IA por .aiignore)
    df = pd.DataFrame(
        [
            {
                "origin_id": r.origin_id,
                "destination_id": r.destination_id,
                "num_nodes": len(r.path),
                "length_m": r.length_m,
                "travel_time_s": r.travel_time_s,
                "path_nodes": r.path,
            }
            for r in routes
        ]
    )
    df.to_parquet(output_routes_path)

    # 2. Resumen JSON compacto (< 250 tokens para LLMs)
    with open(output_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2)

    return output_routes_path, output_summary_path
