"""Evaluador de funciones de aptitud multiobjetivo para redes de transporte.

Calcula el vector de objetivos F(I) = (f1: Tiempo de viaje, f2: Traslape de aristas, f3: Cobertura).
"""

import networkx as nx

from src.demand.schemas import PointOfInterest
from src.optimization.schemas import ObjectiveValues, RouteChromosome


def calculate_route_metrics(G: nx.MultiDiGraph, path: list[int]) -> tuple[float, float]:
    """Calcula la longitud total (m) y el tiempo total de recorrido (s) de un camino continuo."""
    total_len = 0.0
    total_time = 0.0

    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        if G.has_edge(u, v):
            edge_data = G[u][v]
            best_edge = min(edge_data.values(), key=lambda d: d.get("travel_time_s", 9999.0))
            total_len += best_edge.get("length_m", 0.0)
            total_time += best_edge.get("travel_time_s", 0.0)
        else:
            total_time += 30.0  # Penalización conservadora por desconexión

    return round(total_len, 2), round(total_time, 2)


def evaluate_individual_fitness(
    G: nx.MultiDiGraph,
    routes: list[RouteChromosome],
    pois: list[PointOfInterest],
    od_volumes: dict[tuple[str, str], float],
    walkable_radius_m: float = 400.0,
) -> ObjectiveValues:
    """Evalúa los tres objetivos en competencia para un plan de rutas dado.

    Args:
        G: Grafo vial dirigido.
        routes: Lista de cromosomas de ruta del individuo.
        pois: Lista de POIs estratégicos con coordenadas métricas.
        od_volumes: Diccionario (origin_id, dest_id) -> volumen horario.
        walkable_radius_m: Radio caminable en metros para considerar cubierto un POI.

    Returns:
        Instancia de ObjectiveValues con f1, f2 y f3 calculados.
    """
    # 1. f1: Tiempo total ponderado por demanda + penalización por riesgo vial en aristas
    total_weighted_time = 0.0
    for r in routes:
        vol = od_volumes.get((r.origin_id, r.destination_id), 1.0)
        path = r.node_sequence
        route_risk = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if G.has_edge(u, v):
                best = min(G[u][v].values(), key=lambda d: d.get("travel_time_s", 9999.0))
                route_risk += float(best.get("risk_score", 0.0))
        effective_time = r.travel_time_s * (1.0 + 0.02 * route_risk)
        total_weighted_time += effective_time * vol

    # 2. f2: Redundancia / Traslape espacial de aristas
    edge_counts: dict[tuple[int, int], int] = {}
    edge_lengths: dict[tuple[int, int], float] = {}

    for r in routes:
        path = r.node_sequence
        for i in range(len(path) - 1):
            e = (path[i], path[i + 1])
            edge_counts[e] = edge_counts.get(e, 0) + 1
            if e not in edge_lengths and G.has_edge(e[0], e[1]):
                best = min(G[e[0]][e[1]].values(), key=lambda d: d.get("length_m", 9999.0))
                edge_lengths[e] = best.get("length_m", 10.0)

    overlap_length = 0.0
    for e, count in edge_counts.items():
        if count > 1:
            overlap_length += (count - 1) * edge_lengths.get(e, 10.0)

    # 3. f3: Cobertura espacial de demanda (POIs cubiertos a <= walkable_radius_m)
    # Recolectar coordenadas métricas de todos los nodos visitados por las rutas
    visited_node_coords: list[tuple[float, float]] = []
    nodes_data = G.nodes

    for r in routes:
        for nid in r.node_sequence:
            if nid in nodes_data:
                nd = nodes_data[nid]
                if "x_m" in nd and "y_m" in nd:
                    visited_node_coords.append((nd["x_m"], nd["y_m"]))

    total_poi_weight = sum(p.weight for p in pois)
    covered_poi_weight = 0.0

    for p in pois:
        px, py = p.x_m, p.y_m
        # Comprobar si algún nodo de la red de rutas está a <= walkable_radius_m
        is_covered = False
        for nx_m, ny_m in visited_node_coords:
            dx = px - nx_m
            dy = py - ny_m
            if (dx * dx + dy * dy) <= (walkable_radius_m * walkable_radius_m):
                is_covered = True
                break
        if is_covered:
            covered_poi_weight += p.weight

    coverage_ratio = covered_poi_weight / total_poi_weight if total_poi_weight > 0 else 0.0

    return ObjectiveValues(
        f1_travel_time_s=round(total_weighted_time, 2),
        f2_overlap_length_m=round(overlap_length, 2),
        f3_coverage_ratio=round(coverage_ratio, 4),
    )
