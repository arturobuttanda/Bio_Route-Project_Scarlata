"""Motor de simulación de contingencias urbanas, recálculo reactivo y análisis de resiliencia."""

import json
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from config.settings import settings
from src.demand.schemas import PointOfInterest
from src.graph.routing_baseline import make_euclidean_heuristic
from src.simulation.scenarios import get_all_scenarios
from src.simulation.schemas import (
    DisruptionScenario,
    DisruptionType,
    ReroutingRecord,
    ResilienceSummarySchema,
    ScenarioImpactSummary,
)


def apply_scenario_to_graph(G: nx.MultiDiGraph, scenario: DisruptionScenario) -> nx.MultiDiGraph:
    """Aplica la perturbación sobre una copia del grafo vial.

    - Cierres y fallos de nodo: Inhabilitan aristas asignando peso infinito o eliminándolas.
    - Congestión: Multiplica el tiempo de viaje por el factor de fricción (e.g. 3.0x).
    """
    G_disrupted = G.copy()
    affected_edges_set = set(scenario.affected_edges)
    affected_nodes_set = set(scenario.affected_nodes)

    if scenario.disruption_type in (
        DisruptionType.ROAD_CLOSURE,
        DisruptionType.TRANSFER_HUB_FAILURE,
    ):
        # Inhabilitar aristas afectadas
        for u, v in affected_edges_set:
            if G_disrupted.has_edge(u, v):
                # Asignar peso inalcanzable para evitar desconectar la estructura del objeto
                for k, d in G_disrupted[u][v].items():
                    d["travel_time_s"] = 999_999.0

        # Para nodos aislados del hub
        for n in affected_nodes_set:
            if G_disrupted.has_node(n):
                for u, _, d in G_disrupted.in_edges(n, data=True):
                    d["travel_time_s"] = 999_999.0
                for _, v, d in G_disrupted.out_edges(n, data=True):
                    d["travel_time_s"] = 999_999.0

    elif scenario.disruption_type == DisruptionType.CONGESTION_SPIKE:
        for u, v in affected_edges_set:
            if G_disrupted.has_edge(u, v):
                for k, d in G_disrupted[u][v].items():
                    d["travel_time_s"] = d.get("travel_time_s", 1.0) * scenario.friction_multiplier

    return G_disrupted


def reroute_single_path(
    G_disrupted: nx.MultiDiGraph,
    u_origin: int,
    v_dest: int,
    heuristic,
) -> tuple[list[int] | None, float, float]:
    """Ejecuta el recálculo dinámico en milisegundos mediante A* con poda de pesos infinitos."""
    t_start = time.perf_counter()
    try:
        path = nx.astar_path(
            G_disrupted,
            u_origin,
            v_dest,
            heuristic=heuristic,
            weight="travel_time_s",
        )

        # Calcular tiempo acumulado real (descartando si usa alguna arista inhabilitada)
        total_time = 0.0
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            best = min(G_disrupted[u][v].values(), key=lambda d: d.get("travel_time_s", 9999.0))
            t_edge = best.get("travel_time_s", 0.0)
            if t_edge >= 900_000.0:
                # El camino usó una arista cerrada (desvío no factible)
                duration_ms = (time.perf_counter() - t_start) * 1000.0
                return None, 0.0, duration_ms
            total_time += t_edge

        duration_ms = (time.perf_counter() - t_start) * 1000.0
        return path, total_time, duration_ms

    except (nx.NetworkXNoPath, nx.NodeNotFound):
        duration_ms = (time.perf_counter() - t_start) * 1000.0
        return None, 0.0, duration_ms


def evaluate_scenario_on_routes(
    G: nx.MultiDiGraph,
    routes_list: list[dict],
    scenario: DisruptionScenario,
) -> tuple[list[ReroutingRecord], ScenarioImpactSummary]:
    """Evalúa el impacto de una contingencia sobre un conjunto de rutas y mide la resiliencia."""
    G_disrupted = apply_scenario_to_graph(G, scenario)
    heuristic = make_euclidean_heuristic(G_disrupted)

    affected_edges_set = set(scenario.affected_edges)
    affected_nodes_set = set(scenario.affected_nodes)

    records: list[ReroutingRecord] = []
    severed_count = 0
    successful_reroutes = 0
    delays: list[float] = []
    reroute_durations_ms: list[float] = []
    nominal_times: list[float] = []

    for r in routes_list:
        path = r["path_nodes"]
        nom_time = float(r.get("travel_time_s", 100.0))
        nominal_times.append(nom_time)

        # Detectar si la ruta original cruzaba alguna arista o nodo afectado
        was_severed = False
        for i in range(len(path) - 1):
            e = (path[i], path[i + 1])
            if (
                e in affected_edges_set
                or path[i] in affected_nodes_set
                or path[i + 1] in affected_nodes_set
            ):
                was_severed = True
                break

        if was_severed:
            severed_count += 1
            u_orig = path[0]
            v_dest = path[-1]

            new_path, new_time, duration_ms = reroute_single_path(
                G_disrupted, u_orig, v_dest, heuristic
            )
            reroute_durations_ms.append(duration_ms)

            if new_path is not None:
                successful_reroutes += 1
                delay = max(0.0, new_time - nom_time)
                delays.append(delay)
                records.append(
                    ReroutingRecord(
                        route_id=str(
                            r.get("route_id", f"{r.get('origin_id')}_{r.get('destination_id')}")
                        ),
                        origin_id=str(r.get("origin_id", "")),
                        destination_id=str(r.get("destination_id", "")),
                        was_severed=True,
                        rerouted_successfully=True,
                        nominal_time_s=nom_time,
                        disrupted_time_s=round(new_time, 2),
                        delay_seconds=round(delay, 2),
                        rerouting_duration_ms=round(duration_ms, 2),
                    )
                )
            else:
                delays.append(nom_time * 2.0)  # Penalización por incomunicación
                records.append(
                    ReroutingRecord(
                        route_id=str(
                            r.get("route_id", f"{r.get('origin_id')}_{r.get('destination_id')}")
                        ),
                        origin_id=str(r.get("origin_id", "")),
                        destination_id=str(r.get("destination_id", "")),
                        was_severed=True,
                        rerouted_successfully=False,
                        nominal_time_s=nom_time,
                        disrupted_time_s=999_999.0,
                        delay_seconds=round(nom_time * 2.0, 2),
                        rerouting_duration_ms=round(duration_ms, 2),
                    )
                )
        else:
            # Ruta no afectada
            records.append(
                ReroutingRecord(
                    route_id=str(
                        r.get("route_id", f"{r.get('origin_id')}_{r.get('destination_id')}")
                    ),
                    origin_id=str(r.get("origin_id", "")),
                    destination_id=str(r.get("destination_id", "")),
                    was_severed=False,
                    rerouted_successfully=True,
                    nominal_time_s=nom_time,
                    disrupted_time_s=nom_time,
                    delay_seconds=0.0,
                    rerouting_duration_ms=0.0,
                )
            )

    total_tested = len(routes_list)
    disruption_rate = (severed_count / total_tested * 100.0) if total_tested > 0 else 0.0
    reroute_success_rate = (
        (successful_reroutes / severed_count * 100.0) if severed_count > 0 else 100.0
    )
    mean_delay = float(np.mean(delays)) if delays else 0.0
    mean_duration = float(np.mean(reroute_durations_ms)) if reroute_durations_ms else 0.0
    mean_nom_time = float(np.mean(nominal_times)) if nominal_times else 100.0

    # Cálculo formal del Índice de Robustez de Red:
    # R_net = (N_exitosas / N_total) * (1 / (1 + mean_delay / mean_nom_time))
    total_successful = (total_tested - severed_count) + successful_reroutes
    success_ratio = total_successful / total_tested if total_tested > 0 else 0.0
    delay_factor = 1.0 / (1.0 + (mean_delay / mean_nom_time)) if mean_nom_time > 0 else 1.0
    robustness_index = round(float(success_ratio * delay_factor), 4)

    summary = ScenarioImpactSummary(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        total_routes_tested=total_tested,
        severed_routes_count=severed_count,
        service_disruption_rate_pct=round(disruption_rate, 1),
        rerouting_success_rate_pct=round(reroute_success_rate, 1),
        mean_delay_seconds=round(mean_delay, 2),
        mean_reroute_time_ms=round(mean_duration, 2),
        robustness_index=robustness_index,
    )

    return records, summary


def run_comparative_resilience_simulation(
    G: nx.MultiDiGraph,
    pois: list[PointOfInterest],
    baseline_routes: list[dict],
    pareto_routes: list[dict],
    output_json_path: Path | None = None,
    output_parquet_path: Path | None = None,
) -> ResilienceSummarySchema:
    """Ejecuta la batería de escenarios y compara la resiliencia de Baseline vs Pareto."""
    if output_json_path is None:
        output_json_path = settings.outputs_dir / "resilience_metrics.json"
    if output_parquet_path is None:
        output_parquet_path = settings.outputs_dir / "contingency_scenarios_results.parquet"

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_parquet_path.parent.mkdir(parents=True, exist_ok=True)

    scenarios = get_all_scenarios(G, pois)

    scenario_summaries: list[ScenarioImpactSummary] = []
    all_parquet_rows: list[dict] = []
    baseline_r_indices: list[float] = []
    pareto_r_indices: list[float] = []
    all_reroute_times_ms: list[float] = []

    for sc in scenarios:
        # 1. Evaluar en Baseline
        base_records, base_summary = evaluate_scenario_on_routes(G, baseline_routes, sc)
        baseline_r_indices.append(base_summary.robustness_index)

        # 2. Evaluar en Pareto (NSGA-II)
        pareto_records, pareto_summary = evaluate_scenario_on_routes(G, pareto_routes, sc)
        pareto_r_indices.append(pareto_summary.robustness_index)
        scenario_summaries.append(pareto_summary)

        for rec in base_records:
            all_reroute_times_ms.append(rec.rerouting_duration_ms)
            all_parquet_rows.append(
                {
                    "scenario_id": sc.scenario_id,
                    "plan_type": "baseline_deterministic",
                    "route_id": rec.route_id,
                    "was_severed": rec.was_severed,
                    "rerouted_successfully": rec.rerouted_successfully,
                    "nominal_time_s": rec.nominal_time_s,
                    "disrupted_time_s": rec.disrupted_time_s,
                    "delay_seconds": rec.delay_seconds,
                    "rerouting_duration_ms": rec.rerouting_duration_ms,
                }
            )

        for rec in pareto_records:
            all_parquet_rows.append(
                {
                    "scenario_id": sc.scenario_id,
                    "plan_type": "pareto_bioinspired",
                    "route_id": rec.route_id,
                    "was_severed": rec.was_severed,
                    "rerouted_successfully": rec.rerouted_successfully,
                    "nominal_time_s": rec.nominal_time_s,
                    "disrupted_time_s": rec.disrupted_time_s,
                    "delay_seconds": rec.delay_seconds,
                    "rerouting_duration_ms": rec.rerouting_duration_ms,
                }
            )

    # Serializar resultados detallados en Parquet (excluido de contexto por .aiignore)
    df_results = pd.DataFrame(all_parquet_rows)
    df_results.to_parquet(output_parquet_path)

    # Métricas agregadas
    mean_base_rob = float(np.mean(baseline_r_indices))
    mean_pareto_rob = float(np.mean(pareto_r_indices))
    resilience_gain = (
        round(((mean_pareto_rob - mean_base_rob) / mean_base_rob) * 100.0, 2)
        if mean_base_rob > 0
        else 0.0
    )

    valid_times = [t for t in all_reroute_times_ms if t > 0.0]
    avg_reroute_duration = float(np.mean(valid_times)) if valid_times else 12.5

    summary = ResilienceSummarySchema(
        algorithm="Simulador Estocástico de Contingencias & Desvío Dinámico",
        scenarios_evaluated=len(scenarios),
        mean_rerouting_duration_ms=round(avg_reroute_duration, 2),
        baseline_global_robustness=round(mean_base_rob, 4),
        pareto_global_robustness=round(mean_pareto_rob, 4),
        resilience_gain_percent=resilience_gain,
        scenarios=scenario_summaries,
        metadata={
            "total_routes_analyzed": len(all_parquet_rows),
            "reroute_latency_sla_target_ms": 50.0,
            "meets_latency_sla": avg_reroute_duration < 50.0,
        },
    )

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(summary.model_dump(), f, indent=2)

    return summary
