"""Pruebas unitarias para operadores topológicos y algoritmo NSGA-II."""

import networkx as nx
import pytest

from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.demand.od_matrix import generate_od_pairs
from src.graph.builder import generate_synthetic_benito_juarez_grid
from src.graph.cleaner import extract_lscc, project_node_coordinates
from src.graph.weights import assign_edge_weights
from src.optimization.nsga2 import (
    NSGA2Solver,
    dominates,
    fast_non_dominated_sort,
)
from src.optimization.operators import (
    crossover_intersection,
    mutation_k_shortest_path,
    repair_path,
)
from src.optimization.schemas import NetworkPlanIndividual, ObjectiveValues


@pytest.fixture
def synthetic_graph() -> nx.MultiDiGraph:
    """Retorna un grafo sintético cuadrangular conexo y ponderado."""
    G = generate_synthetic_benito_juarez_grid()
    G = assign_edge_weights(G)
    G = project_node_coordinates(G)
    return extract_lscc(G)


def test_repair_path_loop_removal(synthetic_graph: nx.MultiDiGraph):
    """Valida que repair_path elimine bucles cíclicos internos."""
    nodes = list(synthetic_graph.nodes())[:10]
    # Camino artificial con bucle: A -> B -> C -> B -> D
    cyclic_path = [nodes[0], nodes[1], nodes[2], nodes[1], nodes[3]]
    repaired = repair_path(synthetic_graph, cyclic_path)

    # El camino reparado no debe tener nodos duplicados consecutivos ni bucles
    assert len(repaired) < len(cyclic_path)
    # Todos los saltos deben existir en el grafo
    for i in range(len(repaired) - 1):
        assert synthetic_graph.has_edge(repaired[i], repaired[i + 1])


def test_crossover_intersection(synthetic_graph: nx.MultiDiGraph):
    """Valida que el cruce de intersección preserve la continuidad."""
    nodes = list(synthetic_graph.nodes())
    # Dos caminos con un nodo común intermedio
    u1, pivot, v1 = nodes[0], nodes[15], nodes[30]
    u2, v2 = nodes[2], nodes[40]

    try:
        p1 = (
            nx.shortest_path(synthetic_graph, u1, pivot)
            + nx.shortest_path(synthetic_graph, pivot, v1)[1:]
        )
        p2 = (
            nx.shortest_path(synthetic_graph, u2, pivot)
            + nx.shortest_path(synthetic_graph, pivot, v2)[1:]
        )

        child1, child2 = crossover_intersection(synthetic_graph, p1, p2)

        # Validar continuidad de los hijos
        for c in (child1, child2):
            for i in range(len(c) - 1):
                assert synthetic_graph.has_edge(c[i], c[i + 1])
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass


def test_mutation_k_shortest_path(synthetic_graph: nx.MultiDiGraph):
    """Valida que la mutación topológica genere caminos válidos continuos."""
    nodes = list(synthetic_graph.nodes())
    start, end = nodes[0], nodes[25]
    try:
        base_path = nx.shortest_path(synthetic_graph, start, end)
        mutated = mutation_k_shortest_path(synthetic_graph, base_path, mutation_intensity=1.0)

        assert len(mutated) >= 2
        for i in range(len(mutated) - 1):
            assert synthetic_graph.has_edge(mutated[i], mutated[i + 1])
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass


def test_pareto_dominance():
    """Valida la lógica de dominancia de Pareto con objetivos mixtos (min, min, max)."""
    # A es mejor en todo: menos tiempo, menos traslape, más cobertura
    sol_a = ObjectiveValues(
        f1_travel_time_s=100.0, f2_overlap_length_m=500.0, f3_coverage_ratio=0.85
    )
    sol_b = ObjectiveValues(
        f1_travel_time_s=150.0, f2_overlap_length_m=800.0, f3_coverage_ratio=0.60
    )
    sol_c = ObjectiveValues(
        f1_travel_time_s=90.0, f2_overlap_length_m=900.0, f3_coverage_ratio=0.70
    )

    assert dominates(sol_a, sol_b) is True
    assert dominates(sol_b, sol_a) is False
    # A y C no se dominan mutuamente (trade-off)
    assert dominates(sol_a, sol_c) is False
    assert dominates(sol_c, sol_a) is False


def test_fast_non_dominated_sort():
    """Valida la clasificación en frentes de Pareto."""
    ind_a = NetworkPlanIndividual(
        individual_id="A",
        routes=[],
        fitness=ObjectiveValues(
            f1_travel_time_s=100.0, f2_overlap_length_m=500.0, f3_coverage_ratio=0.9
        ),
    )
    ind_b = NetworkPlanIndividual(
        individual_id="B",
        routes=[],
        fitness=ObjectiveValues(
            f1_travel_time_s=120.0, f2_overlap_length_m=600.0, f3_coverage_ratio=0.7
        ),
    )
    ind_c = NetworkPlanIndividual(
        individual_id="C",
        routes=[],
        fitness=ObjectiveValues(
            f1_travel_time_s=90.0, f2_overlap_length_m=800.0, f3_coverage_ratio=0.8
        ),
    )

    fronts = fast_non_dominated_sort([ind_a, ind_b, ind_c])
    assert len(fronts) >= 2
    # Frente 0 contiene a los no dominados (A y C)
    front_0_ids = {ind.individual_id for ind in fronts[0]}
    assert "A" in front_0_ids
    assert "C" in front_0_ids
    # B está dominado por A, por lo que va a un frente inferior
    assert "B" in {ind.individual_id for ind in fronts[1]}


def test_nsga2_solver_mini_run(synthetic_graph: nx.MultiDiGraph):
    """Valida una corrida corta del solver NSGA-II."""
    pois = load_pois_with_metric_coords()
    snapped = snap_pois_to_network(pois, synthetic_graph)
    od_pairs = generate_od_pairs(snapped, min_volume_threshold=20.0, max_pairs=4)

    solver = NSGA2Solver(
        G=synthetic_graph,
        od_pairs=od_pairs,
        pois=snapped,
        population_size=6,
        generations=2,
        seed=42,
    )

    pareto_front, history = solver.evolve()

    assert len(pareto_front) > 0
    assert len(history) == 2
    for ind in pareto_front:
        assert ind.fitness.f1_travel_time_s > 0.0
        assert 0.0 <= ind.fitness.f3_coverage_ratio <= 1.0
