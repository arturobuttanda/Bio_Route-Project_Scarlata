"""Generador de escenarios de contingencia, estrés y perturbaciones viales en Benito Juárez.

Modela eventos disruptivos de alto impacto calibrados a la geografía real:
- Cierres de Ejes Viales estructurados.
- Picos de congestión severa tipo C5 (incremento del 300% en fricción).
- Fallas de acceso a nodos intermodales de transferencia masiva.
"""

import math

import networkx as nx

from src.demand.schemas import PointOfInterest
from src.simulation.schemas import DisruptionScenario, DisruptionType


def create_eje_central_closure_scenario(G: nx.MultiDiGraph) -> DisruptionScenario:
    """Crea un escenario de cierre total en Eje Central Lázaro Cárdenas.

    Inhabilita aristas que coincidan con el nombre del eje o que se ubiquen en el
    corredor oriental de Benito Juárez (lon: [-99.152, -99.142], lat: [19.365, 19.390]).
    """
    closed_edges: list[tuple[int, int]] = []

    for u, v, k, data in G.edges(keys=True, data=True):
        name = str(data.get("name", "")).lower()
        node_u = G.nodes[u]
        lat = node_u.get("y", 0.0)
        lon = node_u.get("x", 0.0)

        is_named = (
            "eje central" in name
            or "l\u00e1zaro c\u00e1rdenas" in name
            or "lazaro cardenas" in name
        )
        in_corridor = (19.365 <= lat <= 19.390) and (-99.152 <= lon <= -99.142)

        if is_named or (in_corridor and "primary" in str(data.get("highway", ""))):
            closed_edges.append((u, v))

    return DisruptionScenario(
        scenario_id="SCENARIO_EJE_CENTRAL_CLOSURE",
        name="Cierre Total de Eje Central Lázaro Cárdenas",
        description="Bloqueo por obra civil mayor o manifestación entre Xola y División del Norte.",
        disruption_type=DisruptionType.ROAD_CLOSURE,
        affected_edges=closed_edges,
        affected_nodes=[],
        friction_multiplier=999.0,
    )


def create_insurgentes_congestion_scenario(G: nx.MultiDiGraph) -> DisruptionScenario:
    """Crea un escenario de congestión severa C5 en el corredor Insurgentes / Del Valle.

    Aplica un multiplicador de fricción de 3.0x a los tiempos de viaje en el
    cuadrante comercial y financiero de Insurgentes Sur y Félix Cuevas.
    """
    congested_edges: list[tuple[int, int]] = []

    for u, v, k, data in G.edges(keys=True, data=True):
        name = str(data.get("name", "")).lower()
        node_u = G.nodes[u]
        lat = node_u.get("y", 0.0)
        lon = node_u.get("x", 0.0)

        is_named = "insurgentes" in name or "f\u00e9lix cuevas" in name or "felix cuevas" in name
        in_polygon = (19.372 <= lat <= 19.392) and (-99.182 <= lon <= -99.168)

        if is_named or in_polygon:
            congested_edges.append((u, v))

    return DisruptionScenario(
        scenario_id="SCENARIO_INSURGENTES_CONGESTION",
        name="Pico de Congestión Severa C5 Corredor Insurgentes",
        description="Embotellamiento en hora pico con incremento del 300% en fricción sobre Insurgentes y Del Valle.",
        disruption_type=DisruptionType.CONGESTION_SPIKE,
        affected_edges=congested_edges,
        affected_nodes=[],
        friction_multiplier=3.0,
    )


def create_zapata_hub_failure_scenario(
    G: nx.MultiDiGraph,
    pois: list[PointOfInterest],
    disruption_radius_m: float = 250.0,
) -> DisruptionScenario:
    """Crea un escenario de fallo/inhabilitación en el nodo intermodal Metro Zapata (L3/L12).

    Inhabilita los nodos y aristas de acceso en un radio de 250 metros del Centro de Transferencia.
    """
    # Localizar nodo de Metro Zapata
    zapata_poi = next((p for p in pois if p.id == "MET_ZAPATA"), None)
    if zapata_poi is None or zapata_poi.nearest_node is None:
        # Fallback al primer nodo céntrico si no se encuentra
        target_node = list(G.nodes())[0]
        target_xm = G.nodes[target_node].get("x_m", 484000.0)
        target_ym = G.nodes[target_node].get("y_m", 2142000.0)
    else:
        target_node = zapata_poi.nearest_node
        target_xm = G.nodes[target_node].get("x_m", zapata_poi.x_m)
        target_ym = G.nodes[target_node].get("y_m", zapata_poi.y_m)

    affected_nodes: list[int] = [target_node]
    affected_edges: list[tuple[int, int]] = []

    for n, data in G.nodes(data=True):
        if n == target_node:
            continue
        dx = data.get("x_m", 0.0) - target_xm
        dy = data.get("y_m", 0.0) - target_ym
        dist = math.sqrt(dx * dx + dy * dy)
        if dist <= disruption_radius_m:
            affected_nodes.append(n)

    for u, v, k, data in G.edges(keys=True, data=True):
        if u in affected_nodes or v in affected_nodes:
            affected_edges.append((u, v))

    return DisruptionScenario(
        scenario_id="SCENARIO_ZAPATA_HUB_FAILURE",
        name="Colapso de Nodo Intermodal Metro Zapata",
        description="Inhabilitación temporal de accesos en el Centro de Transferencia Modal Metro Zapata.",
        disruption_type=DisruptionType.TRANSFER_HUB_FAILURE,
        affected_edges=affected_edges,
        affected_nodes=affected_nodes,
        friction_multiplier=999.0,
    )


def get_all_scenarios(G: nx.MultiDiGraph, pois: list[PointOfInterest]) -> list[DisruptionScenario]:
    """Genera y retorna la suite estándar de los 3 escenarios de contingencia."""
    return [
        create_eje_central_closure_scenario(G),
        create_insurgentes_congestion_scenario(G),
        create_zapata_hub_failure_scenario(G, pois),
    ]
