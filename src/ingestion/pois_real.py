"""Ingesta real de Puntos de Interés (POIs) en Benito Juárez desde Datos Abiertos CDMX.

Descarga y recorta al polígono oficial de Benito Juárez:
1. Hospitales públicos y privados en operación (GeoJSON CDMX).
2. Escuelas públicas y privadas (SHP CDMX).
3. Centros comerciales, plazas comerciales y tiendas de autoservicio (GeoJSON CDMX).
Combina los resultados con estaciones Metro/Metrobús y centroides de colonias.
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from pyproj import Transformer
from shapely.geometry import Point

from config.settings import settings
from src.demand.schemas import POIKind, PointOfInterest
from src.ingestion.boundary import get_benito_juarez_polygon
from src.ingestion.schemas import POISummarySchema

HOSPITALES_GEOJSON_URL = (
    "https://datos.cdmx.gob.mx/dataset/fe9c1fb7-892e-4db0-854b-0b48d4a1291d/"
    "resource/aa9edefd-2b53-4f8c-98ca-76de9d8e10fd/download/aa9edefd-2b53-4f8c-98ca-76de9d8e10fd.json"
)
ESCUELAS_PUBLICAS_CSV_URL = (
    "https://datos.cdmx.gob.mx/dataset/f4be0114-49fd-4a4a-84ab-3d12b54d9435/"
    "resource/2aace691-0dc3-4e80-9564-92d56a9e9022/download/2aace691-0dc3-4e80-9564-92d56a9e9022.csv"
)
ESCUELAS_PRIVADAS_CSV_URL = (
    "https://datos.cdmx.gob.mx/dataset/6ab735f4-a764-449b-8e1e-f527f7fd304d/"
    "resource/72f904fb-3d44-48f4-a376-6aa635d06acc/download/72f904fb-3d44-48f4-a376-6aa635d06acc.csv"
)
PLAZAS_GEOJSON_URL = (
    "https://datos.cdmx.gob.mx/dataset/c995a424-bc67-44d4-a01d-059bb8568589/"
    "resource/a7a06916-8b4f-4b49-b64a-efb714ed2155/download/a7a06916-8b4f-4b49-b64a-efb714ed2155.json"
)

VERIFIED_MAJOR_MALLS: list[dict[str, object]] = [
    {
        "id": "MALL_PARQUE_DELTA",
        "name": "Parque Delta",
        "lat": 19.4030,
        "lon": -99.1545,
        "weight": 5.0,
    },
    {
        "id": "MALL_MITIKAH",
        "name": "Centro Comercial Mítikah",
        "lat": 19.3601,
        "lon": -99.1674,
        "weight": 5.0,
    },
    {
        "id": "MALL_PLAZA_UNIVERSIDAD",
        "name": "Plaza Universidad",
        "lat": 19.3665,
        "lon": -99.1666,
        "weight": 4.2,
    },
    {
        "id": "MALL_GALERIAS_INSURGENTES",
        "name": "Galerías Insurgentes",
        "lat": 19.3712,
        "lon": -99.1782,
        "weight": 4.5,
    },
    {
        "id": "MALL_MANACAR",
        "name": "Torre y Plaza Manacar",
        "lat": 19.3688,
        "lon": -99.1816,
        "weight": 4.0,
    },
    {
        "id": "MALL_METROPOLI_PATRIOTISMO",
        "name": "Metrópoli Patriotismo",
        "lat": 19.3965,
        "lon": -99.1811,
        "weight": 4.0,
    },
    {
        "id": "MALL_PABELLON_DEL_VALLE",
        "name": "Pabellón del Valle",
        "lat": 19.3735,
        "lon": -99.1627,
        "weight": 3.5,
    },
]


def _download_cached(url: str, dest: Path, timeout: int = 45) -> Path:
    """Descarga y cachea un archivo en disco si no existe."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 500:
        return dest
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return dest


def _extract_cdmx_layer(
    file_path: Path,
    poly_utm: object,
    kind: POIKind,
    prefix: str,
    default_weight: float,
    name_candidates: tuple[str, ...],
) -> list[dict[str, object]]:
    """Lee un GeoJSON o ZIP-SHP de CDMX, filtra a Benito Juárez y extrae POIs."""
    try:
        read_target = f"zip://{file_path}" if file_path.suffix == ".zip" else str(file_path)
        gdf = gpd.read_file(read_target)
    except Exception as exc:
        print(f"[Aviso] No se pudo leer {file_path.name}: {exc}")
        return []

    if gdf.empty:
        return []
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf_utm = gdf.to_crs("EPSG:32614")
    gdf_utm["geometry"] = gdf_utm.geometry.centroid
    gdf_bj = gdf_utm[gdf_utm.geometry.within(poly_utm)].copy()
    if gdf_bj.empty:
        return []

    gdf_4326 = gdf_bj.to_crs("EPSG:4326")
    name_col = next((c for c in name_candidates if c in gdf_bj.columns), None)

    records: list[dict[str, object]] = []
    seen_names: set[str] = set()

    for idx in range(len(gdf_bj)):
        row = gdf_bj.iloc[idx]
        pt_utm = row.geometry
        pt_4326 = gdf_4326.iloc[idx].geometry
        if pt_utm is None or pt_utm.is_empty:
            continue

        raw_name = row[name_col] if name_col else None
        clean_name = (
            str(raw_name).strip()
            if pd.notna(raw_name) and str(raw_name).strip()
            else f"{prefix}_{len(records) + 1:03d}"
        )
        if clean_name.lower() in seen_names:
            continue
        seen_names.add(clean_name.lower())

        records.append(
            {
                "id": f"{prefix}_{len(records) + 1:03d}",
                "name": clean_name.title() if clean_name.isupper() else clean_name,
                "kind": kind.value,
                "lon": round(float(pt_4326.x), 6),
                "lat": round(float(pt_4326.y), 6),
                "x_m": round(float(pt_utm.x), 2),
                "y_m": round(float(pt_utm.y), 2),
                "weight": default_weight,
            }
        )

    return records


def _extract_cdmx_csv_pois(
    csv_path: Path,
    poly_utm: object,
    kind: POIKind,
    prefix: str,
    default_weight: float,
) -> list[dict[str, object]]:
    """Lee un CSV de CDMX con columnas nombre, latitud, longitud y filtra a Benito Juárez."""
    df = pd.read_csv(csv_path, low_memory=False)
    df["latitud"] = pd.to_numeric(df.get("latitud"), errors="coerce")
    df["longitud"] = pd.to_numeric(df.get("longitud"), errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"]).copy()
    df = df[(df["latitud"].between(19.0, 19.7)) & (df["longitud"].between(-99.4, -98.9))]
    if df.empty:
        return []

    gdf = gpd.GeoDataFrame(
        df,
        geometry=[Point(lon, lat) for lon, lat in zip(df["longitud"], df["latitud"])],
        crs="EPSG:4326",
    ).to_crs("EPSG:32614")
    gdf_bj = gdf[gdf.geometry.within(poly_utm)].copy()
    if gdf_bj.empty:
        return []

    records: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for _, row in gdf_bj.iterrows():
        raw_name = row.get("nombre")
        clean_name = (
            str(raw_name).strip()
            if pd.notna(raw_name) and str(raw_name).strip()
            else f"{prefix}_{len(records) + 1:03d}"
        )
        if clean_name.lower() in seen_names:
            continue
        seen_names.add(clean_name.lower())
        pt_utm = row.geometry
        records.append(
            {
                "id": f"{prefix}_{len(records) + 1:03d}",
                "name": clean_name.title() if clean_name.isupper() else clean_name,
                "kind": kind.value,
                "lon": round(float(row["longitud"]), 6),
                "lat": round(float(row["latitud"]), 6),
                "x_m": round(float(pt_utm.x), 2),
                "y_m": round(float(pt_utm.y), 2),
                "weight": default_weight,
            }
        )
    return records


def build_real_pois_catalog(
    output_parquet: Path | None = None,
    output_summary: Path | None = None,
) -> tuple[list[PointOfInterest], POISummarySchema]:
    """Extrae y consolida POIs reales de Benito Juárez (hospitales, escuelas, malls y base)."""
    if output_parquet is None:
        output_parquet = settings.processed_data_dir / "pois_real.parquet"
    if output_summary is None:
        output_summary = settings.processed_data_dir / "pois_summary.json"

    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    raw_dir = settings.raw_data_dir / "cdmx"

    boundary_gdf = get_benito_juarez_polygon(buffer_meters=0.0, use_cache=True)
    poly_utm = boundary_gdf[boundary_gdf["type"] == "official_boundary"].geometry.iloc[0]

    # 1. Descargar y extraer capas oficiales CDMX
    hosp_path = _download_cached(HOSPITALES_GEOJSON_URL, raw_dir / "hospitales_zmvm.json")
    esc_pub_path = _download_cached(ESCUELAS_PUBLICAS_CSV_URL, raw_dir / "escuelas_publicas.csv")
    esc_priv_path = _download_cached(ESCUELAS_PRIVADAS_CSV_URL, raw_dir / "escuelas_privadas.csv")
    plazas_path = _download_cached(PLAZAS_GEOJSON_URL, raw_dir / "plazas_comerciales.json")

    hospitals = _extract_cdmx_layer(
        hosp_path,
        poly_utm,
        POIKind.HOSPITAL,
        "HOSP",
        4.2,
        ("nombre", "nom_estab", "hospital", "name", "unidad"),
    )
    schools_pub = _extract_cdmx_csv_pois(esc_pub_path, poly_utm, POIKind.SCHOOL, "ESC_PUB", 3.2)
    schools_priv = _extract_cdmx_csv_pois(esc_priv_path, poly_utm, POIKind.SCHOOL, "ESC_PRIV", 3.0)
    malls_cdmx = _extract_cdmx_layer(
        plazas_path,
        poly_utm,
        POIKind.SHOPPING_MALL,
        "MALL_CDMX",
        4.0,
        ("nombre", "nom_estab", "plaza", "name"),
    )

    # 2. Completar plazas principales verificadas sin duplicar
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
    existing_mall_names = {str(m["name"]).lower() for m in malls_cdmx}
    verified_malls: list[dict[str, object]] = []
    for m in VERIFIED_MAJOR_MALLS:
        m_name = str(m["name"]).lower()
        if any(m_name in ex or ex in m_name for ex in existing_mall_names):
            continue
        lon = float(m["lon"])  # type: ignore[arg-type]
        lat = float(m["lat"])  # type: ignore[arg-type]
        xm, ym = transformer.transform(lon, lat)
        verified_malls.append(
            {
                "id": m["id"],
                "name": m["name"],
                "kind": POIKind.SHOPPING_MALL.value,
                "lon": lon,
                "lat": lat,
                "x_m": round(xm, 2),
                "y_m": round(ym, 2),
                "weight": m["weight"],
            }
        )

    # 3. Combinar con estaciones base de Metro/Metrobús y colonias
    from src.demand.generators import RAW_BENITO_JUAREZ_POIS

    base_records: list[dict[str, object]] = []
    for item in RAW_BENITO_JUAREZ_POIS:
        xm, ym = transformer.transform(float(item["lon"]), float(item["lat"]))
        base_records.append(
            {
                "id": item["id"],
                "name": item["name"],
                "kind": item["kind"].value if hasattr(item["kind"], "value") else str(item["kind"]),
                "lon": float(item["lon"]),
                "lat": float(item["lat"]),
                "x_m": round(xm, 2),
                "y_m": round(ym, 2),
                "weight": float(item.get("weight", 1.0)),
            }
        )

    all_records = (
        base_records + hospitals + schools_pub + schools_priv + malls_cdmx + verified_malls
    )
    df = pd.DataFrame(all_records).drop_duplicates(subset=["id"]).reset_index(drop=True)
    df.to_parquet(output_parquet, index=False)

    counts_by_kind = {str(k): int(v) for k, v in df["kind"].value_counts().to_dict().items()}
    summary = POISummarySchema(
        total_pois=len(df),
        counts_by_kind=counts_by_kind,
        crs_projected="EPSG:32614",
        sources=[
            "Datos Abiertos CDMX (Hospitales ZMVM, Escuelas Públicas/Privadas, Plazas Comerciales)",
            "Catálogo verificado Benito Juárez (Metro, Metrobús, Colonias, Plazas)",
        ],
    )
    with open(output_summary, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)

    pois = [PointOfInterest.model_validate(row) for row in df.to_dict(orient="records")]
    return pois, summary


if __name__ == "__main__":
    _, res = build_real_pois_catalog()
    print(f"==> POIs reales guardados: {res.total_pois} total -> {res.counts_by_kind}")
