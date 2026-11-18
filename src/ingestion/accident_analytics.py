"""Analítica espacial (DBSCAN) y temporal (24h) de accidentes viales en Benito Juárez.

Implementa DBSCAN determinista sobre coordenadas métricas EPSG:32614 mediante
cKDTree de SciPy para identificar cruceros críticos reales y perfiles horarios.
"""

import json
from collections import deque
from pathlib import Path

import geopandas as gpd
import numpy as np
from scipy.spatial import cKDTree

from config.settings import settings
from src.ingestion.schemas import AccidentAnalyticsSchema, AccidentClusterSchema


def _dbscan_kdtree(coords: np.ndarray, eps: float, min_samples: int) -> np.ndarray:
    """Ejecuta DBSCAN determinista sobre puntos 2D usando cKDTree.

    Retorna arreglo de etiquetas (-1 = ruido, >= 0 = id de cluster).
    """
    n = len(coords)
    labels = np.full(n, -1, dtype=int)
    if n == 0:
        return labels

    tree = cKDTree(coords)
    neighbors_list = tree.query_ball_point(coords, r=eps)
    visited = np.zeros(n, dtype=bool)
    cluster_id = 0

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        nbrs = neighbors_list[i]
        if len(nbrs) < min_samples:
            continue

        labels[i] = cluster_id
        queue: deque[int] = deque(nbrs)
        in_queue = set(nbrs)

        while queue:
            j = queue.popleft()
            if not visited[j]:
                visited[j] = True
                j_nbrs = neighbors_list[j]
                if len(j_nbrs) >= min_samples:
                    for k in j_nbrs:
                        if k not in in_queue:
                            queue.append(k)
                            in_queue.add(k)
            if labels[j] == -1:
                labels[j] = cluster_id

        cluster_id += 1

    return labels


def classify_time_band(hour: int) -> str:
    """Clasifica una hora (0-23) en franja de movilidad urbana."""
    if 6 <= hour <= 9:
        return "pico_am"
    if 10 <= hour <= 16:
        return "dia"
    if 17 <= hour <= 20:
        return "pico_pm"
    return "noche"


def run_accident_analytics(
    accidents_gdf: gpd.GeoDataFrame | None = None,
    eps_meters: float = 120.0,
    min_samples: int = 15,
    output_json: Path | None = None,
) -> AccidentAnalyticsSchema:
    """Ejecuta clustering DBSCAN y perfil horario 24h sobre accidentes de Benito Juárez."""
    if accidents_gdf is None:
        acc_path = settings.processed_data_dir / "accidents_bj.geoparquet"
        if not acc_path.exists():
            return AccidentAnalyticsSchema()
        accidents_gdf = gpd.read_parquet(acc_path)

    if output_json is None:
        output_json = settings.processed_data_dir / "accident_analytics.json"

    if accidents_gdf.empty:
        return AccidentAnalyticsSchema()

    gdf_utm = accidents_gdf.to_crs("EPSG:32614")
    coords = np.column_stack([gdf_utm.geometry.x.to_numpy(), gdf_utm.geometry.y.to_numpy()])
    labels = _dbscan_kdtree(coords, eps=eps_meters, min_samples=min_samples)

    # Extraer hora numérica (0-23)
    hours: list[int] = []
    for val in gdf_utm.get("hora_evento", ["12:00"] * len(gdf_utm)):
        try:
            h = int(str(val).split(":")[0])
            hours.append(h if 0 <= h <= 23 else 12)
        except (ValueError, IndexError):
            hours.append(12)

    gdf_work = gdf_utm.copy()
    gdf_work["cluster_id"] = labels
    gdf_work["hour"] = hours

    # Perfil horario 24h y por franja
    hourly_counts = [0] * 24
    band_counts = {"pico_am": 0, "dia": 0, "pico_pm": 0, "noche": 0}
    for h in hours:
        hourly_counts[h] += 1
        band_counts[classify_time_band(h)] += 1

    # Construir resumen por cluster (excluyendo ruido -1)
    clusters: list[AccidentClusterSchema] = []
    unique_cids = sorted(int(c) for c in set(labels) if c >= 0)
    for cid in unique_cids:
        sub = gdf_work[gdf_work["cluster_id"] == cid]
        sub_coords = coords[labels == cid]
        cx, cy = sub_coords.mean(axis=0)
        dists = np.hypot(sub_coords[:, 0] - cx, sub_coords[:, 1] - cy)
        radius_m = max(40.0, float(np.percentile(dists, 90)))

        top_colonia = (
            str(sub["colonia"].mode().iloc[0]) if not sub["colonia"].empty else "Benito Juárez"
        )
        dom_type = (
            str(sub["tipo_evento"].mode().iloc[0])
            if not sub["tipo_evento"].empty
            else "Hecho de tránsito"
        )
        peak_h = int(sub["hour"].mode().iloc[0]) if not sub["hour"].empty else 12

        clusters.append(
            AccidentClusterSchema(
                cluster_id=cid,
                label=top_colonia.title() if top_colonia.isupper() else top_colonia,
                lat=round(float(sub["latitud"].mean()), 6),
                lon=round(float(sub["longitud"].mean()), 6),
                radius_m=round(radius_m, 1),
                accident_count=len(sub),
                injured_total=int(sub["personas_lesionadas"].sum()),
                fatalities_total=int(sub["personas_fallecidas"].sum()),
                severity_sum=round(float(sub["severity_weight"].sum()), 1),
                dominant_type=dom_type,
                peak_hour=peak_h,
            )
        )

    clusters.sort(key=lambda c: c.severity_sum, reverse=True)
    clusters = clusters[:25]

    analytics = AccidentAnalyticsSchema(
        total_analyzed=len(gdf_work),
        eps_meters=eps_meters,
        min_samples=min_samples,
        cluster_count=len(unique_cids),
        clusters=clusters,
        hourly_counts=hourly_counts,
        band_counts=band_counts,
    )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(analytics.model_dump(), f, indent=2, ensure_ascii=False)

    return analytics


if __name__ == "__main__":
    res = run_accident_analytics()
    print(
        f"==> DBSCAN completado: {res.cluster_count} clusters críticos "
        f"sobre {res.total_analyzed} accidentes (top={len(res.clusters)})"
    )
    print(f"    Franjas horarias: {res.band_counts}")
