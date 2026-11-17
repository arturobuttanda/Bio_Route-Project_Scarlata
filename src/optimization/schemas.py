"""Esquemas Pydantic v2 para el motor de optimización bioinspirada (NSGA-II).

Cumple con el principio 'Blind Data Ingestion' para exponer contratos
de genomas, frentes de Pareto y resúmenes analíticos para agentes IA.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RouteChromosome(BaseModel):
    """Representación de una ruta individual en el genoma."""

    model_config = ConfigDict(extra="ignore")

    route_id: str
    origin_id: str
    destination_id: str
    node_sequence: list[int] = Field(description="Secuencia ordenada de nodos dirigidos continuos")
    length_m: float = Field(ge=0.0, description="Longitud física en metros")
    travel_time_s: float = Field(ge=0.0, description="Tiempo nominal de viaje en segundos")


class ObjectiveValues(BaseModel):
    """Vector de valores fitness multiobjetivo."""

    f1_travel_time_s: float = Field(description="Minimizar: Tiempo total ponderado por demanda")
    f2_overlap_length_m: float = Field(
        description="Minimizar: Longitud de aristas duplicadas/traslapadas"
    )
    f3_coverage_ratio: float = Field(
        ge=0.0, le=1.0, description="Maximizar: Proporción de demanda cubierta (400m)"
    )


class NetworkPlanIndividual(BaseModel):
    """Individuo de la población: conjunto de K rutas que forman una red alimentadora."""

    model_config = ConfigDict(extra="ignore")

    individual_id: str
    routes: list[RouteChromosome]
    fitness: ObjectiveValues
    rank: int = Field(default=0, ge=0, description="Rango de no dominancia en NSGA-II")
    crowding_distance: float = Field(default=0.0, ge=0.0, description="Distancia de hacinamiento")


class ParetoSolutionSummary(BaseModel):
    """Resumen de una solución representativa en el Frente de Pareto."""

    solution_id: str
    travel_time_s: float
    overlap_m: float
    coverage_percentage: float
    route_count: int
    total_length_km: float


class OptimizationSummarySchema(BaseModel):
    """Resumen ultracompacto (< 300 tokens) de la optimización bioinspirada para LLMs."""

    model_config = ConfigDict(extra="ignore")

    algorithm: str = "NSGA-II Multiobjetivo Bioinspirado"
    population_size: int = Field(ge=10)
    generations: int = Field(ge=1)
    pareto_solutions_count: int = Field(ge=1)
    hypervolume: float = Field(ge=0.0, description="Métrica de calidad del frente de Pareto")

    # Comparativa porcentual frente al baseline determinista
    baseline_time_s: float
    best_time_solution_s: float
    time_delta_percent: float = Field(description="% cambio en tiempo de viaje")

    baseline_coverage_percent: float
    best_coverage_solution_percent: float
    coverage_improvement_percent: float = Field(description="% incremento de cobertura")

    best_solutions: list[ParetoSolutionSummary]
    metadata: dict[str, Any] = Field(default_factory=dict)
