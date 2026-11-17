"""Esquemas Pydantic v2 para simulación de contingencias y análisis de resiliencia.

Cumple con el principio 'Blind Data Ingestion' para exponer contratos
de perturbaciones urbanas y métricas de robustez para agentes IA.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DisruptionType(StrEnum):
    """Tipos de perturbación estocástica e incidentes viales."""

    ROAD_CLOSURE = "road_closure"  # Cierre total de tramo vial (obra, manifestación, colapso)
    CONGESTION_SPIKE = (
        "congestion_spike"  # Incremento súbito de fricción (pico C5 / embotellamiento)
    )
    TRANSFER_HUB_FAILURE = "transfer_hub_failure"  # Inhabilitación de nodo intermodal de transbordo


class DisruptionScenario(BaseModel):
    """Definición formal de un escenario de estrés o contingencia urbana."""

    model_config = ConfigDict(extra="ignore")

    scenario_id: str
    name: str
    description: str
    disruption_type: DisruptionType
    affected_edges: list[tuple[int, int]] = Field(
        default_factory=list, description="Lista de aristas (u, v) afectadas"
    )
    affected_nodes: list[int] = Field(
        default_factory=list, description="Lista de nodos inhabilitados"
    )
    friction_multiplier: float = Field(
        default=3.0, ge=1.0, description="Multiplicador de tiempo de viaje para congestión"
    )


class ReroutingRecord(BaseModel):
    """Resultado del recálculo reactivo para una ruta individual."""

    model_config = ConfigDict(extra="ignore")

    route_id: str
    origin_id: str
    destination_id: str
    was_severed: bool = Field(description="Indica si la ruta original cruzaba el área perturbada")
    rerouted_successfully: bool = Field(
        description="Indica si se encontró un camino de desvío viable"
    )
    nominal_time_s: float
    disrupted_time_s: float
    delay_seconds: float
    rerouting_duration_ms: float = Field(
        description="Tiempo de computación del recálculo en milisegundos"
    )


class ScenarioImpactSummary(BaseModel):
    """Métricas consolidadas de impacto de un escenario de contingencia."""

    scenario_id: str
    scenario_name: str
    total_routes_tested: int
    severed_routes_count: int
    service_disruption_rate_pct: float = Field(
        description="% de rutas cortadas por la perturbación"
    )
    rerouting_success_rate_pct: float = Field(description="% de rutas re-enrutadas con éxito")
    mean_delay_seconds: float = Field(description="Demora promedio por desvío en segundos")
    mean_reroute_time_ms: float = Field(description="Tiempo promedio de cómputo del desvío en ms")
    robustness_index: float = Field(
        ge=0.0, le=1.0, description="Índice de robustez R_net (1.0 = máxima resiliencia)"
    )


class ResilienceSummarySchema(BaseModel):
    """Resumen ultracompacto (< 250 tokens) de resiliencia y contingencias para LLMs."""

    model_config = ConfigDict(extra="ignore")

    algorithm: str = "Simulador Estocástico de Contingencias & Desvío Dinámico"
    scenarios_evaluated: int = Field(ge=1)
    mean_rerouting_duration_ms: float = Field(
        description="Tiempo de respuesta reactivo en milisegundos"
    )
    baseline_global_robustness: float = Field(
        ge=0.0, le=1.0, description="Robustez de red en rutas deterministas"
    )
    pareto_global_robustness: float = Field(
        ge=0.0, le=1.0, description="Robustez de red en rutas bioinspiradas NSGA-II"
    )
    resilience_gain_percent: float = Field(
        description="% incremento de resiliencia de Pareto vs Baseline"
    )
    scenarios: list[ScenarioImpactSummary]
    metadata: dict[str, Any] = Field(default_factory=dict)
