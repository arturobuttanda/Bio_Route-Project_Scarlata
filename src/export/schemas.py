"""Esquemas Pydantic para la exportación geoespacial (GeoPackage, GeoParquet, GeoJSON).

Garantiza el contrato de blind data ingestion y validación de tipos estricta.
"""

from pydantic import BaseModel, Field


class LayerSummary(BaseModel):
    """Resumen de una capa geográfica exportada."""

    name: str = Field(..., description="Nombre de la capa en el GeoPackage")
    feature_count: int = Field(..., ge=0, description="Cantidad de geometrías")
    geometry_type: str = Field(..., description="Tipo de geometría (Point, LineString, Polygon)")
    crs: str = Field(..., description="Código EPSG de referencia espacial")


class ExportSummarySchema(BaseModel):
    """Resumen de los artefactos espaciales exportados para GIS y Analytics."""

    gpkg_path: str = Field(..., description="Ruta al archivo OGC GeoPackage")
    geoparquet_path: str = Field(..., description="Ruta al archivo GeoParquet para DuckDB/Tableau")
    geojson_path: str = Field(..., description="Ruta al archivo Web GeoJSON (RFC 7946)")
    layers: list[LayerSummary] = Field(
        default_factory=list, description="Capas contenidas en el GeoPackage"
    )
    total_features: int = Field(..., ge=0, description="Total de entidades exportadas")
