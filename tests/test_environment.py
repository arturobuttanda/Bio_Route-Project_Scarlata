"""Verificación básica de entorno, scaffolding e importaciones."""

from config.settings import settings


def test_project_directories_exist():
    """Valida que los directorios principales del proyecto existan."""
    assert settings.base_dir.exists()
    assert settings.raw_data_dir.exists()
    assert settings.processed_data_dir.exists()
    assert settings.outputs_dir.exists()
    assert settings.config_dir.exists()


def test_spatial_params_file_exists():
    """Valida la presencia y carga tipada del archivo de configuración espacial."""
    params_path = settings.config_dir / "spatial_params.yaml"
    assert params_path.exists()
    assert params_path.stat().st_size > 0
    assert settings.spatial_params.spatial.crs_projected == "EPSG:32614"
    assert settings.spatial_params.spatial.boundary.buffer_meters == 500.0
    assert settings.spatial_params.demand.walkable_radius_meters == 400.0


def test_context_rules_exist():
    """Valida que las reglas de agentes y contexto estén presentes."""
    assert (settings.base_dir / "AGENTS.md").exists()
    assert (settings.base_dir / "CONTEXT.md").exists()
    assert (settings.base_dir / ".aiignore").exists()
    assert (settings.base_dir / "requirements.txt").exists()
    assert (settings.base_dir / "requirements.txt").stat().st_size > 0
