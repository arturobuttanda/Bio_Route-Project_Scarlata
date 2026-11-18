"""Pruebas unitarias para la exportación geoespacial multi-formato (Fase 5)."""

import json
from pathlib import Path

import geopandas as gpd
import pyogrio

from src.export.qgis_styler import generate_pareto_routes_qml, generate_road_network_qml
from src.export.schemas import ExportSummarySchema
from src.export.spatial_export import export_spatial_layers


def test_qgis_styles_generation(tmp_path: Path):
    """Verifica que los estilos .qml se generen con XML válido."""
    road_qml = generate_road_network_qml(tmp_path / "road.qml")
    pareto_qml = generate_pareto_routes_qml(tmp_path / "pareto.qml")

    assert road_qml.exists()
    assert pareto_qml.exists()

    road_txt = road_qml.read_text(encoding="utf-8")
    assert "<qgis" in road_txt
    assert "graduatedSymbol" in road_txt
    assert "speed_kph" in road_txt

    pareto_txt = pareto_qml.read_text(encoding="utf-8")
    assert "<qgis" in pareto_txt
    assert "travel_time_s" in pareto_txt


def test_spatial_export_execution(tmp_path: Path):
    """Verifica la exportación a GPKG, GeoParquet, GeoJSON y JSON summary."""
    gpkg_file = tmp_path / "test_mobility.gpkg"
    geoparquet_file = tmp_path / "test_analytics.geoparquet"
    geojson_file = tmp_path / "test_web.geojson"
    summary_file = tmp_path / "test_summary.json"

    summary = export_spatial_layers(
        gpkg_path=gpkg_file,
        geoparquet_path=geoparquet_file,
        geojson_path=geojson_file,
        summary_path=summary_file,
    )

    # Validar Schema
    assert isinstance(summary, ExportSummarySchema)
    assert summary.total_features > 0
    assert len(summary.layers) >= 6

    # 1. Inspeccionar capas en GPKG con pyogrio
    layers = pyogrio.list_layers(gpkg_file)
    layer_names = [lyr[0] for lyr in layers]
    expected_layers = [
        "boundary_bj",
        "road_network",
        "transit_stops",
        "baseline_routes",
        "pareto_optimal_routes",
        "contingency_chokepoints",
    ]
    for el in expected_layers:
        assert el in layer_names

    # Validar CRS de una capa
    gdf_stops = gpd.read_file(gpkg_file, layer="transit_stops", engine="pyogrio")
    assert gdf_stops.crs.to_string() == "EPSG:32614"
    assert len(gdf_stops) >= 30

    # 2. Inspeccionar GeoParquet
    assert geoparquet_file.exists()
    gdf_parquet = gpd.read_parquet(geoparquet_file)
    assert not gdf_parquet.empty
    assert "route_type" in gdf_parquet.columns
    assert gdf_parquet.crs.to_string() == "EPSG:32614"

    # 3. Inspeccionar GeoJSON
    assert geojson_file.exists()
    gdf_json = gpd.read_file(geojson_file)
    assert not gdf_json.empty
    assert gdf_json.crs.to_string() == "EPSG:4326"

    # 4. Inspeccionar JSON Summary
    assert summary_file.exists()
    with open(summary_file, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["total_features"] == summary.total_features


def test_spa_dashboard_generation(tmp_path: Path):
    """Verifica que el generador de la SPA interactiva construya el archivo HTML autocontenido."""
    from src.export.spa_builder import build_spa_dashboard

    out_html = tmp_path / "test_spa.html"
    res = build_spa_dashboard(output_html=out_html)

    assert res.exists()
    assert res.stat().st_size > 10000
    html_text = res.read_text(encoding="utf-8")
    assert "Benito Juárez Mobility Digital Twin" in html_text
    assert "mask_geojson" in html_text
    assert "L.tileLayer" in html_text
    assert "pareto_solutions" in html_text
