"""Pruebas unitarias para la validación de topología vial, LSCC e impedancias."""

import json
from pathlib import Path

import networkx as nx
import pytest

from src.graph.builder import build_road_network, generate_synthetic_benito_juarez_grid
from src.graph.cleaner import extract_lscc, project_node_coordinates
from src.graph.schemas import NetworkSummarySchema
from src.graph.weights import assign_edge_weights


@pytest.fixture
def base_graph() -> nx.MultiDiGraph:
    """Fixture que retorna una red sintética estructurada de Benito Juárez."""
    G = generate_synthetic_benito_juarez_grid()
    G = assign_edge_weights(G)
    G = project_node_coordinates(G)
    return extract_lscc(G)


def test_lscc_connectivity(base_graph: nx.MultiDiGraph):
    """Verifica que el grafo sea estrictamente fuertemente conexo (LSCC)."""
    assert nx.is_strongly_connected(base_graph), "El grafo debe ser fuertemente conexo"
    assert base_graph.number_of_nodes() > 50
    assert base_graph.number_of_edges() > 100


def test_edge_weight_attributes(base_graph: nx.MultiDiGraph):
    """Verifica que todas las aristas tengan impedancias físicas válidas y positivas."""
    for u, v, k, data in base_graph.edges(keys=True, data=True):
        assert "length_m" in data, f"Arista ({u}, {v}) carece de length_m"
        assert data["length_m"] > 0, f"Longitud nula o negativa en ({u}, {v})"

        assert "speed_kph" in data, f"Arista ({u}, {v}) carece de speed_kph"
        assert 10.0 <= data["speed_kph"] <= 80.0, f"Velocidad anómala en ({u}, {v})"

        assert "travel_time_s" in data, f"Arista ({u}, {v}) carece de travel_time_s"
        assert data["travel_time_s"] > 0, f"Tiempo de viaje nulo en ({u}, {v})"


def test_projected_coordinates(base_graph: nx.MultiDiGraph):
    """Verifica que los nodos cuenten con coordenadas proyectadas UTM 14N."""
    for node, data in base_graph.nodes(data=True):
        assert "x_m" in data, f"Nodo {node} carece de coordenada x_m"
        assert "y_m" in data, f"Nodo {node} carece de coordenada y_m"
        # Rango nominal en UTM Zona 14N para Ciudad de México
        assert 450_000 < data["x_m"] < 550_000, f"Coordenada X_m fuera de rango en {node}"
        assert 2_100_000 < data["y_m"] < 2_200_000, f"Coordenada Y_m fuera de rango en {node}"


def test_network_build_and_summary(tmp_path: Path):
    """Prueba la construcción completa y la generación del resumen ultracompacto."""
    G, graphml_path = build_road_network(
        buffer_meters=500.0, force_synthetic=True, output_dir=tmp_path
    )

    assert graphml_path.exists()
    assert nx.is_strongly_connected(G)

    summary_file = tmp_path / "network_summary.json"
    assert summary_file.exists()

    with open(summary_file, encoding="utf-8") as f:
        data = json.load(f)

    # Validar contra el esquema Pydantic
    summary = NetworkSummarySchema.model_validate(data)
    assert summary.is_strongly_connected is True
    assert summary.node_count > 0
    assert summary.total_length_km > 0.0
    assert summary.speed_distribution.median_kph > 0.0
