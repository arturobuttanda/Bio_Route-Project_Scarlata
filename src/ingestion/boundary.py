"""Módulo para la adquisición y delimitación espacial de la alcaldía Benito Juárez.

Aplica un buffer perimetral métrico de 500m en EPSG:32614 para evitar cortes
artificiales en avenidas y ejes viales perimetrales (Viaducto, Churubusco, etc.).
"""

from pathlib import Path

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Polygon

from config.settings import settings

DEFAULT_BJ_BBOX = {
    "south": 19.352,
    "north": 19.412,
    "west": -99.195,
    "east": -99.125,
}


def get_benito_juarez_polygon(buffer_meters: float = 500.0) -> gpd.GeoDataFrame:
    """Obtiene el polígono oficial de Benito Juárez con buffer métrico de contención.

    Args:
        buffer_meters: Distancia métrica en metros para expandir el boundary.

    Returns:
        GeoDataFrame con dos filas: el polígono oficial y el polígono con buffer.
    """
    try:
        # Intentar geocodificación oficial en OSM
        gdf = ox.geocode_to_gdf("Benito Juárez, Ciudad de México, Mexico")
        if gdf.empty:
            raise ValueError("No se obtuvieron geometrías de OSMnx.")
    except Exception as err:
        # Fallback determinista basado en el bounding box oficial si la API de OSM no responde
        bbox = DEFAULT_BJ_BBOX
        geom = Polygon(
            [
                (bbox["west"], bbox["south"]),
                (bbox["east"], bbox["south"]),
                (bbox["east"], bbox["north"]),
                (bbox["west"], bbox["north"]),
                (bbox["west"], bbox["south"]),
            ]
        )
        gdf = gpd.GeoDataFrame(
            [{"name": "Benito Juárez", "fallback": True, "error": str(err)}],
            geometry=[geom],
            crs="EPSG:4326",
        )

    # Asegurar proyección WGS84 inicial
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")

    # Reproyectar a UTM Zona 14N para aplicar buffer métrico exacto
    gdf_utm = gdf.to_crs("EPSG:32614")
    buffered_geom = gdf_utm.geometry.iloc[0].buffer(buffer_meters)

    # Crear GeoDataFrame resultante con ambas geometrías
    result = gpd.GeoDataFrame(
        [
            {
                "type": "official_boundary",
                "buffer_meters": 0.0,
                "geometry": gdf_utm.geometry.iloc[0],
            },
            {
                "type": "buffered_boundary",
                "buffer_meters": buffer_meters,
                "geometry": buffered_geom,
            },
        ],
        crs="EPSG:32614",
    )

    return result


def save_boundary(gdf: gpd.GeoDataFrame, output_path: Path | None = None) -> Path:
    """Guarda el límite oficial y con buffer en formato GeoParquet."""
    if output_path is None:
        output_path = settings.processed_data_dir / "benito_juarez_boundary.parquet"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(output_path)
    return output_path


if __name__ == "__main__":
    boundary_gdf = get_benito_juarez_polygon(buffer_meters=500.0)
    saved = save_boundary(boundary_gdf)
    print(f"Boundary guardado en: {saved}")
