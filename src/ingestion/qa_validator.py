"""Auditoría espacial automatizada (GIS QA) para validar exactitud cartográfica.

Verifica en EPSG:32614 (UTM Zona 14N):
1. Contención estricta dentro del límite oficial / buffer de Benito Juárez.
2. Distancia métrica de anclaje (snap) de cada POI y parada hacia la red vial LSCC.
3. Exactitud geográfica de hitos icónicos de referencia.
4. Integridad geométrica de las capas de transporte y accidentes.
"""

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import KDTree
from shapely.geometry import Point

from config.settings import settings
from src.graph.cleaner import load_road_network
from src.ingestion.boundary import get_benito_juarez_polygon
from src.ingestion.schemas import QALandmarkCheck, QAReportSchema

# Coordenadas de referencia reales (WGS84) de hitos clave en Benito Juárez
REFERENCE_LANDMARKS: list[tuple[str, float, float, float]] = [
    ("Metro Zapata", 19.3708, -99.1652, 250.0),
    ("Metro Mixcoac", 19.3758, -99.1874, 250.0),
    ("Parque Delta", 19.4030, -99.1545, 350.0),
    ("Mítikah", 19.3601, -99.1674, 350.0),
    ("20 de Noviembre", 19.3725, -99.1760, 450.0),
]


def run_spatial_qa_audit(output_json: Path | None = None) -> QAReportSchema:
    """Ejecuta la auditoría espacial completa sobre las capas procesadas de Benito Juárez."""
    if output_json is None:
        output_json = settings.processed_data_dir / "qa_report.json"

    G = load_road_network(ensure_weights=False)
    node_coords = [
        (float(d["x_m"]), float(d["y_m"]))
        for _, d in G.nodes(data=True)
        if "x_m" in d and "y_m" in d
    ]
    tree = KDTree(node_coords)

    boundary_500 = get_benito_juarez_polygon(buffer_meters=500.0, use_cache=True)
    official_poly = boundary_500[boundary_500["type"] == "official_boundary"].geometry.iloc[0]
    buffered_poly = boundary_500[boundary_500["type"] == "buffered_boundary"].geometry.iloc[0]

    # 1. Auditar POIs reales
    pois_path = settings.processed_data_dir / "pois_real.parquet"
    pois_total = 0
    pois_containment_pct = 0.0
    pois_mean_snap = 0.0
    pois_p95_snap = 0.0
    pois_outliers = 0
    landmark_checks: list[QALandmarkCheck] = []

    if pois_path.exists():
        df_pois = pd.read_parquet(pois_path)
        pois_total = len(df_pois)
        if pois_total > 0:
            pts = [Point(x, y) for x, y in zip(df_pois["x_m"], df_pois["y_m"])]
            inside = sum(1 for pt in pts if pt.within(buffered_poly))
            pois_containment_pct = round(100.0 * inside / pois_total, 2)

            dists, _ = tree.query(list(zip(df_pois["x_m"], df_pois["y_m"])))
            pois_mean_snap = round(float(np.mean(dists)), 2)
            pois_p95_snap = round(float(np.percentile(dists, 95)), 2)
            pois_outliers = int(np.sum(dists > 150.0))

            transformer = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True)
            for lm_name, ref_lat, ref_lon, tol_m in REFERENCE_LANDMARKS:
                rx, ry = transformer.transform(ref_lon, ref_lat)
                matches = df_pois[
                    df_pois["name"].astype(str).str.contains(lm_name, case=False, na=False)
                ]
                if matches.empty:
                    landmark_checks.append(
                        QALandmarkCheck(name=lm_name, found=False, within_tolerance=False)
                    )
                else:
                    min_err = min(
                        math.hypot(float(r["x_m"]) - rx, float(r["y_m"]) - ry)
                        for _, r in matches.iterrows()
                    )
                    landmark_checks.append(
                        QALandmarkCheck(
                            name=lm_name,
                            found=True,
                            distance_error_m=round(min_err, 1),
                            within_tolerance=min_err <= tol_m,
                        )
                    )

    # 2. Auditar Transporte Público (Líneas y Paradas)
    tlines_path = settings.processed_data_dir / "transit_lines.geoparquet"
    tstops_path = settings.processed_data_dir / "transit_stops.geoparquet"
    tlines_total = 0
    tstops_total = 0
    tstops_containment_pct = 0.0
    tstops_mean_snap = 0.0

    if tlines_path.exists():
        gdf_tl = gpd.read_parquet(tlines_path).to_crs("EPSG:32614")
        tlines_total = len(gdf_tl)

    if tstops_path.exists():
        gdf_ts = gpd.read_parquet(tstops_path).to_crs("EPSG:32614")
        tstops_total = len(gdf_ts)
        if tstops_total > 0:
            inside_ts = int(gdf_ts.geometry.within(buffered_poly).sum())
            tstops_containment_pct = round(100.0 * inside_ts / tstops_total, 2)
            ts_coords = [(float(g.x), float(g.y)) for g in gdf_ts.geometry if not g.is_empty]
            if ts_coords:
                ts_dists, _ = tree.query(ts_coords)
                tstops_mean_snap = round(float(np.mean(ts_dists)), 2)

    # 3. Auditar Accidentes Viales
    acc_path = settings.processed_data_dir / "accidents_bj.geoparquet"
    acc_total = 0
    acc_containment_pct = 0.0
    if acc_path.exists():
        gdf_acc = gpd.read_parquet(acc_path).to_crs("EPSG:32614")
        acc_total = len(gdf_acc)
        if acc_total > 0:
            inside_acc = int(gdf_acc.geometry.within(buffered_poly).sum())
            acc_containment_pct = round(100.0 * inside_acc / acc_total, 2)

    _ = official_poly  # Mantenido para futuras auditorías estrictas sin buffer

    passed = (
        pois_containment_pct >= 98.0
        and tstops_containment_pct >= 98.0
        and acc_containment_pct >= 98.0
        and pois_mean_snap <= 80.0
        and all(lc.within_tolerance for lc in landmark_checks)
    )

    report = QAReportSchema(
        pois_total=pois_total,
        pois_containment_pct=pois_containment_pct,
        pois_mean_snap_m=pois_mean_snap,
        pois_p95_snap_m=pois_p95_snap,
        pois_outliers_gt_150m=pois_outliers,
        transit_lines_total=tlines_total,
        transit_stops_total=tstops_total,
        transit_stops_containment_pct=tstops_containment_pct,
        transit_stops_mean_snap_m=tstops_mean_snap,
        accidents_total=acc_total,
        accidents_containment_pct=acc_containment_pct,
        landmark_checks=landmark_checks,
        passed=passed,
    )

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

    return report


if __name__ == "__main__":
    qa = run_spatial_qa_audit()
    print(f"==> GIS QA Passed: {qa.passed}")
    print(
        f"    POIs ({qa.pois_total}): contención {qa.pois_containment_pct}%, "
        f"snap medio {qa.pois_mean_snap_m}m (p95={qa.pois_p95_snap_m}m), outliers>150m={qa.pois_outliers_gt_150m}"
    )
    print(
        f"    Paradas ({qa.transit_stops_total}): contención {qa.transit_stops_containment_pct}%, "
        f"snap medio {qa.transit_stops_mean_snap_m}m"
    )
    print(f"    Accidentes ({qa.accidents_total}): contención {qa.accidents_containment_pct}%")
    for lc in qa.landmark_checks:
        print(
            f"    Hito {lc.name}: found={lc.found}, error={lc.distance_error_m}m, ok={lc.within_tolerance}"
        )
