"""Motor evolutivo multiobjetivo NSGA-II (Deb et al., 2002) adaptado a grafos viales."""

import random
from typing import Any

import networkx as nx

from src.demand.schemas import ODPair, PointOfInterest
from src.optimization.fitness import calculate_route_metrics, evaluate_individual_fitness
from src.optimization.operators import (
    crossover_intersection,
    generate_initial_route,
    mutation_k_shortest_path,
)
from src.optimization.schemas import NetworkPlanIndividual, ObjectiveValues, RouteChromosome


def dominates(val_a: ObjectiveValues, val_b: ObjectiveValues) -> bool:
    """Verifica dominancia de Pareto: val_a domina a val_b (A ≺ B).

    Criterios:
    - f1 (tiempo): menor es mejor (a <= b)
    - f2 (traslape): menor es mejor (a <= b)
    - f3 (cobertura): mayor es mejor (a >= b)
    """
    no_worse = (
        val_a.f1_travel_time_s <= val_b.f1_travel_time_s
        and val_a.f2_overlap_length_m <= val_b.f2_overlap_length_m
        and val_a.f3_coverage_ratio >= val_b.f3_coverage_ratio
    )
    strictly_better = (
        val_a.f1_travel_time_s < val_b.f1_travel_time_s
        or val_a.f2_overlap_length_m < val_b.f2_overlap_length_m
        or val_a.f3_coverage_ratio > val_b.f3_coverage_ratio
    )
    return no_worse and strictly_better


def fast_non_dominated_sort(
    population: list[NetworkPlanIndividual],
) -> list[list[NetworkPlanIndividual]]:
    """Clasificación rápida en frentes de no dominancia (F1, F2, ...)."""
    fronts: list[list[NetworkPlanIndividual]] = [[]]
    domination_counts: dict[str, int] = {}
    dominated_solutions: dict[str, list[NetworkPlanIndividual]] = {}

    for p in population:
        p_id = p.individual_id
        domination_counts[p_id] = 0
        dominated_solutions[p_id] = []

        for q in population:
            if dominates(p.fitness, q.fitness):
                dominated_solutions[p_id].append(q)
            elif dominates(q.fitness, p.fitness):
                domination_counts[p_id] += 1

        if domination_counts[p_id] == 0:
            p.rank = 0
            fronts[0].append(p)

    i = 0
    while i < len(fronts) and fronts[i]:
        next_front: list[NetworkPlanIndividual] = []
        for p in fronts[i]:
            for q in dominated_solutions[p.individual_id]:
                domination_counts[q.individual_id] -= 1
                if domination_counts[q.individual_id] == 0:
                    q.rank = i + 1
                    next_front.append(q)
        i += 1
        if next_front:
            fronts.append(next_front)

    return fronts


def assign_crowding_distance(front: list[NetworkPlanIndividual]) -> None:
    """Asigna la distancia de hacinamiento a los individuos de un frente de Pareto."""
    num_individuals = len(front)
    if num_individuals == 0:
        return
    if num_individuals <= 2:
        for ind in front:
            ind.crowding_distance = float("inf")
        return

    for ind in front:
        ind.crowding_distance = 0.0

    # Dimensiones: (f1, f2, f3)
    objectives = [
        ("f1_travel_time_s", False),  # min
        ("f2_overlap_length_m", False),  # min
        ("f3_coverage_ratio", True),  # max
    ]

    for attr, _ in objectives:
        front.sort(key=lambda ind: getattr(ind.fitness, attr))
        # Extremos con distancia infinita
        front[0].crowding_distance = float("inf")
        front[-1].crowding_distance = float("inf")

        val_min = getattr(front[0].fitness, attr)
        val_max = getattr(front[-1].fitness, attr)
        spread = val_max - val_min

        if spread > 0:
            for i in range(1, num_individuals - 1):
                prev_val = getattr(front[i - 1].fitness, attr)
                next_val = getattr(front[i + 1].fitness, attr)
                front[i].crowding_distance += (next_val - prev_val) / spread


def crowded_comparison(ind_a: NetworkPlanIndividual, ind_b: NetworkPlanIndividual) -> int:
    """Operador de comparación abarrotada (Crowded Comparison Operator)."""
    if ind_a.rank < ind_b.rank:
        return -1
    elif ind_a.rank > ind_b.rank:
        return 1
    elif ind_a.crowding_distance > ind_b.crowding_distance:
        return -1
    elif ind_a.crowding_distance < ind_b.crowding_distance:
        return 1
    return 0


def tournament_selection(
    population: list[NetworkPlanIndividual], k: int = 2
) -> NetworkPlanIndividual:
    """Selección por torneo binario basada en rango y crowding distance."""
    selected = random.sample(population, k)
    best = selected[0]
    for candidate in selected[1:]:
        if crowded_comparison(candidate, best) < 0:
            best = candidate
    return best


class NSGA2Solver:
    """Optimizador Multiobjetivo NSGA-II para Redes de Transporte en Benito Juárez."""

    def __init__(
        self,
        G: nx.MultiDiGraph,
        od_pairs: list[ODPair],
        pois: list[PointOfInterest],
        population_size: int = 30,
        generations: int = 25,
        crossover_prob: float = 0.8,
        mutation_prob: float = 0.3,
        seed: int = 42,
    ):
        self.G = G
        self.od_pairs = od_pairs
        self.pois = pois
        self.pop_size = population_size
        self.generations = generations
        self.cx_prob = crossover_prob
        self.mut_prob = mutation_prob
        self.seed = seed
        self.od_volumes = {(p.origin_id, p.destination_id): p.trip_volume for p in od_pairs}

        random.seed(seed)

    def _create_individual(self, ind_id: str, stochastic: bool = True) -> NetworkPlanIndividual:
        """Crea un individuo generando caminos para cada par OD."""
        routes: list[RouteChromosome] = []

        for pair in self.od_pairs:
            path = generate_initial_route(
                self.G, pair.origin_node, pair.dest_node, stochastic=stochastic
            )
            length_m, time_s = calculate_route_metrics(self.G, path)
            routes.append(
                RouteChromosome(
                    route_id=f"{ind_id}_{pair.origin_id}_{pair.destination_id}",
                    origin_id=pair.origin_id,
                    destination_id=pair.destination_id,
                    node_sequence=path,
                    length_m=length_m,
                    travel_time_s=time_s,
                )
            )

        fitness = evaluate_individual_fitness(self.G, routes, self.pois, self.od_volumes)
        return NetworkPlanIndividual(individual_id=ind_id, routes=routes, fitness=fitness)

    def evolve(self) -> tuple[list[NetworkPlanIndividual], list[dict[str, Any]]]:
        """Ejecuta el ciclo generacional completo de NSGA-II."""
        # 1. Población inicial
        population: list[NetworkPlanIndividual] = []
        # Primer individuo determinista de referencia
        population.append(self._create_individual("ind_0_baseline", stochastic=False))
        # Resto con perturbación estocástica
        for i in range(1, self.pop_size):
            population.append(self._create_individual(f"ind_init_{i}", stochastic=True))

        fronts = fast_non_dominated_sort(population)
        for front in fronts:
            assign_crowding_distance(front)

        history: list[dict[str, Any]] = []

        # 2. Bucle generacional
        for gen in range(self.generations):
            offspring: list[NetworkPlanIndividual] = []

            while len(offspring) < self.pop_size:
                parent1 = tournament_selection(population)
                parent2 = tournament_selection(population)

                # Clonar rutas para los hijos
                child_routes_1: list[RouteChromosome] = []
                child_routes_2: list[RouteChromosome] = []

                for r1, r2 in zip(parent1.routes, parent2.routes, strict=False):
                    p1_seq = r1.node_sequence.copy()
                    p2_seq = r2.node_sequence.copy()

                    # Crossover
                    if random.random() < self.cx_prob:
                        p1_seq, p2_seq = crossover_intersection(self.G, p1_seq, p2_seq)

                    # Mutación
                    if random.random() < self.mut_prob:
                        p1_seq = mutation_k_shortest_path(self.G, p1_seq)
                    if random.random() < self.mut_prob:
                        p2_seq = mutation_k_shortest_path(self.G, p2_seq)

                    l1, t1 = calculate_route_metrics(self.G, p1_seq)
                    l2, t2 = calculate_route_metrics(self.G, p2_seq)

                    child_routes_1.append(
                        RouteChromosome(
                            route_id=f"g{gen}_c1_{r1.origin_id}_{r1.destination_id}",
                            origin_id=r1.origin_id,
                            destination_id=r1.destination_id,
                            node_sequence=p1_seq,
                            length_m=l1,
                            travel_time_s=t1,
                        )
                    )
                    child_routes_2.append(
                        RouteChromosome(
                            route_id=f"g{gen}_c2_{r2.origin_id}_{r2.destination_id}",
                            origin_id=r2.origin_id,
                            destination_id=r2.destination_id,
                            node_sequence=p2_seq,
                            length_m=l2,
                            travel_time_s=t2,
                        )
                    )

                fit1 = evaluate_individual_fitness(
                    self.G, child_routes_1, self.pois, self.od_volumes
                )
                fit2 = evaluate_individual_fitness(
                    self.G, child_routes_2, self.pois, self.od_volumes
                )

                offspring.append(
                    NetworkPlanIndividual(
                        individual_id=f"gen_{gen}_ind_{len(offspring)}",
                        routes=child_routes_1,
                        fitness=fit1,
                    )
                )
                if len(offspring) < self.pop_size:
                    offspring.append(
                        NetworkPlanIndividual(
                            individual_id=f"gen_{gen}_ind_{len(offspring)}",
                            routes=child_routes_2,
                            fitness=fit2,
                        )
                    )

            # Reemplazo elitista R_t = P_t U Q_t
            combined = population + offspring
            fronts = fast_non_dominated_sort(combined)

            new_pop: list[NetworkPlanIndividual] = []
            for front in fronts:
                assign_crowding_distance(front)
                if len(new_pop) + len(front) <= self.pop_size:
                    new_pop.extend(front)
                else:
                    # Ordenar por crowding distance descendente y tomar el sobrante
                    front.sort(key=lambda ind: ind.crowding_distance, reverse=True)
                    needed = self.pop_size - len(new_pop)
                    new_pop.extend(front[:needed])
                    break

            population = new_pop

            # Registrar métricas de la generación
            p_front = fronts[0] if fronts else []
            min_t = min(ind.fitness.f1_travel_time_s for ind in p_front) if p_front else 0.0
            max_cov = max(ind.fitness.f3_coverage_ratio for ind in p_front) if p_front else 0.0

            history.append(
                {
                    "generation": gen + 1,
                    "pareto_size": len(p_front),
                    "best_weighted_time_s": min_t,
                    "best_coverage_ratio": max_cov,
                }
            )

        pareto_front = [ind for ind in population if ind.rank == 0]
        return pareto_front, history
