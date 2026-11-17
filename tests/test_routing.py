"""Pruebas unitarias para modelado de demanda y ruteo determinista (A* y Dijkstra)."""

import json
from pathlib import Path

import networkx as nx
import pytest

from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.demand.od_matrix import generate_od_pairs
from src.demand.schemas import BaselineMetricsSummary
from src.graph.builder import generate_synthetic_benito_juarez_grid
from src.graph.cleaner import extract_lscc, project_node_coordinates
from src.graph.routing_baseline import compute_baseline_routes, save_baseline_artifacts
from src.graph.weights import assign_edge_weights


@pytest.fixture
def test_network() -> nx.MultiDiGraph:
    """Fixture de red sintética ponderada y con conectividad garantizada."""
    G = generate_synthetic_benito_juarez_grid()
    G = assign_edge_weights(G)
    G = project_node_coordinates(G)
    return extract_lscc(G)


def test_poi_snapping(test_network: nx.MultiDiGraph):
    """Valida que todos los POIs se anclen a nodos existentes y activos en la red."""
    pois = load_pois_with_metric_coords()
    snapped = snap_pois_to_network(pois, test_network)

    assert len(snapped) > 0
    for poi in snapped:
        assert poi.nearest_node is not None
        assert test_network.has_node(poi.nearest_node)
        assert test_network.out_degree(poi.nearest_node) > 0
        assert test_network.in_degree(poi.nearest_node) > 0


def test_od_generation(test_network: nx.MultiDiGraph):
    """Valida la generación de matriz OD gravitatoria."""
    pois = load_pois_with_metric_coords()
    snapped = snap_pois_to_network(pois, test_network)
    od_pairs = generate_od_pairs(snapped, min_volume_threshold=10.0, max_pairs=30)

    assert len(od_pairs) > 0
    for pair in od_pairs:
        assert pair.origin_node != pair.dest_node
        assert pair.trip_volume > 0.0


def test_dijkstra_astar_equivalence(test_network: nx.MultiDiGraph):
    """Verifica que A* con heurística euclidiana y Dijkstra produzcan el mismo tiempo óptimo."""
    pois = load_pois_with_metric_coords()
    snapped = snap_pois_to_network(pois, test_network)
    od_pairs = generate_od_pairs(snapped, min_volume_threshold=15.0, max_pairs=10)

    routes_astar, _ = compute_baseline_routes(test_network, od_pairs, algorithm="astar")
    routes_dijkstra, _ = compute_baseline_routes(test_network, od_pairs, algorithm="dijkstra")

    assert len(routes_astar) == len(routes_dijkstra)

    for r_astar, r_dijkstra in zip(routes_astar, routes_dijkstra, strict=False):
        assert r_astar.origin_id == r_dijkstra.origin_id
        assert r_astar.destination_id == r_dijkstra.destination_id
        # Los tiempos óptimos de viaje deben coincidir con precisión de décimas
        assert pytest.approx(r_astar.travel_time_s, abs=0.5) == r_dijkstra.travel_time_s


def test_baseline_artifacts_saving(test_network: nx.MultiDiGraph, tmp_path: Path):
    """Valida la serialización de Parquet y el JSON de resumen de línea base."""
    pois = load_pois_with_metric_coords()
    snapped = snap_pois_to_network(pois, test_network)
    od_pairs = generate_od_pairs(snapped, min_volume_threshold=10.0, max_pairs=20)

    routes, summary = compute_baseline_routes(test_network, od_pairs, algorithm="astar")
    assert summary.unreachable_pairs == 0

    parquet_p = tmp_path / "baseline_routes.parquet"
    json_p = tmp_path / "baseline_metrics.json"

    save_baseline_artifacts(routes, summary, parquet_p, json_p)

    assert parquet_p.exists()
    assert json_p.exists()

    with open(json_p, encoding="utf-8") as f:
        data = json.load(f)

    parsed = BaselineMetricsSummary.model_validate(data)
    assert parsed.total_od_pairs == len(od_pairs)
    assert parsed.mean_travel_time_s > 0.0
    assert parsed.unreachable_pairs == 0
