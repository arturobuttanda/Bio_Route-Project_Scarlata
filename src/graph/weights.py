"""Asignación y cálculo de impedancias físicas, velocidades y tiempos de viaje.

Todas las longitudes métricas se proyectan a EPSG:32614 (UTM Zona 14N)
para eliminar distorsiones geodésicas en el ruteo.
"""

import networkx as nx

DEFAULT_SPEEDS_KPH: dict[str, float] = {
    "motorway": 60.0,
    "motorway_link": 45.0,
    "trunk": 50.0,
    "trunk_link": 40.0,
    "primary": 50.0,  # Ejes viales principales
    "primary_link": 35.0,
    "secondary": 40.0,  # Avenidas secundarias
    "secondary_link": 30.0,
    "tertiary": 35.0,
    "tertiary_link": 25.0,
    "residential": 30.0,  # Calles locales
    "living_street": 20.0,
    "unclassified": 30.0,
}


def parse_maxspeed(speed_val: str | list[str] | float | int | None, default_kph: float) -> float:
    """Parsea valores de velocidad de OSM a float en km/h."""
    if speed_val is None:
        return default_kph
    if isinstance(speed_val, (int, float)):
        return float(speed_val) if speed_val > 0 else default_kph
    if isinstance(speed_val, list):
        if not speed_val:
            return default_kph
        speed_val = speed_val[0]

    # Procesar string
    cleaned = str(speed_val).lower().replace("km/h", "").replace("kph", "").strip()
    try:
        val = float(cleaned)
        return val if val > 0 else default_kph
    except ValueError:
        return default_kph


def assign_edge_weights(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Calcula y asigna length_m, speed_kph y travel_time_s a cada arista de la red.

    Args:
        G: Grafo dirigido multígrafo.

    Returns:
        Grafo con atributos ponderados garantizados.
    """
    for u, v, k, data in G.edges(keys=True, data=True):
        # 1. Determinar tipo funcional de vía
        highway = data.get("highway", "residential")
        if isinstance(highway, list):
            highway = highway[0]

        fallback_speed = DEFAULT_SPEEDS_KPH.get(str(highway), 30.0)

        # 2. Asignar velocidad (respetando carril contraflujo o psv si existe)
        is_contraflow = data.get("is_contraflow", False) or bool(data.get("bus:lanes"))
        if is_contraflow:
            speed_kph = 35.0
        else:
            speed_kph = parse_maxspeed(data.get("maxspeed"), fallback_speed)

        # Limitar rangos razonables urbanos
        speed_kph = max(10.0, min(speed_kph, 80.0))

        # 3. Longitud métrica
        length_m = float(data.get("length", 10.0))
        if length_m <= 0.0:
            length_m = 10.0

        # 4. Tiempo nominal de viaje en segundos: tau = length_m / (v * 1000/3600)
        speed_mps = speed_kph * (1000.0 / 3600.0)
        travel_time_s = length_m / speed_mps

        # Asignar atributos limpios
        data["length_m"] = round(length_m, 2)
        data["speed_kph"] = round(speed_kph, 1)
        data["travel_time_s"] = round(travel_time_s, 2)
        data["is_contraflow"] = is_contraflow

    return G
