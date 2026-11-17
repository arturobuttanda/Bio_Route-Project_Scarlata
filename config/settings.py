"""Configuración centralizada del sistema mediante Pydantic Settings y YAML espacial."""

from functools import cached_property
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BoundaryParams(BaseModel):
    """Parámetros de delimitación territorial."""

    name: str = "Benito Juárez"
    state: str = "Ciudad de México"
    cve_geo: str = "09014"
    buffer_meters: float = 500.0


class SpatialCRSParams(BaseModel):
    """Sistemas de referencia espaciales y parámetros de borde."""

    crs_geographic: str = "EPSG:4326"
    crs_projected: str = "EPSG:32614"
    boundary: BoundaryParams = Field(default_factory=BoundaryParams)


class SpeedParams(BaseModel):
    """Velocidades urbanas nominales y factores de penalización."""

    default_primary_kph: float = 50.0
    default_secondary_kph: float = 40.0
    default_residential_kph: float = 30.0
    transit_contraflow_kph: float = 35.0
    congested_factor: float = 0.33


class DemandParams(BaseModel):
    """Parámetros de cobertura caminable y demanda."""

    walkable_radius_meters: float = 400.0
    transit_transfer_penalty_seconds: float = 300.0


class OptimizationParams(BaseModel):
    """Hiperparámetros por defecto para el algoritmo NSGA-II."""

    default_seed: int = 42
    population_size: int = 50
    generations: int = 60
    crossover_prob: float = 0.8
    mutation_prob: float = 0.2


class SpatialParams(BaseModel):
    """Contrato completo del archivo config/spatial_params.yaml."""

    spatial: SpatialCRSParams = Field(default_factory=SpatialCRSParams)
    speeds: SpeedParams = Field(default_factory=SpeedParams)
    demand: DemandParams = Field(default_factory=DemandParams)
    optimization: OptimizationParams = Field(default_factory=OptimizationParams)


class AppSettings(BaseSettings):
    """Ajustes de entorno y rutas del sistema."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Identificación
    app_name: str = "benito_juarez_spatial_optimization"
    debug: bool = False
    random_seed: int = 42

    # Rutas base del proyecto
    base_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = base_dir / "data"
    raw_data_dir: Path = data_dir / "raw"
    interim_data_dir: Path = data_dir / "interim"
    processed_data_dir: Path = data_dir / "processed"
    outputs_dir: Path = data_dir / "outputs"
    config_dir: Path = base_dir / "config"

    # Configuración de Base de Datos PostGIS
    db_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    db_port: int = Field(default=5432, alias="POSTGRES_PORT")
    db_user: str = Field(default="postgres", alias="POSTGRES_USER")
    db_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    db_name: str = Field(default="mobility_bj", alias="POSTGRES_DB")

    @cached_property
    def spatial_params(self) -> SpatialParams:
        """Carga y valida los parámetros espaciales desde config/spatial_params.yaml."""
        yaml_path = self.config_dir / "spatial_params.yaml"
        if not yaml_path.exists():
            return SpatialParams()
        with open(yaml_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        return SpatialParams.model_validate(raw)

    @property
    def database_url(self) -> str:
        """Retorna la URI de conexión para SQLAlchemy / GeoAlchemy."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


settings = AppSettings()
