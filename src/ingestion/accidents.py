"""Ingesta de base de datos real de accidentes viales (SSC/C5 CDMX) en Benito Juárez.

Filtra los últimos 24 meses disponibles dentro del límite territorial de la alcaldía,
calcula pesos de severidad y enriquece las aristas de la LSCC con métricas de riesgo.
"""

import json
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
import requests
from shapely.geometry import LineString, Point

from config.settings import settings
from src.ingestion.boundary import get_benito_juarez_polygon
from src.ingestion.schemas import AccidentHotspotSummary, AccidentsSummarySchema

SSC_HECHOS_TRANSITO_URL = (
    "https://datos.cdmx.gob.mx/dataset/a9afdb1b-80ed-4f6c-a34a-0200211e527e/"
    "resource/0555dd20-d921-4f76-aa8c-1a0689f48bce/download/0555dd20-d921-4f76-aa8c-1a0689f48bce.csv"
)


def _download_accidents_csv(dest: Path, timeout: int = 90) -> Path:
    """Descarga el CSV oficial de hechos de tránsito SSC si no existe en caché."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 10000:
        return dest
    resp = requests.get(SSC_HECHOS_TRANSITO_URL, timeout=timeout, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
    return dest


def ingest_benito_juarez_accidents(
    window_months: int = 24,
    output_parquet: Path | None = None,
    output_summary: Path | None = None,
) -> tuple[gpd.GeoDataFrame, AccidentsSummarySchema]:
    """Ingiere, filtra espacial y temporalmente (24 meses) los accidentes de Benito Juárez."""
    if output_parquet is None:
        output_parquet = settings.processed_data_dir / "accidents_bj.geoparquet"
    if output_summary is None:
        output_summary = settings.processed_data_dir / "accidents_summary.json"

    csv_path = _download_accidents_csv(settings.raw_data_dir / "cdmx" / "hechos_transito_ssc.csv")
    df = pd.read_csv(csv_path, low_memory=False)

    # Normalizar fechas y filtrar últimos N meses disponibles en el dataset
    df["fecha_dt"] = pd.to_datetime(df["fecha_evento"], errors="coerce")
    df = df.dropna(subset=["fecha_dt", "latitud", "longitud"]).copy()
    df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.dropna(subset=["latitud", "longitud"])

    # Rango geográfico razonable de CDMX antes de clipping exacto
    df = df[(df["latitud"].between(19.0, 19.7)) & (df["longitud"].between(-99.4, -98.9))]

    max_date = df["fecha_dt"].max()
    min_cutoff = max_date - pd.DateOffset(months=window_months)
    df = df[df["fecha_dt"] >= min_cutoff].copy()

    # Geometría y recorte espacial estricto al polígono de Benito Juárez (+200m perimetral)
    geometry = [Point(lon, lat) for lon, lat in zip(df["longitud"], df["latitud"])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326").to_crs("EPSG:32614")

    boundary_gdf = get_benito_juarez_polygon(buffer_meters=200.0, use_cache=True)
    bj_poly = boundary_gdf[boundary_gdf["type"] == "buffered_boundary"].geometry.iloc[0]
    gdf_bj = gdf[gdf.geometry.within(bj_poly)].copy()

    # Limpiar y calcular peso de severidad
    for col in ("personas_lesionadas", "personas_fallecidas"):
        gdf_bj[col] = pd.to_numeric(gdf_bj.get(col, 0), errors="coerce").fillna(0).astype(int)

    gdf_bj["severity_weight"] = (
        1.0 + 0.5 * gdf_bj["personas_lesionadas"] + 3.0 * gdf_bj["personas_fallecidas"]
    )
    gdf_bj["fecha_evento"] = gdf_bj["fecha_dt"].dt.strftime("%Y-%m-%d")
    gdf_bj["tipo_evento"] = (
        gdf_bj.get("tipo_evento", "Sin especificar").fillna("Sin especificar").astype(str)
    )
    gdf_bj["colonia"] = gdf_bj.get("colonia", "Sin colonia").fillna("Sin colonia").astype(str)
    gdf_bj["hora_evento"] = gdf_bj.get("hora_evento", "").fillna("").astype(str)
    gdf_bj["folio"] = gdf_bj.get("folio", "").fillna("").astype(str)
    gdf_bj["prioridad"] = gdf_bj.get("prioridad", "").fillna("").astype(str)

    keep_cols = [
        "folio",
        "fecha_evento",
        "hora_evento",
        "tipo_evento",
        "colonia",
        "prioridad",
        "latitud",
        "longitud",
        "personas_lesionadas",
        "personas_fallecidas",
        "severity_weight",
        "geometry",
    ]
    gdf_clean = gpd.GeoDataFrame(gdf_bj[keep_cols], crs="EPSG:32614").reset_index(drop=True)
    output_parquet.parent.mkdir(parents=True, exist_ok=True)
    gdf_clean.to_parquet(output_parquet)

    # Hotspots por colonia
    hotspots: list[AccidentHotspotSummary] = []
    if not gdf_clean.empty:
        grouped = (
            gdf_clean.groupby("colonia", as_index=False)
            .agg(
                accident_count=("folio", "count"),
                injured_total=("personas_lesionadas", "sum"),
                fatalities_total=("personas_fallecidas", "sum"),
                lat=("latitud", "mean"),
                lon=("longitud", "mean"),
            )
            .sort_values("accident_count", ascending=False)
            .head(8)
        )
        for _, row in grouped.iterrows():
            hotspots.append(
                AccidentHotspotSummary(
                    colonia=str(row["colonia"]),
                    lat=round(float(row["lat"]), 6),
                    lon=round(float(row["lon"]), 6),
                    accident_count=int(row["accident_count"]),
                    injured_total=int(row["injured_total"]),
                    fatalities_total=int(row["fatalities_total"]),
                )
            )

    by_type = {
        str(k): int(v) for k, v in gdf_clean["tipo_evento"].value_counts().head(8).to_dict().items()
    }
    summary = AccidentsSummarySchema(
        total_accidents=len(gdf_clean),
        date_min=str(gdf_clean["fecha_evento"].min()) if not gdf_clean.empty else None,
        date_max=str(gdf_clean["fecha_evento"].max()) if not gdf_clean.empty else None,
        window_months=window_months,
        total_injured=int(gdf_clean["personas_lesionadas"].sum()) if not gdf_clean.empty else 0,
        total_fatalities=int(gdf_clean["personas_fallecidas"].sum()) if not gdf_clean.empty else 0,
        by_type=by_type,
        top_hotspots=hotspots,
        crs_projected="EPSG:32614",
        metadata={"source": "SSC / Datos Abiertos CDMX (Hechos de Tránsito)"},
    )
    with open(output_summary, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)

    return gdf_clean, summary


def enrich_graph_with_accident_risk(
    G: nx.MultiDiGraph,
    accidents_gdf: gpd.GeoDataFrame | None = None,
    buffer_m: float = 25.0,
    risk_penalty_alpha: float = 0.15,
) -> tuple[nx.MultiDiGraph, int]:
    """Asigna accident_count, risk_score y safe_travel_time_s a cada arista del grafo LSCC."""
    if accidents_gdf is None:
        acc_path = settings.processed_data_dir / "accidents_bj.geoparquet"
        if not acc_path.exists():
            for _, _, d in G.edges(data=True):
                d["accident_count"] = 0
                d["risk_score"] = 0.0
                d["safe_travel_time_s"] = float(d.get("travel_time_s", 10.0))
            return G, 0
        accidents_gdf = gpd.read_parquet(acc_path)

    if accidents_gdf.empty:
        for _, _, d in G.edges(data=True):
            d["accident_count"] = 0
            d["risk_score"] = 0.0
            d["safe_travel_time_s"] = float(d.get("travel_time_s", 10.0))
        return G, 0

    node_xy = {
        n: (float(d.get("x_m", 0.0)), float(d.get("y_m", 0.0))) for n, d in G.nodes(data=True)
    }
    edge_rows = []
    for u, v, k, _ in G.edges(keys=True, data=True):
        if u in node_xy and v in node_xy:
            edge_rows.append(
                {
                    "u": u,
                    "v": v,
                    "k": k,
                    "geometry": LineString([node_xy[u], node_xy[v]]).buffer(buffer_m),
                }
            )

    gdf_edges = gpd.GeoDataFrame(edge_rows, crs="EPSG:32614")
    joined = gpd.sjoin(
        accidents_gdf[["severity_weight", "geometry"]],
        gdf_edges,
        how="inner",
        predicate="within",
    )

    agg = (
        joined.groupby(["u", "v", "k"])
        .agg(acc_count=("severity_weight", "count"), risk_sum=("severity_weight", "sum"))
        .to_dict(orient="index")
    )

    edges_with_accidents = 0
    for u, v, k, d in G.edges(keys=True, data=True):
        stats = agg.get((u, v, k))
        base_time = float(d.get("travel_time_s", 10.0))
        if stats:
            edges_with_accidents += 1
            count = int(stats["acc_count"])
            risk = round(float(stats["risk_sum"]), 2)
        else:
            count = 0
            risk = 0.0
        d["accident_count"] = count
        d["risk_score"] = risk
        d["safe_travel_time_s"] = round(base_time * (1.0 + risk_penalty_alpha * risk), 2)

    return G, edges_with_accidents


if __name__ == "__main__":
    _, res = ingest_benito_juarez_accidents(window_months=24)
    print(
        f"==> Accidentes BJ (24m): {res.total_accidents} eventos "
        f"({res.date_min} a {res.date_max}), lesionados={res.total_injured}, fallecidos={res.total_fatalities}"
    )
