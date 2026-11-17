"""Esquemas Pydantic v2 para modelado de demanda, puntos de interés (POIs) y línea base."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class POIKind(StrEnum):
    """Categorías de generadores y atractores espaciales."""

    METRO = "metro"
    METROBUS = "metrobus"
    TROLEBUS = "trolebus"
    COLONIA_CENTROID = "colonia_centroid"


class PointOfInterest(BaseModel):
    """Punto de interés (estación de transporte masivo o centroide barrial)."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(description="Identificador alfanumérico único")
    name: str = Field(description="Nombre oficial o toponímico")
    kind: POIKind = Field(description="Tipo de POI")
    lon: float = Field(description="Longitud geográfica EPSG:4326")
    lat: float = Field(description="Latitud geográfica EPSG:4326")
    x_m: float = Field(description="Coordenada X métrica en EPSG:32614")
    y_m: float = Field(description="Coordenada Y métrica en EPSG:32614")
    weight: float = Field(default=1.0, gt=0.0, description="Factor de peso/atracción en viajes")
    nearest_node: int | None = Field(
        default=None, description="Nodo de la LSCC vial al que está anclado"
    )


class ODPair(BaseModel):
    """Par Origen-Destino con volumen de demanda calibrado."""

    model_config = ConfigDict(extra="ignore")

    origin_id: str
    destination_id: str
    origin_node: int = Field(description="Nodo de red vial del origen")
    dest_node: int = Field(description="Nodo de red vial del destino")
    trip_volume: float = Field(default=1.0, ge=0.0, description="Volumen estimado de viajes / hora")


class RouteResult(BaseModel):
    """Resultado del ruteo determinista para un par OD."""

    model_config = ConfigDict(extra="ignore")

    origin_id: str
    destination_id: str
    path: list[int] = Field(
        description="Secuencia ordenada de nodos que conforman el camino mínimo"
    )
    length_m: float = Field(ge=0.0, description="Longitud física acumulada en metros")
    travel_time_s: float = Field(ge=0.0, description="Tiempo de viaje nominal en segundos")


class BaselineMetricsSummary(BaseModel):
    """Resumen cuantitativo ultracompacto (< 250 tokens) de la línea base determinista para LLMs."""

    model_config = ConfigDict(extra="ignore")

    algorithm: str = "A* / Dijkstra Bidireccional"
    total_od_pairs: int = Field(ge=1, description="Cantidad de pares OD evaluados")
    total_trips_simulated: float = Field(ge=0.0, description="Suma de volumen de viajes")
    mean_travel_time_s: float = Field(gt=0.0, description="Tiempo de viaje promedio en segundos")
    median_travel_time_s: float = Field(gt=0.0, description="Mediana (p50) del tiempo de viaje")
    p90_travel_time_s: float = Field(gt=0.0, description="Percentil 90 del tiempo de viaje")
    mean_distance_m: float = Field(gt=0.0, description="Distancia promedio en metros")
    total_passenger_hours: float = Field(gt=0.0, description="Horas-pasajero totales consumidas")
    unreachable_pairs: int = Field(0, description="Pares sin ruta posible (debe ser 0 en LSCC)")
    metadata: dict[str, Any] = Field(default_factory=dict)
