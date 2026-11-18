"""Limpieza topológica, consolidación y extracción de la Largest Strongly Connected Component (LSCC)."""

import json
from pathlib import Path

import networkx as nx
import numpy as np
from pyproj import Transformer

from config.settings import settings
from src.graph.schemas import NetworkSummarySchema, SpeedDistribution
from src.graph.weights import assign_edge_weights


def load_road_network(
    graph_path: Path | None = None,
    ensure_weights: bool = True,
) -> nx.MultiDiGraph:
    """Carga el grafo LSCC desde GraphML, normaliza IDs de nodos y tipa atributos."""
    if graph_path is None:
        graph_path = settings.processed_data_dir / "road_network_lscc.graphml"

    G = nx.read_graphml(graph_path)
    G = nx.relabel_nodes(G, {n: int(n) if str(n).isdigit() else n for n in G.nodes()})

    for _, _, d in G.edges(data=True):
        for attr in ("travel_time_s", "length_m", "speed_kph", "risk_score", "safe_travel_time_s"):
            if attr in d:
                d[attr] = float(d[attr])
        if "accident_count" in d:
            d["accident_count"] = int(float(d["accident_count"]))

    for _, d in G.nodes(data=True):
        for attr in ("x", "y", "x_m", "y_m", "x_proj", "y_proj"):
            if attr in d:
                d[attr] = float(d[attr])

    if ensure_weights:
        G = project_node_coordinates(G)
        G = assign_edge_weights(G)

    return G


def project_node_coordinates(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Proyecta las coordenadas de los nodos a UTM Zona 14N (EPSG:32614)."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
    for node, data in G.nodes(data=True):
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            xm, ym = transformer.transform(x, y)
            data["x_m"] = round(xm, 2)
            data["y_m"] = round(ym, 2)
    return G


def inject_contraflow_transit_edges(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Detecta y duplica aristas virtuales para carriles de transporte público en contraflujo.

    Ejemplo clave en Benito Juárez: Eje Central Lázaro Cárdenas posee flujo vehicular
    sur->norte y carril trolebús confinado norte->sur.
    """
    edges_to_add: list[tuple[int, int, dict]] = []

    for u, v, k, data in G.edges(keys=True, data=True):
        name = str(data.get("name", "")).lower()
        highway = str(data.get("highway", "")).lower()

        # Condición de contraflujo por nombre o tag OSM
        has_contraflow_tag = bool(
            data.get("bus:lanes") or data.get("lanes:bus:backward") or data.get("psv")
        )
        is_eje_vial = "eje" in name or "insurgentes" in name or "cuauhtémoc" in name

        if has_contraflow_tag or (is_eje_vial and "primary" in highway):
            # Si no existe arista inversa v -> u, agregamos una arista de transporte público
            if not G.has_edge(v, u):
                reversed_data = data.copy()
                reversed_data["is_contraflow"] = True
                reversed_data["reversed"] = True
                reversed_data["oneway"] = True
                reversed_data["speed_kph"] = 35.0  # Velocidad comercial de trolebús/metrobús
                # Recomputar tiempo de viaje
                length_m = reversed_data.get("length_m", 20.0)
                speed_mps = 35.0 * (1000.0 / 3600.0)
                reversed_data["travel_time_s"] = round(length_m / speed_mps, 2)
                edges_to_add.append((v, u, reversed_data))

    for u_rev, v_rev, r_data in edges_to_add:
        G.add_edge(u_rev, v_rev, **r_data)

    return G


def extract_lscc(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Extrae la Componente Fuertemente Conexa más grande (LSCC).

    Garantiza que todo par ordenado de nodos (u, v) tenga una ruta finita disponible.
    """
    if G.is_directed():
        scc_components = list(nx.strongly_connected_components(G))
        largest = max(scc_components, key=len)
        G_lscc = G.subgraph(largest).copy()
    else:
        cc_components = list(nx.connected_components(G))
        largest = max(cc_components, key=len)
        G_lscc = G.subgraph(largest).copy()

    # Actualizar grados de entrada y salida
    for node, data in G_lscc.nodes(data=True):
        data["in_degree"] = G_lscc.in_degree(node)
        data["out_degree"] = G_lscc.out_degree(node)

    return G_lscc


def generate_network_summary(
    G: nx.MultiDiGraph, output_json_path: Path | None = None
) -> NetworkSummarySchema:
    """Genera un reporte sintético ultracompacto (< 200 tokens) para razonamiento de IA."""
    speeds = [data.get("speed_kph", 30.0) for _, _, data in G.edges(data=True)]
    times = [data.get("travel_time_s", 1.0) for _, _, data in G.edges(data=True)]
    lengths = [data.get("length_m", 1.0) for _, _, data in G.edges(data=True)]

    speed_dist = SpeedDistribution(
        min_kph=float(np.min(speeds)) if speeds else 0.0,
        p25_kph=float(np.percentile(speeds, 25)) if speeds else 0.0,
        median_kph=float(np.median(speeds)) if speeds else 0.0,
        p75_kph=float(np.percentile(speeds, 75)) if speeds else 0.0,
        max_kph=float(np.max(speeds)) if speeds else 0.0,
    )

    summary = NetworkSummarySchema(
        name="Benito Juárez Road Network (LSCC)",
        node_count=G.number_of_nodes(),
        edge_count=G.number_of_edges(),
        total_length_km=round(sum(lengths) / 1000.0, 2),
        mean_travel_time_s=round(float(np.mean(times)), 2) if times else 0.0,
        is_strongly_connected=nx.is_strongly_connected(G),
        crs_projected="EPSG:32614",
        speed_distribution=speed_dist,
        metadata={
            "contraflow_edges": sum(
                1 for _, _, d in G.edges(data=True) if d.get("is_contraflow", False)
            ),
        },
    )

    if output_json_path:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(summary.model_dump(), f, indent=2)

    return summary
