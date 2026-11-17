"""Generación y calibración de la matriz Origen-Destino (OD) de Benito Juárez.

Modela la interacción gravitatoria entre zonas residenciales (colonias) y
hubs de transporte masivo (Metro / Metrobús) calibrada con factores de atracción.
"""

import math

from src.demand.schemas import ODPair, PointOfInterest


def compute_gravity_trip_volume(
    origin: PointOfInterest,
    destination: PointOfInterest,
    base_flow: float = 100.0,
    distance_decay_scale: float = 2000.0,
) -> float:
    """Calcula el volumen de viajes horario mediante un modelo gravitatorio ajustado.

    T_ij = base_flow * (W_i * W_j) / (1 + (dist_ij / decay_scale)^2)
    """
    dx = origin.x_m - destination.x_m
    dy = origin.y_m - destination.y_m
    dist_m = math.sqrt(dx * dx + dy * dy)

    if dist_m < 50.0:  # Mismo nodo o muy cercano
        return 0.0

    friction = 1.0 + (dist_m / distance_decay_scale) ** 2
    raw_volume = base_flow * (origin.weight * destination.weight) / friction
    return round(raw_volume, 1)


def generate_od_pairs(
    pois: list[PointOfInterest],
    min_volume_threshold: float = 15.0,
    max_pairs: int | None = None,
) -> list[ODPair]:
    """Genera la lista de pares OD a partir de los POIs con nodos asignados.

    Args:
        pois: Lista de POIs ya anclados a la red vial.
        min_volume_threshold: Filtro de corte de volumen mínimo para evitar ruido.
        max_pairs: Límite superior opcional de pares a generar.

    Returns:
        Lista de pares ODPair con volúmenes calculados.
    """
    pairs: list[ODPair] = []

    for orig in pois:
        if orig.nearest_node is None:
            continue
        for dest in pois:
            if dest.nearest_node is None or orig.id == dest.id:
                continue

            # Si el nodo de red origen y destino son idénticos, omitir
            if orig.nearest_node == dest.nearest_node:
                continue

            volume = compute_gravity_trip_volume(orig, dest)
            if volume >= min_volume_threshold:
                pairs.append(
                    ODPair(
                        origin_id=orig.id,
                        destination_id=dest.id,
                        origin_node=orig.nearest_node,
                        dest_node=dest.nearest_node,
                        trip_volume=volume,
                    )
                )

    # Ordenar de mayor a menor volumen de viajes
    pairs.sort(key=lambda p: p.trip_volume, reverse=True)

    if max_pairs is not None:
        pairs = pairs[:max_pairs]

    return pairs
