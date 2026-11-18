"""Pipeline de ejecución de la Fase 3: Optimización Bioinspirada (NSGA-II)."""

from pathlib import Path

from config.settings import settings
from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.demand.od_matrix import generate_od_pairs
from src.graph.cleaner import load_road_network
from src.graph.routing_baseline import compute_baseline_routes
from src.ingestion.accidents import enrich_graph_with_accident_risk
from src.optimization.benchmarks import build_optimization_summary
from src.optimization.fitness import evaluate_individual_fitness
from src.optimization.nsga2 import NSGA2Solver
from src.optimization.schemas import RouteChromosome


def run_optimization_pipeline(
    pop_size: int = 20,
    generations: int = 15,
    max_od_pairs: int = 15,
    seed: int = 42,
) -> tuple[Path, Path]:
    """Ejecuta el ciclo de optimización multiobjetivo bioinspirada sobre Benito Juárez.

    Args:
        pop_size: Tamaño de la población de planes de ruta.
        generations: Número de iteraciones evolutivas.
        max_od_pairs: Pares OD estratégicos a conectar simultáneamente.
        seed: Semilla determinista para reproducibilidad.

    Returns:
        Tupla con las rutas del resumen JSON y el archivo Parquet del frente de Pareto.
    """
    graph_path = settings.processed_data_dir / "road_network_lscc.graphml"
    print(f"[1/4] Cargando grafo vial LSCC desde {graph_path}...")
    G = load_road_network(graph_path)
    G, _ = enrich_graph_with_accident_risk(G)

    print("[2/4] Preparando POIs y matriz de pares estratégicos...")
    pois = load_pois_with_metric_coords()
    pois = snap_pois_to_network(pois, G)

    od_pairs = generate_od_pairs(pois, min_volume_threshold=20.0, max_pairs=max_od_pairs)
    print(f"      {len(od_pairs)} corredores estratégicos seleccionados para optimizar.")

    print(
        f"[3/4] Inicializando motor evolutivo NSGA-II (P={pop_size}, G={generations}, Seed={seed})..."
    )
    solver = NSGA2Solver(
        G=G,
        od_pairs=od_pairs,
        pois=pois,
        population_size=pop_size,
        generations=generations,
        crossover_prob=0.8,
        mutation_prob=0.3,
        seed=seed,
    )

    pareto_front, history = solver.evolve()
    print(
        f"      Evolución culminada: {len(pareto_front)} soluciones no dominadas en el Frente de Pareto."
    )

    print("[4/4] Construyendo benchmark comparativo justo (mismos corredores) contra A*...")
    base_routes, base_summary = compute_baseline_routes(G, od_pairs, algorithm="astar")
    base_chromosomes = [
        RouteChromosome(
            route_id=f"BASE_{i}",
            origin_id=r.origin_id,
            destination_id=r.destination_id,
            node_sequence=r.path,
            length_m=r.length_m,
            travel_time_s=r.travel_time_s,
        )
        for i, r in enumerate(base_routes)
    ]
    od_volumes = {(p.origin_id, p.destination_id): p.trip_volume for p in od_pairs}
    base_fit = evaluate_individual_fitness(G, base_chromosomes, pois, od_volumes)
    baseline_stats = {
        "mean_travel_time_s": base_summary.mean_travel_time_s,
        "baseline_coverage_percent": round(base_fit.f3_coverage_ratio * 100.0, 2),
    }

    json_path = settings.outputs_dir / "optimization_summary.json"
    parquet_path = settings.outputs_dir / "pareto_routes.parquet"

    build_optimization_summary(
        pareto_front=pareto_front,
        history=history,
        baseline_stats=baseline_stats,
        output_json_path=json_path,
        output_parquet_path=parquet_path,
    )

    print(f"==> Resumen de optimización guardado en: {json_path}")
    print(f"==> Rutas del Frente de Pareto guardadas en: {parquet_path}")

    return json_path, parquet_path


if __name__ == "__main__":
    run_optimization_pipeline()
