"""Pipeline de ejecución para la Fase 2: Demanda y Línea Base de Ruteo."""

from pathlib import Path

from config.settings import settings
from src.demand.generators import load_pois_with_metric_coords, snap_pois_to_network
from src.demand.od_matrix import generate_od_pairs
from src.graph.cleaner import load_road_network
from src.graph.routing_baseline import compute_baseline_routes, save_baseline_artifacts


def run_demand_and_baseline_pipeline(
    graph_path: Path | None = None,
    max_od_pairs: int = 150,
) -> tuple[Path, Path]:
    """Ejecuta el flujo completo de demanda y baseline determinista.

    Args:
        graph_path: Ruta al archivo GraphML de la red vial LSCC.
        max_od_pairs: Límite de pares OD a procesar para el benchmark.

    Returns:
        Tupla con las rutas del archivo Parquet de rutas y el JSON de métricas.
    """
    if graph_path is None:
        graph_path = settings.processed_data_dir / "road_network_lscc.graphml"

    print(f"[1/4] Cargando grafo vial LSCC desde {graph_path}...")
    G = load_road_network(graph_path)

    print("[2/4] Cargando POIs (Metro, Metrobús, colonias) y anclando a la LSCC...")
    pois = load_pois_with_metric_coords()
    pois = snap_pois_to_network(pois, G)
    print(f"      {len(pois)} POIs anclados exitosamente.")

    print("[3/4] Generando pares OD calibrados con modelo gravitatorio...")
    od_pairs = generate_od_pairs(pois, min_volume_threshold=10.0, max_pairs=max_od_pairs)
    print(f"      {len(od_pairs)} pares OD generados.")

    print("[4/4] Ejecutando ruteo determinista A* (caminos mínimos)...")
    routes, summary = compute_baseline_routes(G, od_pairs, algorithm="astar")

    parquet_path, json_path = save_baseline_artifacts(routes, summary)

    print(f"==> Rutas baseline guardadas en: {parquet_path}")
    print(f"==> Resumen de métricas baseline en: {json_path}")
    print(
        f"    Pares alcanzables: {len(routes)} / {len(od_pairs)} (Unreachable: {summary.unreachable_pairs})"
    )
    print(
        f"    Tiempo medio: {summary.mean_travel_time_s:.1f}s | Distancia media: {summary.mean_distance_m:.1f}m"
    )
    print(f"    Horas-pasajero simuladas: {summary.total_passenger_hours:.2f} pax-hrs")

    return parquet_path, json_path


if __name__ == "__main__":
    run_demand_and_baseline_pipeline()
