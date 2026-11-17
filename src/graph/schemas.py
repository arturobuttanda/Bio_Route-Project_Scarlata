"""Esquemas Pydantic v2 para nodos, aristas y resúmenes topológicos de la red vial.

Cumple con el principio 'Blind Data Ingestion' para permitir a agentes IA
razonar sobre la estructura de la red sin cargar geometrías pesadas.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NodeSchema(BaseModel):
    """Contrato de atributos para nodos de la red vial."""

    model_config = ConfigDict(extra="ignore")

    osmid: int = Field(description="Identificador único del nodo en OpenStreetMap")
    x: float = Field(description="Longitud geográfica en grados decimales (EPSG:4326)")
    y: float = Field(description="Latitud geográfica en grados decimales (EPSG:4326)")
    x_m: float | None = Field(
        default=None, description="Coordenada X en metros UTM Zona 14N (EPSG:32614)"
    )
    y_m: float | None = Field(
        default=None, description="Coordenada Y en metros UTM Zona 14N (EPSG:32614)"
    )
    in_degree: int = Field(default=0, ge=0, description="Grado de entrada del nodo")
    out_degree: int = Field(default=0, ge=0, description="Grado de salida del nodo")


class EdgeSchema(BaseModel):
    """Contrato de atributos para aristas dirigidas de la red vial."""

    model_config = ConfigDict(extra="ignore")

    u: int = Field(description="Nodo origen (osmid)")
    v: int = Field(description="Nodo destino (osmid)")
    key: int = Field(default=0, description="Clave de multígrafo de NetworkX")
    name: str | list[str] | None = Field(
        default=None, description="Nombre de la vialidad o eje vial"
    )
    highway: str | list[str] = Field(description="Clasificación funcional de la vía en OSM")
    oneway: bool = Field(default=True, description="Indica si el segmento es de un solo sentido")
    reversed: bool = Field(default=False, description="Indica si la geometría fue invertida")
    is_contraflow: bool = Field(
        default=False, description="Indica si posee carril de transporte en contraflujo"
    )
    length_m: float = Field(gt=0.0, description="Longitud física proyectada en metros (EPSG:32614)")
    speed_kph: float = Field(gt=0.0, le=120.0, description="Velocidad normativa o asignada en km/h")
    travel_time_s: float = Field(gt=0.0, description="Tiempo nominal de recorrido en segundos")


class SpeedDistribution(BaseModel):
    """Distribución percentil de velocidades en la red."""

    min_kph: float
    p25_kph: float
    median_kph: float
    p75_kph: float
    max_kph: float


class NetworkSummarySchema(BaseModel):
    """Resumen ultracompacto (< 200 tokens) del estado del grafo vial para LLMs."""

    model_config = ConfigDict(extra="ignore")

    name: str = "Benito Juárez Road Network (LSCC)"
    node_count: int = Field(ge=1, description="Total de nodos en la componente fuertemente conexa")
    edge_count: int = Field(ge=1, description="Total de aristas dirigidas")
    total_length_km: float = Field(
        gt=0.0, description="Longitud acumulada de toda la red en kilómetros"
    )
    mean_travel_time_s: float = Field(
        gt=0.0, description="Tiempo de viaje promedio por arista en segundos"
    )
    is_strongly_connected: bool = Field(True, description="Garantía de conectividad fuerte (LSCC)")
    crs_projected: str = "EPSG:32614"
    speed_distribution: SpeedDistribution
    metadata: dict[str, Any] = Field(default_factory=dict)
