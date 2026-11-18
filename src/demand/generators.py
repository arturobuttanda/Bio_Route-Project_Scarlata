"""Generador y anclaje espacial de Puntos de Interés (POIs) en Benito Juárez.

Integra estaciones del Sistema de Movilidad Integrada (Metro, Metrobús, Trolebús)
y centroides de las colonias más representativas, proyectándolos al nodo más
cercano de la red vial mediante KDTree en UTM Zona 14N (EPSG:32614).
"""

from typing import Any

import networkx as nx
import pandas as pd
from pyproj import Transformer
from scipy.spatial import KDTree

from config.settings import settings
from src.demand.schemas import POIKind, PointOfInterest

# Catálogo calibrado de POIs neurálgicos de la alcaldía Benito Juárez (CDMX)
RAW_BENITO_JUAREZ_POIS: list[dict[str, Any]] = [
    # --- METRO (Centros de Transferencia Modal y Estaciones Clave) ---
    {
        "id": "MET_ZAPATA",
        "name": "Metro Zapata (L3/L12)",
        "kind": POIKind.METRO,
        "lat": 19.3708,
        "lon": -99.1652,
        "weight": 5.0,
    },
    {
        "id": "MET_MIXCOAC",
        "name": "Metro Mixcoac (L7/L12)",
        "kind": POIKind.METRO,
        "lat": 19.3758,
        "lon": -99.1874,
        "weight": 4.5,
    },
    {
        "id": "MET_ETIOPIA",
        "name": "Metro Etiopía / Plaza de la Transparencia (L3)",
        "kind": POIKind.METRO,
        "lat": 19.3956,
        "lon": -99.1565,
        "weight": 4.0,
    },
    {
        "id": "MET_EUGENIA",
        "name": "Metro Eugenia (L3)",
        "kind": POIKind.METRO,
        "lat": 19.3857,
        "lon": -99.1581,
        "weight": 3.5,
    },
    {
        "id": "MET_DIV_NORTE",
        "name": "Metro División del Norte (L3)",
        "kind": POIKind.METRO,
        "lat": 19.3799,
        "lon": -99.1593,
        "weight": 3.5,
    },
    {
        "id": "MET_COYOACAN",
        "name": "Metro Coyoacán (L3)",
        "kind": POIKind.METRO,
        "lat": 19.3620,
        "lon": -99.1712,
        "weight": 3.8,
    },
    {
        "id": "MET_PORTALES",
        "name": "Metro Portales (L2)",
        "kind": POIKind.METRO,
        "lat": 19.3697,
        "lon": -99.1418,
        "weight": 3.5,
    },
    {
        "id": "MET_NATIVITAS",
        "name": "Metro Nativitas (L2)",
        "kind": POIKind.METRO,
        "lat": 19.3794,
        "lon": -99.1402,
        "weight": 3.0,
    },
    {
        "id": "MET_SAN_ANTONIO",
        "name": "Metro San Antonio (L7)",
        "kind": POIKind.METRO,
        "lat": 19.3842,
        "lon": -99.1868,
        "weight": 3.5,
    },
    {
        "id": "MET_HOSP_20_NOV",
        "name": "Metro Hospital 20 de Noviembre (L12)",
        "kind": POIKind.METRO,
        "lat": 19.3725,
        "lon": -99.1776,
        "weight": 3.2,
    },
    {
        "id": "MET_INSURGENTES_SUR",
        "name": "Metro Insurgentes Sur (L12)",
        "kind": POIKind.METRO,
        "lat": 19.3739,
        "lon": -99.1798,
        "weight": 4.2,
    },
    {
        "id": "MET_PARQUE_VENADOS",
        "name": "Metro Parque de los Venados (L12)",
        "kind": POIKind.METRO,
        "lat": 19.3705,
        "lon": -99.1585,
        "weight": 3.0,
    },
    # --- METROBÚS (Corredor Insurgentes L1 y Ejes) ---
    {
        "id": "MB_FELIX_CUEVAS",
        "name": "Metrobús Félix Cuevas (L1)",
        "kind": POIKind.METROBUS,
        "lat": 19.3735,
        "lon": -99.1794,
        "weight": 4.0,
    },
    {
        "id": "MB_COL_DEL_VALLE",
        "name": "Metrobús Colonia del Valle (L1)",
        "kind": POIKind.METROBUS,
        "lat": 19.3804,
        "lon": -99.1763,
        "weight": 3.5,
    },
    {
        "id": "MB_NAPOLES",
        "name": "Metrobús Nápoles (L1)",
        "kind": POIKind.METROBUS,
        "lat": 19.3899,
        "lon": -99.1732,
        "weight": 3.5,
    },
    {
        "id": "MB_POLYFORUM",
        "name": "Metrobús Polyforum Siqueiros (L1)",
        "kind": POIKind.METROBUS,
        "lat": 19.3942,
        "lon": -99.1738,
        "weight": 3.8,
    },
    {
        "id": "MB_CD_DEPORTES",
        "name": "Metrobús Ciudad de los Deportes (L1)",
        "kind": POIKind.METROBUS,
        "lat": 19.3837,
        "lon": -99.1757,
        "weight": 3.2,
    },
    {
        "id": "MB_AMORES",
        "name": "Metrobús Amores (L2)",
        "kind": POIKind.METROBUS,
        "lat": 19.3985,
        "lon": -99.1678,
        "weight": 2.8,
    },
    # --- CENTROIDES DE COLONIAS REPRESENTATIVAS ---
    {
        "id": "COL_DEL_VALLE_CENTRO",
        "name": "Colonia Del Valle Centro",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3790,
        "lon": -99.1680,
        "weight": 4.0,
    },
    {
        "id": "COL_DEL_VALLE_SUR",
        "name": "Colonia Del Valle Sur",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3690,
        "lon": -99.1720,
        "weight": 3.8,
    },
    {
        "id": "COL_DEL_VALLE_NORTE",
        "name": "Colonia Del Valle Norte",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3910,
        "lon": -99.1650,
        "weight": 3.5,
    },
    {
        "id": "COL_NARVARTE_PONIENTE",
        "name": "Colonia Narvarte Poniente",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3900,
        "lon": -99.1550,
        "weight": 3.6,
    },
    {
        "id": "COL_NARVARTE_ORIENTE",
        "name": "Colonia Narvarte Oriente",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3930,
        "lon": -99.1480,
        "weight": 3.2,
    },
    {
        "id": "COL_NAPOLES",
        "name": "Colonia Nápoles",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3920,
        "lon": -99.1760,
        "weight": 3.7,
    },
    {
        "id": "COL_NOCHEBUENA",
        "name": "Colonia Nochebuena",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3820,
        "lon": -99.1800,
        "weight": 2.8,
    },
    {
        "id": "COL_MIXCOAC",
        "name": "Colonia Mixcoac",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3740,
        "lon": -99.1880,
        "weight": 3.2,
    },
    {
        "id": "COL_PORTALES_SUR",
        "name": "Colonia Portales Sur",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3650,
        "lon": -99.1450,
        "weight": 3.0,
    },
    {
        "id": "COL_PORTALES_NORTE",
        "name": "Colonia Portales Norte",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3720,
        "lon": -99.1440,
        "weight": 3.0,
    },
    {
        "id": "COL_ALAMOS",
        "name": "Colonia Álamos",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.4000,
        "lon": -99.1430,
        "weight": 2.9,
    },
    {
        "id": "COL_SAN_JOSE_INSURGENTES",
        "name": "Colonia San José Insurgentes",
        "kind": POIKind.COLONIA_CENTROID,
        "lat": 19.3650,
        "lon": -99.1820,
        "weight": 3.2,
    },
]


def load_pois_with_metric_coords(use_real: bool = True) -> list[PointOfInterest]:
    """Carga los POIs reales (si existen) o el catálogo base, en EPSG:32614."""
    real_path = settings.processed_data_dir / "pois_real.parquet"
    if use_real and real_path.exists():
        df = pd.read_parquet(real_path)
        return [PointOfInterest.model_validate(row) for row in df.to_dict(orient="records")]

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
    pois: list[PointOfInterest] = []

    for item in RAW_BENITO_JUAREZ_POIS:
        xm, ym = transformer.transform(item["lon"], item["lat"])
        poi = PointOfInterest(
            id=item["id"],
            name=item["name"],
            kind=item["kind"],
            lon=item["lon"],
            lat=item["lat"],
            x_m=round(xm, 2),
            y_m=round(ym, 2),
            weight=item.get("weight", 1.0),
        )
        pois.append(poi)

    return pois


def snap_pois_to_network(pois: list[PointOfInterest], G: nx.MultiDiGraph) -> list[PointOfInterest]:
    """Ancla cada POI al nodo más cercano de la LSCC vial utilizando un KDTree métrico en UTM 14N.

    Args:
        pois: Lista de puntos de interés.
        G: Grafo vial procesado (LSCC) con atributos x_m e y_m en sus nodos.

    Returns:
        Lista de POIs con el atributo nearest_node asignado.
    """
    node_ids: list[int] = []
    coords: list[tuple[float, float]] = []

    for node, data in G.nodes(data=True):
        if "x_m" in data and "y_m" in data:
            node_ids.append(node)
            coords.append((data["x_m"], data["y_m"]))

    if not coords:
        raise ValueError("El grafo no contiene coordenadas métricas x_m, y_m proyectadas.")

    tree = KDTree(coords)

    for poi in pois:
        _, idx = tree.query([poi.x_m, poi.y_m])
        poi.nearest_node = int(node_ids[idx])

    return pois
