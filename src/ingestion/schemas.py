"""Esquemas Pydantic v2 para ingesta real de POIs, transporte público y accidentes viales."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TransitMode(StrEnum):
    """Modalidades de transporte público modeladas en Benito Juárez."""

    METRO = "metro"
    METROBUS = "metrobus"
    RTP = "rtp"
    TROLEBUS = "trolebus"
    CONCESSIONAIRE = "concessionaire"


class TransitSummarySchema(BaseModel):
    """Resumen compacto (< 300 tokens) de la red real de transporte público."""

    model_config = ConfigDict(extra="ignore")

    total_lines: int = Field(ge=0)
    total_stops: int = Field(ge=0)
    lines_by_mode: dict[str, int] = Field(default_factory=dict)
    stops_by_mode: dict[str, int] = Field(default_factory=dict)
    total_length_km: float = Field(ge=0.0)
    crs_projected: str = "EPSG:32614"
    sources: list[str] = Field(default_factory=list)


class AccidentRecord(BaseModel):
    """Registro normalizado de hecho de tránsito en Benito Juárez."""

    model_config = ConfigDict(extra="ignore")

    folio: str
    fecha_evento: str
    hora_evento: str | None = None
    tipo_evento: str
    latitud: float
    longitud: float
    colonia: str | None = None
    prioridad: str | None = None
    personas_lesionadas: int = 0
    personas_fallecidas: int = 0
    severity_weight: float = Field(default=1.0, gt=0.0)


class AccidentHotspotSummary(BaseModel):
    """Punto crítico de siniestralidad vial."""

    colonia: str
    lat: float
    lon: float
    accident_count: int
    injured_total: int
    fatalities_total: int


class AccidentsSummarySchema(BaseModel):
    """Resumen compacto (< 300 tokens) de siniestralidad vial en Benito Juárez."""

    model_config = ConfigDict(extra="ignore")

    total_accidents: int = Field(ge=0)
    date_min: str | None = None
    date_max: str | None = None
    window_months: int = 24
    total_injured: int = 0
    total_fatalities: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    top_hotspots: list[AccidentHotspotSummary] = Field(default_factory=list)
    edges_with_accidents: int = 0
    crs_projected: str = "EPSG:32614"
    metadata: dict[str, Any] = Field(default_factory=dict)


class POISummarySchema(BaseModel):
    """Resumen compacto de POIs reales extraídos para Benito Juárez."""

    model_config = ConfigDict(extra="ignore")

    total_pois: int = Field(ge=0)
    counts_by_kind: dict[str, int] = Field(default_factory=dict)
    crs_projected: str = "EPSG:32614"
    sources: list[str] = Field(default_factory=list)


class QALandmarkCheck(BaseModel):
    """Resultado de verificación de un hito geográfico de referencia."""

    name: str
    found: bool
    distance_error_m: float | None = None
    within_tolerance: bool = False


class QAReportSchema(BaseModel):
    """Reporte compacto de auditoría espacial (GIS QA) para Benito Juárez."""

    model_config = ConfigDict(extra="ignore")

    pois_total: int = 0
    pois_containment_pct: float = 0.0
    pois_mean_snap_m: float = 0.0
    pois_p95_snap_m: float = 0.0
    pois_outliers_gt_150m: int = 0
    transit_lines_total: int = 0
    transit_stops_total: int = 0
    transit_stops_containment_pct: float = 0.0
    transit_stops_mean_snap_m: float = 0.0
    accidents_total: int = 0
    accidents_containment_pct: float = 0.0
    landmark_checks: list[QALandmarkCheck] = Field(default_factory=list)
    passed: bool = False


class AccidentClusterSchema(BaseModel):
    """Cluster espacial crítico descubierto mediante DBSCAN en EPSG:32614."""

    cluster_id: int
    label: str
    lat: float
    lon: float
    radius_m: float
    accident_count: int
    injured_total: int
    fatalities_total: int
    severity_sum: float
    dominant_type: str
    peak_hour: int


class AccidentAnalyticsSchema(BaseModel):
    """Analítica espacial (DBSCAN) y temporal (24h) de siniestralidad vial."""

    model_config = ConfigDict(extra="ignore")

    total_analyzed: int = 0
    eps_meters: float = 120.0
    min_samples: int = 15
    cluster_count: int = 0
    clusters: list[AccidentClusterSchema] = Field(default_factory=list)
    hourly_counts: list[int] = Field(default_factory=lambda: [0] * 24)
    band_counts: dict[str, int] = Field(default_factory=dict)


class TrafficSummarySchema(BaseModel):
    """Resumen compacto de congestión y nivel de servicio vial en Benito Juárez."""

    model_config = ConfigDict(extra="ignore")

    total_edges_evaluated: int = 0
    infovial_records_used: int = 0
    mean_factor_by_band: dict[str, float] = Field(default_factory=dict)
    los_distribution_pm: dict[str, int] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
