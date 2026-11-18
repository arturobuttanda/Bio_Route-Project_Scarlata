"""Ingesta real de redes de transporte público de CDMX recortadas a Benito Juárez.

Integra fuentes oficiales de Datos Abiertos CDMX / SEMOVI:
1. GTFS estático CDMX (Metro, Metrobús, RTP, Trolebús).
2. Rutas y corredores de Transporte Público Concesionado (camiones/microbuses).
3. Paradas locales de autobús/camión en OpenStreetMap.
"""

import json
import zipfile
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
import requests
from shapely.geometry import LineString, Point

from config.settings import settings
from src.ingestion.boundary import get_benito_juarez_polygon
from src.ingestion.schemas import TransitMode, TransitSummarySchema

GTFS_CDMX_URL = (
    "https://datos.cdmx.gob.mx/dataset/75538d96-3ade-4bc5-ae7d-d85595e4522d/"
    "resource/32ed1b6b-41cd-49b3-b7f0-b57acb0eb819/download/32ed1b6b-41cd-49b3-b7f0-b57acb0eb819.zip"
)
CONCESIONADO_GEOJSON_URL = (
    "https://datos.cdmx.gob.mx/dataset/015b3314-3c28-425a-9c98-a5da8b303b49/"
    "resource/14c6be6e-d6ee-4342-9e9f-87d61fa168a6/download/14c6be6e-d6ee-4342-9e9f-87d61fa168a6.json"
)


def _download_file(url: str, dest: Path, timeout: int = 60) -> Path:
    """Descarga un archivo remoto si no existe en caché local."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return dest


def _classify_gtfs_mode(agency_id: str, route_type: int, route_name: str) -> TransitMode | None:
    """Clasifica una ruta GTFS en Metro, Metrobús, RTP o Trolebús."""
    ag = agency_id.upper()
    rn = route_name.upper()
    if "STC" in ag or "METRO" in ag and "METROBUS" not in ag and "METROBÚS" not in ag:
        return TransitMode.METRO
    if "MB" in ag or "METROBUS" in ag or "METROBÚS" in rn or route_type == 3 and "LÍNEA" in rn:
        if "METROBUS" in ag or "METROBÚS" in ag or ag == "MB":
            return TransitMode.METROBUS
    if "RTP" in ag or "RTP" in rn:
        return TransitMode.RTP
    if "STE" in ag or "TROLE" in ag or "TROLE" in rn or route_type == 11:
        return TransitMode.TROLEBUS
    if route_type == 1:
        return TransitMode.METRO
    if route_type == 3:
        return TransitMode.RTP
    return None


def _load_gtfs_layers(
    gtfs_zip_path: Path,
    clip_poly_utm: object,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Extrae trazas de líneas y paradas del GTFS CDMX recortadas al área de estudio."""
    with zipfile.ZipFile(gtfs_zip_path, "r") as zf:
        routes = pd.read_csv(zf.open("routes.txt"), dtype=str).fillna("")
        trips = pd.read_csv(zf.open("trips.txt"), dtype=str).fillna("")
        shapes = pd.read_csv(zf.open("shapes.txt"))
        stops = pd.read_csv(zf.open("stops.txt"), dtype=str).fillna("")
        stop_times = pd.read_csv(
            zf.open("stop_times.txt"), usecols=["trip_id", "stop_id"], dtype=str
        )

    # Clasificar rutas
    route_mode: dict[str, TransitMode] = {}
    route_label: dict[str, str] = {}
    for _, r in routes.iterrows():
        rid = str(r.get("route_id", ""))
        agency = str(r.get("agency_id", ""))
        rtype = int(r["route_type"]) if str(r.get("route_type", "")).isdigit() else 3
        name = str(r.get("route_short_name") or r.get("route_long_name") or rid)
        mode = _classify_gtfs_mode(agency, rtype, name)
        if mode is not None:
            route_mode[rid] = mode
            route_label[rid] = name

    # Shapes únicos por ruta (un shape representativo por dirección/ruta)
    trip_shapes = (
        trips[trips["route_id"].isin(route_mode.keys())]
        .dropna(subset=["shape_id"])
        .drop_duplicates(subset=["route_id", "shape_id"])
    )

    shapes = shapes.sort_values(["shape_id", "shape_pt_sequence"])
    shape_groups = shapes.groupby("shape_id")

    line_rows: list[dict[str, object]] = []
    seen_shape_route: set[tuple[str, str]] = set()
    for _, tr in trip_shapes.iterrows():
        rid = str(tr["route_id"])
        sid = str(tr["shape_id"])
        if not sid or (rid, sid) in seen_shape_route or sid not in shape_groups.groups:
            continue
        seen_shape_route.add((rid, sid))
        grp = shape_groups.get_group(sid)
        if len(grp) < 2:
            continue
        coords = list(zip(grp["shape_pt_lon"].astype(float), grp["shape_pt_lat"].astype(float)))
        line_rows.append(
            {
                "route_id": rid,
                "route_name": route_label[rid],
                "mode": route_mode[rid].value,
                "source": "GTFS_CDMX",
                "geometry": LineString(coords),
            }
        )

    gdf_lines = gpd.GeoDataFrame(line_rows, crs="EPSG:4326").to_crs("EPSG:32614")
    gdf_lines = gpd.clip(gdf_lines, clip_poly_utm)
    gdf_lines = gdf_lines[~gdf_lines.geometry.is_empty].copy()

    # Paradas asociadas a rutas clasificadas
    trips_valid = trips[trips["route_id"].isin(route_mode.keys())][["trip_id", "route_id"]]
    st_merged = stop_times.merge(trips_valid, on="trip_id", how="inner").drop_duplicates("stop_id")
    stops_valid = stops.merge(st_merged[["stop_id", "route_id"]], on="stop_id", how="inner")

    stop_rows: list[dict[str, object]] = []
    for _, st in stops_valid.iterrows():
        try:
            lat = float(st["stop_lat"])
            lon = float(st["stop_lon"])
        except ValueError:
            continue
        rid = str(st["route_id"])
        stop_rows.append(
            {
                "stop_id": str(st["stop_id"]),
                "stop_name": str(st.get("stop_name", "")),
                "mode": route_mode[rid].value,
                "route_name": route_label[rid],
                "source": "GTFS_CDMX",
                "geometry": Point(lon, lat),
            }
        )

    gdf_stops = gpd.GeoDataFrame(stop_rows, crs="EPSG:4326").to_crs("EPSG:32614")
    gdf_stops = gdf_stops[gdf_stops.geometry.within(clip_poly_utm)].copy()
    return gdf_lines, gdf_stops


def _load_concesionado_layer(
    geojson_path: Path,
    clip_poly_utm: object,
) -> gpd.GeoDataFrame:
    """Carga rutas de transporte público concesionado (camiones/microbuses) de CDMX."""
    gdf = gpd.read_file(geojson_path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf_utm = gdf.to_crs("EPSG:32614")
    gdf_clip = gpd.clip(gdf_utm, clip_poly_utm)
    gdf_clip = gdf_clip[~gdf_clip.geometry.is_empty].copy()

    name_col = next(
        (c for c in ("ruta", "nombre", "corredor", "name", "ramal", "id") if c in gdf_clip.columns),
        None,
    )
    rows: list[dict[str, object]] = []
    for idx, (_, row) in enumerate(gdf_clip.iterrows()):
        rname = str(row[name_col]) if name_col and pd.notna(row[name_col]) else f"Ruta_{idx + 1}"
        rows.append(
            {
                "route_id": f"CONC_{idx + 1:04d}",
                "route_name": rname,
                "mode": TransitMode.CONCESSIONAIRE.value,
                "source": "SEMOVI_CONCESIONADO",
                "geometry": row.geometry,
            }
        )
    return gpd.GeoDataFrame(rows, crs="EPSG:32614")


def _load_osm_local_bus_stops(clip_poly_4326: object, clip_poly_utm: object) -> gpd.GeoDataFrame:
    """Extrae paradas locales de autobús/camión desde OpenStreetMap."""
    try:
        gdf = ox.features_from_polygon(clip_poly_4326, tags={"highway": "bus_stop"})
    except Exception:
        return gpd.GeoDataFrame(
            columns=["stop_id", "stop_name", "mode", "route_name", "source", "geometry"],
            crs="EPSG:32614",
        )

    if gdf.empty:
        return gpd.GeoDataFrame(
            columns=["stop_id", "stop_name", "mode", "route_name", "source", "geometry"],
            crs="EPSG:32614",
        )

    gdf_utm = gdf.to_crs("EPSG:32614")
    gdf_utm["geometry"] = gdf_utm.geometry.centroid
    gdf_utm = gdf_utm[gdf_utm.geometry.within(clip_poly_utm)]

    rows: list[dict[str, object]] = []
    for idx, (_, row) in enumerate(gdf_utm.iterrows()):
        sname = row.get("name")
        clean_name = (
            str(sname).strip()
            if isinstance(sname, str) and sname.strip()
            else f"Parada Local {idx + 1}"
        )
        rows.append(
            {
                "stop_id": f"OSM_BUS_{idx + 1:04d}",
                "stop_name": clean_name,
                "mode": TransitMode.CONCESSIONAIRE.value,
                "route_name": "Camión / Corredor Local",
                "source": "OSM_BUS_STOP",
                "geometry": row.geometry,
            }
        )
    return gpd.GeoDataFrame(rows, crs="EPSG:32614")


def ingest_real_transit_network(
    lines_out: Path | None = None,
    stops_out: Path | None = None,
    summary_out: Path | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, TransitSummarySchema]:
    """Descarga, recorta y consolida líneas y paradas reales de transporte en Benito Juárez."""
    if lines_out is None:
        lines_out = settings.processed_data_dir / "transit_lines.geoparquet"
    if stops_out is None:
        stops_out = settings.processed_data_dir / "transit_stops.geoparquet"
    if summary_out is None:
        summary_out = settings.processed_data_dir / "transit_summary.json"

    raw_dir = settings.raw_data_dir / "cdmx"
    gtfs_zip = _download_file(GTFS_CDMX_URL, raw_dir / "gtfs_cdmx.zip")
    conc_json = _download_file(CONCESIONADO_GEOJSON_URL, raw_dir / "transporte_concesionado.json")

    boundary_gdf = get_benito_juarez_polygon(buffer_meters=500.0, use_cache=True)
    clip_utm = boundary_gdf[boundary_gdf["type"] == "buffered_boundary"].geometry.iloc[0]
    clip_4326 = (
        boundary_gdf[boundary_gdf["type"] == "buffered_boundary"]
        .to_crs("EPSG:4326")
        .geometry.iloc[0]
    )

    gtfs_lines, gtfs_stops = _load_gtfs_layers(gtfs_zip, clip_utm)
    conc_lines = _load_concesionado_layer(conc_json, clip_utm)
    osm_bus_stops = _load_osm_local_bus_stops(clip_4326, clip_utm)

    all_lines = gpd.GeoDataFrame(
        pd.concat([gtfs_lines, conc_lines], ignore_index=True),
        crs="EPSG:32614",
    )
    all_stops = gpd.GeoDataFrame(
        pd.concat([gtfs_stops, osm_bus_stops], ignore_index=True),
        crs="EPSG:32614",
    )

    lines_out.parent.mkdir(parents=True, exist_ok=True)
    all_lines.to_parquet(lines_out)
    all_stops.to_parquet(stops_out)

    total_km = (
        round(float(all_lines.geometry.length.sum()) / 1000.0, 2) if not all_lines.empty else 0.0
    )
    summary = TransitSummarySchema(
        total_lines=len(all_lines),
        total_stops=len(all_stops),
        lines_by_mode={
            str(k): int(v) for k, v in all_lines["mode"].value_counts().to_dict().items()
        },
        stops_by_mode={
            str(k): int(v) for k, v in all_stops["mode"].value_counts().to_dict().items()
        },
        total_length_km=total_km,
        crs_projected="EPSG:32614",
        sources=[
            "GTFS Estático CDMX (SEMOVI)",
            "Rutas y Corredores Transporte Concesionado CDMX",
            "OpenStreetMap Bus Stops",
        ],
    )
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)

    return all_lines, all_stops, summary


if __name__ == "__main__":
    _, _, res = ingest_real_transit_network()
    print(f"==> Transporte real ingerido: {res.total_lines} trazas, {res.total_stops} paradas")
    print(f"    Líneas por modo: {res.lines_by_mode}")
    print(f"    Paradas por modo: {res.stops_by_mode}")
