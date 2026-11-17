"""Pruebas unitarias para el motor de simulación de contingencias y análisis de resiliencia."""

import json
from pathlib import Path

import networkx as nx
import pytest

from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.graph.builder import generate_synthetic_benito_juarez_grid
from src.graph.cleaner import extract_lscc, project_node_coordinates
from src.graph.routing_baseline import make_euclidean_heuristic
from src.graph.weights import assign_edge_weights
from src.simulation.engine import (
    apply_scenario_to_graph,
    evaluate_scenario_on_routes,
    reroute_single_path,
    run_comparative_resilience_simulation,
)
from src.simulation.scenarios import (
    create_eje_central_closure_scenario,
    create_insurgentes_congestion_scenario,
    create_zapata_hub_failure_scenario,
    get_all_scenarios,
)
from src.simulation.schemas import DisruptionType, ResilienceSummarySchema


@pytest.fixture
def sim_graph() -> nx.MultiDiGraph:
    """Grafo sintético representativo de Benito Juárez con atributos e impedancias."""
    G = generate_synthetic_benito_juarez_grid()
    G = assign_edge_weights(G)
    G = project_node_coordinates(G)
    return extract_lscc(G)


@pytest.fixture
def snapped_pois(sim_graph: nx.MultiDiGraph):
    """POIs anclados a la red sintética."""
    pois = load_pois_with_metric_coords()
    return snap_pois_to_network(pois, sim_graph)


def test_scenario_generation(sim_graph: nx.MultiDiGraph, snapped_pois):
    """Valida la generación de los 3 escenarios de perturbación."""
    sc_eje = create_eje_central_closure_scenario(sim_graph)
    assert sc_eje.disruption_type == DisruptionType.ROAD_CLOSURE
    assert len(sc_eje.affected_edges) > 0

    sc_ins = create_insurgentes_congestion_scenario(sim_graph)
    assert sc_ins.disruption_type == DisruptionType.CONGESTION_SPIKE
    assert sc_ins.friction_multiplier == 3.0

    sc_zapata = create_zapata_hub_failure_scenario(sim_graph, snapped_pois)
    assert sc_zapata.disruption_type == DisruptionType.TRANSFER_HUB_FAILURE
    assert len(sc_zapata.affected_nodes) > 0

    all_scenarios = get_all_scenarios(sim_graph, snapped_pois)
    assert len(all_scenarios) == 3


def test_apply_scenario_to_graph(sim_graph: nx.MultiDiGraph):
    """Verifica que la perturbación modifique únicamente la copia del grafo sin mutar el original."""
    edge = list(sim_graph.edges())[0]
    orig_time = sim_graph[edge[0]][edge[1]][0]["travel_time_s"]

    sc = create_eje_central_closure_scenario(sim_graph)
    G_disrupted = apply_scenario_to_graph(sim_graph, sc)

    # El original conserva su peso nominal
    assert sim_graph[edge[0]][edge[1]][0]["travel_time_s"] == orig_time

    # Las aristas afectadas en el perturbado tienen peso prohibitivo
    if sc.affected_edges:
        u_aff, v_aff = sc.affected_edges[0]
        if G_disrupted.has_edge(u_aff, v_aff):
            disrupted_time = G_disrupted[u_aff][v_aff][0]["travel_time_s"]
            assert disrupted_time >= 900_000.0


def test_reroute_single_path_performance(sim_graph: nx.MultiDiGraph):
    """Valida que el recálculo reactivo resuelva un desvío válido en menos de 50 ms (SLA)."""
    nodes = list(sim_graph.nodes())
    u, v = nodes[0], nodes[25]
    heuristic = make_euclidean_heuristic(sim_graph)

    path, total_time, duration_ms = reroute_single_path(sim_graph, u, v, heuristic)

    assert path is not None
    assert total_time > 0.0
    assert duration_ms < 50.0  # SLA de latencia reactiva en tiempo real


def test_evaluate_scenario_on_routes(sim_graph: nx.MultiDiGraph):
    """Valida la evaluación de contingencia y el cálculo de robustez R_net."""
    nodes = list(sim_graph.nodes())
    # Fabricar rutas sintéticas
    sample_routes = [
        {
            "route_id": "r1",
            "origin_id": "O1",
            "destination_id": "D1",
            "path_nodes": [nodes[0], nodes[1], nodes[2]],
            "travel_time_s": 50.0,
        },
        {
            "route_id": "r2",
            "origin_id": "O2",
            "destination_id": "D2",
            "path_nodes": [nodes[5], nodes[6], nodes[7]],
            "travel_time_s": 60.0,
        },
    ]

    sc = create_eje_central_closure_scenario(sim_graph)
    records, summary = evaluate_scenario_on_routes(sim_graph, sample_routes, sc)

    assert len(records) == 2
    assert summary.total_routes_tested == 2
    assert 0.0 <= summary.robustness_index <= 1.0


def test_comparative_resilience_simulation(
    sim_graph: nx.MultiDiGraph, snapped_pois, tmp_path: Path
):
    """Valida la simulación comparativa y la generación del resumen JSON y Parquet."""
    nodes = list(sim_graph.nodes())
    base_routes = [
        {
            "route_id": "b1",
            "origin_id": "O1",
            "destination_id": "D1",
            "path_nodes": [nodes[0], nodes[12], nodes[24]],
            "travel_time_s": 80.0,
        },
    ]
    pareto_routes = [
        {
            "route_id": "p1",
            "origin_id": "O1",
            "destination_id": "D1",
            "path_nodes": [nodes[0], nodes[1], nodes[13], nodes[24]],
            "travel_time_s": 75.0,
        },
    ]

    json_p = tmp_path / "resilience_metrics.json"
    parquet_p = tmp_path / "contingency_results.parquet"

    summary = run_comparative_resilience_simulation(
        G=sim_graph,
        pois=snapped_pois,
        baseline_routes=base_routes,
        pareto_routes=pareto_routes,
        output_json_path=json_p,
        output_parquet_path=parquet_p,
    )

    assert json_p.exists()
    assert parquet_p.exists()
    assert summary.scenarios_evaluated == 3
    assert summary.baseline_global_robustness > 0.0

    # Validar schema Pydantic
    with open(json_p, encoding="utf-8") as f:
        data = json.load(f)
    validated = ResilienceSummarySchema.model_validate(data)
    assert validated.scenarios_evaluated == 3
