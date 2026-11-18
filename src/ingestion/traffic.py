"""Ingesta y modelado de Tráfico Vial por franja horaria para Benito Juárez.

Combina velocidades históricas oficiales de INFOVIAL (Datos Abiertos CDMX)
con jerarquía vial OSM, ejes troncales conocidos y fricción por siniestralidad
para asignar factores de congestión [AM, Día, PM, Noche] y Nivel de Servicio (LOS).
"""

import json
from pathlib import Path

import networkx as nx
import pandas as pd
import requests

from config.settings import settings
from src.ingestion.schemas import TrafficSummarySchema

INFOVIAL_SPEED_URL = (
    "https://archivo.datos.cdmx.gob.mx/infovial/velocidad/201601_velocidad_limpio.csv"
)

MAJOR_BJ_CORRIDORS = (
    "insurgentes",
    "eje central",
    "lázaro cárdenas",
    "lazaro cardenas",
    "tlalpan",
    "universidad",
    "división del norte",
    "division del norte",
    "revolución",
    "revolucion",
    "patriotismo",
    "viaducto",
    "churubusco",
    "félix cuevas",
    "felix cuevas",
    "xola",
    "eje 5",
    "eje 6",
    "eje 7",
    "eje 8",
    "cuauhtémoc",
    "cuauhtemoc",
)


def _load_infovial_sample_count() -> tuple[int, float]:
    """Descarga y resume velocidades medias de INFOVIAL CDMX (si está disponible)."""
    dest = settings.raw_data_dir / "cdmx" / "infovial_velocidad.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not (dest.exists() and dest.stat().st_size > 1000):
        try:
            resp = requests.get(INFOVIAL_SPEED_URL, timeout=25, stream=True)
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        except Exception:
            return 0, 24.0

    try:
        df = pd.read_csv(dest, usecols=["vialidad", "velocidad"], low_memory=False)
        df["velocidad"] = pd.to_numeric(df["velocidad"], errors="coerce")
        df = df.dropna(subset=["velocidad"])
        df = df[(df["velocidad"] > 2.0) & (df["velocidad"] < 110.0)]
        if df.empty:
            return 0, 24.0
        return len(df), float(df["velocidad"].median())
    except Exception:
        return 0, 24.0


def _classify_los(factor: float) -> str:
    """Clasifica el Nivel de Servicio (LOS) según factor de congestión."""
    if factor <= 1.2:
        return "A"
    if factor <= 1.5:
        return "B"
    if factor <= 1.9:
        return "C"
    if factor <= 2.4:
        return "D"
    if factor <= 2.9:
        return "E"
    return "F"


def enrich_graph_with_traffic(
    G: nx.MultiDiGraph,
    output_summary: Path | None = None,
    use_infovial: bool = True,
) -> tuple[nx.MultiDiGraph, TrafficSummarySchema]:
    """Asigna factores de congestión por franja [AM, Día, PM, Noche] y LOS a cada arista."""
    if output_summary is None:
        output_summary = settings.processed_data_dir / "traffic_summary.json"

    infovial_count, infovial_med_kph = _load_infovial_sample_count() if use_infovial else (0, 24.0)
    # Factor de escala arterial derivado de la mediana INFOVIAL respecto a 50 km/h nominal
    arterial_scale = max(1.15, min(2.2, 50.0 / max(15.0, infovial_med_kph)))

    sums = {"am": 0.0, "dia": 0.0, "pm": 0.0, "noche": 0.0}
    los_dist: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
    edge_count = 0

    for _, _, d in G.edges(data=True):
        edge_count += 1
        hw = str(d.get("highway", "residential")).lower()
        name = str(d.get("name", "")).lower()
        risk = float(d.get("risk_score", 0.0))
        is_major_corridor = any(c in name for c in MAJOR_BJ_CORRIDORS)

        if any(k in hw for k in ("motorway", "trunk", "primary")) or is_major_corridor:
            base_am = 1.65 * (arterial_scale / 1.5)
            base_dia = 1.38 * (arterial_scale / 1.5)
            base_pm = 1.85 * (arterial_scale / 1.5)
            base_noche = 1.08
        elif any(k in hw for k in ("secondary", "tertiary")):
            base_am = 1.38
            base_dia = 1.22
            base_pm = 1.52
            base_noche = 1.05
        else:
            base_am = 1.12
            base_dia = 1.08
            base_pm = 1.18
            base_noche = 1.02

        # Fricción adicional por historial de accidentes en el tramo
        risk_bump = min(0.85, risk * 0.06)
        f_am = round(min(3.4, base_am + risk_bump * 0.8), 2)
        f_dia = round(min(3.0, base_dia + risk_bump * 0.6), 2)
        f_pm = round(min(3.6, base_pm + risk_bump), 2)
        f_noche = round(min(1.8, base_noche + risk_bump * 0.2), 2)

        d["traffic_am"] = f_am
        d["traffic_dia"] = f_dia
        d["traffic_pm"] = f_pm
        d["traffic_noche"] = f_noche
        los = _classify_los(f_pm)
        d["los_pm"] = los

        sums["am"] += f_am
        sums["dia"] += f_dia
        sums["pm"] += f_pm
        sums["noche"] += f_noche
        los_dist[los] += 1

    mean_by_band = {k: round(v / edge_count, 2) if edge_count > 0 else 1.0 for k, v in sums.items()}
    summary = TrafficSummarySchema(
        total_edges_evaluated=edge_count,
        infovial_records_used=infovial_count,
        mean_factor_by_band=mean_by_band,
        los_distribution_pm=los_dist,
        sources=[
            "INFOVIAL CDMX (Velocidades en Vialidades Primarias)",
            "Calibración horaria por jerarquía OSM y fricción por siniestralidad SSC",
        ],
    )

    output_summary.parent.mkdir(parents=True, exist_ok=True)
    with open(output_summary, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)

    return G, summary


if __name__ == "__main__":
    from src.graph.cleaner import load_road_network
    from src.ingestion.accidents import enrich_graph_with_accident_risk

    graph = load_road_network(ensure_weights=False)
    graph, _ = enrich_graph_with_accident_risk(graph)
    _, res = enrich_graph_with_traffic(graph)
    print(
        f"==> Tráfico calibrado sobre {res.total_edges_evaluated} aristas "
        f"(INFOVIAL={res.infovial_records_used} reg.)"
    )
    print(f"    Factores medios: {res.mean_factor_by_band}")
    print(f"    LOS PM: {res.los_distribution_pm}")
