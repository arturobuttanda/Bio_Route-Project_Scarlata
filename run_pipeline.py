"""Orquestador End-to-End del Sistema GeoAI de Movilidad y Rutas Óptimas en Benito Juárez.

Ejecuta el ciclo de vida completo:
- Fase 1: Ingesta de límites oficiales y construcción del grafo vial LSCC con OSMnx/Fallback.
- Fase 2: Snapping de POIs, calibración de matriz gravitatoria y ruteo baseline A*.
- Fase 3: Optimización multiobjetivo bioinspirada NSGA-II (tiempo, solapamiento, cobertura).
- Fase 4: Simulación de contingencias dinámicas C5 (cierres viales, congestión, fallas intermodales).
- Fase 5: Exportación GIS multi-formato (OGC GeoPackage, GeoParquet columnar, Web GeoJSON, QGIS QML).
- Dashboard: Compilación de la Single Page Application (SPA) interactiva autocontenida.
"""

import argparse
import json
import time

from config.settings import settings
from src.demand.pipeline import run_demand_and_baseline_pipeline
from src.export.spa_builder import build_spa_dashboard
from src.export.spatial_export import export_spatial_layers
from src.graph.builder import build_road_network
from src.optimization.pipeline import run_optimization_pipeline
from src.simulation.pipeline import run_simulation_pipeline


def run_full_pipeline(
    skip_osm: bool = False,
    pop_size: int = 20,
    generations: int = 15,
    seed: int = 42,
) -> dict:
    """Ejecuta de manera secuencial y determinista todas las fases del proyecto."""
    start_time = time.time()
    print("=" * 80)
    print("   SISTEMA GEOESPACIAL DE SIMULACIÓN Y OPTIMIZACIÓN BIOINSPIRADA")
    print("           ALCALDÍA BENITO JUÁREZ (CIUDAD DE MÉXICO)")
    print("=" * 80)

    # -------------------------------------------------------------
    # FASE 1: Ingesta y Topología Vial
    # -------------------------------------------------------------
    graph_path = settings.processed_data_dir / "road_network_lscc.graphml"
    if skip_osm and graph_path.exists():
        print(
            f"\n[FASE 1] Omitiendo descarga OSM (--skip-osm). Usando red existente en {graph_path}"
        )
    else:
        print(
            "\n[FASE 1] Ingesta de límites y construcción de topología fuertemente conexa (LSCC)..."
        )
        build_road_network(buffer_meters=500.0)

    # -------------------------------------------------------------
    # FASE 2: Demanda y Ruteo Baseline
    # -------------------------------------------------------------
    print("\n[FASE 2] Modelado de demanda gravitatoria y ruteo determinista A* (Línea Base)...")
    run_demand_and_baseline_pipeline(graph_path=graph_path, max_od_pairs=150)

    # -------------------------------------------------------------
    # FASE 3: Optimización Bioinspirada NSGA-II
    # -------------------------------------------------------------
    print("\n[FASE 3] Ejecutando algoritmo genético multiobjetivo NSGA-II...")
    run_optimization_pipeline(
        pop_size=pop_size,
        generations=generations,
        max_od_pairs=15,
        seed=seed,
    )

    # -------------------------------------------------------------
    # FASE 4: Simulación de Contingencias y Resiliencia
    # -------------------------------------------------------------
    print("\n[FASE 4] Simulando escenarios de contingencia urbana C5 y re-ruteo reactivo...")
    run_simulation_pipeline()

    # -------------------------------------------------------------
    # FASE 5: Exportación Geoespacial (GeoPackage, GeoParquet, GeoJSON, QGIS)
    # -------------------------------------------------------------
    print("\n[FASE 5] Generando artefactos estándar OGC e interoperabilidad GIS...")
    export_spatial_layers()

    # -------------------------------------------------------------
    # SPA Dashboard: Compilación Web Interactiva
    # -------------------------------------------------------------
    print("\n[SPA] Ensamblando Dashboard Web Geoespacial interactivo...")
    spa_path = build_spa_dashboard()

    total_duration = time.time() - start_time

    # -------------------------------------------------------------
    # REPORTE EJECUTIVO SINTÉTICO (Blind Data Ingestion Contract)
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("                     RESUMEN EJECUTIVO DEL PIPELINE")
    print("=" * 80)

    # Cargar métricas sintéticas compactas
    net_summary_file = settings.processed_data_dir / "network_summary.json"
    base_metrics_file = settings.outputs_dir / "baseline_metrics.json"
    opt_summary_file = settings.outputs_dir / "optimization_summary.json"
    res_metrics_file = settings.outputs_dir / "resilience_metrics.json"
    exp_summary_file = settings.outputs_dir / "export_summary.json"

    if net_summary_file.exists():
        with open(net_summary_file, encoding="utf-8") as f:
            ns = json.load(f)
            print(
                f"• Red Vial LSCC: {ns.get('node_count')} nodos, {ns.get('edge_count')} aristas, {ns.get('total_length_km')} km transitables."
            )

    if base_metrics_file.exists():
        with open(base_metrics_file, encoding="utf-8") as f:
            bm = json.load(f)
            print(
                f"• Línea Base A*: {bm.get('total_od_pairs')} pares OD, tiempo medio {bm.get('mean_travel_time_s')}s."
            )

    if opt_summary_file.exists():
        with open(opt_summary_file, encoding="utf-8") as f:
            os_data = json.load(f)
            print(
                f"• NSGA-II Pareto: {os_data.get('pareto_solutions_count')} soluciones óptimas, tiempo mejorado {os_data.get('best_time_solution_s')}s ({os_data.get('time_delta_percent')}% vs baseline)."
            )
            print(f"  Hipervolumen normalizado: {os_data.get('hypervolume')}")

    if res_metrics_file.exists():
        with open(res_metrics_file, encoding="utf-8") as f:
            rm = json.load(f)
            print(
                f"• Resiliencia C5: Robustez Red {rm.get('pareto_global_robustness')} (+{rm.get('resilience_gain_percent')}% vs baseline), latencia re-ruteo {rm.get('mean_rerouting_duration_ms')}ms."
            )

    if exp_summary_file.exists():
        with open(exp_summary_file, encoding="utf-8") as f:
            es = json.load(f)
            print(
                f"• Capas OGC GeoPackage: {len(es.get('layers', []))} capas, {es.get('total_features')} features."
            )

    print(f"\n==> Dashboard SPA: {spa_path}")
    print(f"==> Duración total del ciclo: {total_duration:.2f} segundos")
    print("=" * 80 + "\n")

    return {
        "status": "success",
        "duration_seconds": total_duration,
        "dashboard_html": str(spa_path),
    }


def main():
    """Punto de entrada de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Orquestador del Sistema GeoAI de Movilidad Benito Juárez"
    )
    parser.add_argument(
        "--skip-osm",
        action="store_true",
        help="Reutiliza el grafo LSCC procesado si ya existe en disco.",
    )
    parser.add_argument(
        "--pop-size",
        type=int,
        default=20,
        help="Tamaño de la población para el algoritmo NSGA-II.",
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=15,
        help="Número de generaciones de evolución multiobjetivo.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla aleatoria determinista.",
    )

    args = parser.parse_args()
    run_full_pipeline(
        skip_osm=args.skip_osm,
        pop_size=args.pop_size,
        generations=args.generations,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
