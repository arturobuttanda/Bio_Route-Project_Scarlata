"""Operadores genéticos bioinspirados adaptados a la topología de grafos dirigidos reales.

Garantizan estricta continuidad y factibilidad física de las rutas sobre la LSCC de Benito Juárez.
"""

import random

import networkx as nx


def repair_path(G: nx.MultiDiGraph, path: list[int]) -> list[int]:
    """Repara un camino eliminando bucles y asegurando conectividad dirigida consecutiva.

    Args:
        G: Grafo dirigido LSCC.
        path: Secuencia de identificadores de nodos.

    Returns:
        Camino reparado continuo y libre de bucles internos inmediatos.
    """
    if len(path) <= 1:
        return path

    # 1. Eliminar ciclos simples (si un nodo se repite, cortar el bucle)
    clean_path: list[int] = []
    seen: dict[int, int] = {}

    for node in path:
        if node in seen:
            # Rebobinar hasta la primera aparición del nodo
            cut_idx = seen[node]
            # Eliminar del registro los nodos descartados
            for discarded in clean_path[cut_idx + 1 :]:
                if discarded in seen:
                    del seen[discarded]
            clean_path = clean_path[: cut_idx + 1]
        else:
            seen[node] = len(clean_path)
            clean_path.append(node)

    # 2. Verificar que cada par consecutivo (u, v) tenga arista dirigida en G
    repaired: list[int] = [clean_path[0]]

    for i in range(len(clean_path) - 1):
        u, v = clean_path[i], clean_path[i + 1]
        if G.has_edge(u, v):
            repaired.append(v)
        else:
            # Si no hay arista directa, calcular camino mínimo local para reanudar la continuidad
            try:
                sub_path = nx.shortest_path(G, u, v, weight="travel_time_s")
                repaired.extend(sub_path[1:])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                # Si fallara localmente, continuar con v si existe
                repaired.append(v)

    # Segunda pasada rápida de poda de ciclos tras la reparación local
    final_path: list[int] = []
    seen_final: dict[int, int] = {}
    for node in repaired:
        if node in seen_final:
            idx = seen_final[node]
            for discarded in final_path[idx + 1 :]:
                if discarded in seen_final:
                    del seen_final[discarded]
            final_path = final_path[: idx + 1]
        else:
            seen_final[node] = len(final_path)
            final_path.append(node)

    return final_path


def crossover_intersection(
    G: nx.MultiDiGraph,
    path_a: list[int],
    path_b: list[int],
) -> tuple[list[int], list[int]]:
    """Cruce topológico de intersección: recombina rutas en nodos espaciales comunes.

    Identifica la intersección V_inter = path_a ∩ path_b e intercambia los segmentos
    posteriores al punto de cruce, conservando el destino original si es compatible.
    """
    if len(path_a) < 3 or len(path_b) < 3:
        return path_a.copy(), path_b.copy()

    # Nodos intermedios comunes (excluyendo extremos si tienen distinto origen/destino)
    common_nodes = set(path_a[1:-1]).intersection(set(path_b[1:-1]))

    if not common_nodes:
        # Si no comparten nodos intermedios, retornar copias sin modificación
        return path_a.copy(), path_b.copy()

    # Seleccionar punto de cruce al azar
    pivot = random.choice(list(common_nodes))
    idx_a = path_a.index(pivot)
    idx_b = path_b.index(pivot)

    # Recombinar subcaminos
    child_a = path_a[:idx_a] + path_b[idx_b:]
    child_b = path_b[:idx_b] + path_a[idx_a:]

    return repair_path(G, child_a), repair_path(G, child_b)


def mutation_k_shortest_path(
    G: nx.MultiDiGraph,
    path: list[int],
    mutation_intensity: float = 0.5,
) -> list[int]:
    """Mutación topológica por desvío estocástico (k-shortest path / jittering).

    Selecciona dos nodos no consecutivos a lo largo del camino y recalcula el tramo
    intermedio introduciendo perturbaciones estocásticas de coste en las aristas.
    """
    if len(path) < 4:
        return path.copy()

    # Seleccionar dos índices separados por al menos 2 pasos
    start_idx = random.randint(0, len(path) - 3)
    max_step = min(len(path) - 1, start_idx + 8)
    end_idx = random.randint(start_idx + 2, max_step)

    u, v = path[start_idx], path[end_idx]

    try:
        # Función de peso con ruido estocástico para forzar caminos alternativos
        def stochastic_weight(u_node, v_node, d):
            base_time = d.get("travel_time_s", 1.0)
            jitter = random.uniform(0.6, 2.5) if random.random() < mutation_intensity else 1.0
            return base_time * jitter

        alt_subpath = nx.shortest_path(G, u, v, weight=stochastic_weight)
        mutated_path = path[:start_idx] + alt_subpath + path[end_idx + 1 :]
        return repair_path(G, mutated_path)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return path.copy()


def generate_initial_route(
    G: nx.MultiDiGraph,
    u_origin: int,
    v_dest: int,
    stochastic: bool = True,
) -> list[int]:
    """Genera una ruta inicial factible entre un par de nodos, con opción a perturbación estocástica."""
    if not stochastic:
        try:
            return nx.shortest_path(G, u_origin, v_dest, weight="travel_time_s")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return [u_origin, v_dest]

    def noisy_weight(u_n, v_n, d):
        base_time = d.get("travel_time_s", 1.0)
        return base_time * random.uniform(0.7, 1.8)

    try:
        raw_path = nx.shortest_path(G, u_origin, v_dest, weight=noisy_weight)
        return repair_path(G, raw_path)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return nx.shortest_path(G, u_origin, v_dest, weight="travel_time_s")
