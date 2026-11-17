"""Pipeline de ejecución de la Fase 4: Simulación de Contingencias y Resiliencia."""

from pathlib import Path

import pandas as pd

from config.settings import settings
from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.graph.cleaner import load_road_network
from src.simulation.engine import run_comparative_resilience_simulation


def run_simulation_pipeline() -> tuple[Path, Path]:
    """Ejecuta la suite de simulación de contingencias sobre Benito Juárez."""
    graph_path = settings.processed_data_dir / "road_network_lscc.graphml"
    print(f"[1/4] Cargando grafo vial LSCC desde {graph_path}...")
    G = load_road_network(graph_path)

    print("[2/4] Cargando POIs estratégicos...")
    pois = load_pois_with_metric_coords()
    pois = snap_pois_to_network(pois, G)

    print("[3/4] Cargando rutas de Baseline (Fase 2) y Pareto NSGA-II (Fase 3)...")
    base_file = settings.processed_data_dir / "baseline_od_routes.parquet"
    pareto_file = settings.outputs_dir / "pareto_routes.parquet"

    baseline_df = pd.read_parquet(base_file)
    pareto_df = pd.read_parquet(pareto_file)

    # Filtrar conjunto manejable para la evaluación
    baseline_sample = baseline_df.head(25).to_dict(orient="records")
    pareto_sample = pareto_df[pareto_df["solution_index"] == 0].to_dict(orient="records")

    print("[4/4] Inyectando contingencias (Cierre Eje Central, Congestión C5, Colapso Zapata)...")
    json_path = settings.outputs_dir / "resilience_metrics.json"
    parquet_path = settings.outputs_dir / "contingency_scenarios_results.parquet"

    summary = run_comparative_resilience_simulation(
        G=G,
        pois=pois,
        baseline_routes=baseline_sample,
        pareto_routes=pareto_sample,
        output_json_path=json_path,
        output_parquet_path=parquet_path,
    )

    print(f"==> Métricas de resiliencia guardadas en: {json_path}")
    print(f"==> Trazas detalladas de desvío en: {parquet_path}")
    print(f"    Escenarios evaluados: {summary.scenarios_evaluated}")
    print(
        f"    Latencia media de recálculo: {summary.mean_rerouting_duration_ms:.2f} ms (SLA < 50ms)"
    )
    print(f"    Robustez Baseline: {summary.baseline_global_robustness:.4f}")
    print(
        f"    Robustez Pareto:   {summary.pareto_global_robustness:.4f} (+{summary.resilience_gain_percent:.1f}%)"
    )

    return json_path, parquet_path


if __name__ == "__main__":
    run_simulation_pipeline()
