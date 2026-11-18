"""Constructor de capa de ruteo multimodal (Metro, Metrobús, RTP + Red Vial LSCC).

Conecta estaciones/paradas reales a los nodos viales más cercanos mediante aristas
de abordaje/descenso con penalización realista y crea aristas troncales entre
estaciones consecutivas según su velocidad comercial.
"""

import math
from typing import Any

import geopandas as gpd
import networkx as nx
from scipy.spatial import KDTree

from config.settings import settings

MODE_SPEED_MPS: dict[str, float] = {
    "metro": 55.0 * (1000.0 / 3600.0),
    "metrobus": 30.0 * (1000.0 / 3600.0),
    "rtp": 22.0 * (1000.0 / 3600.0),
}

MODE_BOARDING_PENALTY_S: dict[str, float] = {
    "metro": 150.0,
    "metrobus": 90.0,
    "rtp": 120.0,
}

MODE_MAX_HOP_M: dict[str, float] = {
    "metro": 2800.0,
    "metrobus": 1500.0,
    "rtp": 950.0,
}


def build_multimodal_layer(
    G: nx.MultiDiGraph,
    transit_stops: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    """Construye nodos y aristas multimodales conectadas al grafo vial LSCC."""
    if transit_stops is None:
        stops_path = settings.processed_data_dir / "transit_stops.geoparquet"
        if not stops_path.exists():
            return {"transit_nodes": [], "transit_edges": []}
        transit_stops = gpd.read_parquet(stops_path)

    if transit_stops.empty:
        return {"transit_nodes": [], "transit_edges": []}

    gdf_utm = transit_stops.to_crs("EPSG:32614")
    gdf_wgs = transit_stops.to_crs("EPSG:4326")

    road_nodes: list[int] = []
    road_xy: list[tuple[float, float]] = []
    for nid, d in G.nodes(data=True):
        if "x_m" in d and "y_m" in d:
            road_nodes.append(int(nid))
            road_xy.append((float(d["x_m"]), float(d["y_m"])))

    if not road_xy:
        return {"transit_nodes": [], "transit_edges": []}

    tree = KDTree(road_xy)
    transit_nodes: list[dict[str, Any]] = []
    transit_edges: list[dict[str, Any]] = []

    # Agrupar paradas por (modo, ruta) para enlazar tramos consecutivos
    stops_by_corridor: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for idx in range(len(gdf_utm)):
        row_u = gdf_utm.iloc[idx]
        row_w = gdf_wgs.iloc[idx]
        mode = str(row_u.get("mode", "")).lower()
        if mode not in MODE_SPEED_MPS:
            continue
        if row_u.geometry is None or row_u.geometry.is_empty:
            continue

        xm, ym = float(row_u.geometry.x), float(row_u.geometry.y)
        dist_snap, nn_idx = tree.query([xm, ym])
        if dist_snap > 400.0:
            continue

        road_nid = road_nodes[int(nn_idx)]
        t_nid = f"TRN_{mode}_{idx}"
        route_name = str(row_u.get("route_name", mode))
        stop_name = str(row_u.get("stop_name", t_nid))

        node_entry = {
            "id": t_nid,
            "lat": round(float(row_w.geometry.y), 5),
            "lon": round(float(row_w.geometry.x), 5),
            "x_m": xm,
            "y_m": ym,
            "mode": mode,
            "name": stop_name,
            "route": route_name,
        }
        transit_nodes.append(node_entry)
        stops_by_corridor.setdefault((mode, route_name), []).append(node_entry)

        # Arista de abordaje (calle -> estación) y descenso (estación -> calle)
        walk_time = float(dist_snap) / 1.25
        board_pen = MODE_BOARDING_PENALTY_S[mode]
        transit_edges.append(
            {
                "u": str(road_nid),
                "v": t_nid,
                "time_s": round(walk_time + board_pen, 1),
                "length_m": round(float(dist_snap), 1),
                "mode": "transfer",
            }
        )
        transit_edges.append(
            {
                "u": t_nid,
                "v": str(road_nid),
                "time_s": round(walk_time + 20.0, 1),
                "length_m": round(float(dist_snap), 1),
                "mode": "transfer",
            }
        )

    # Enlazar paradas consecutivas por vecino más cercano dentro del corredor
    for (mode, _), corridor_stops in stops_by_corridor.items():
        if len(corridor_stops) < 2:
            continue
        speed_mps = MODE_SPEED_MPS[mode]
        max_hop = MODE_MAX_HOP_M[mode]

        # Ordenar por coordenada dominante (N-S o E-O) para formar cadena continua
        xs = [s["x_m"] for s in corridor_stops]
        ys = [s["y_m"] for s in corridor_stops]
        sort_key = "x_m" if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else "y_m"
        ordered = sorted(corridor_stops, key=lambda s: s[sort_key])

        for i in range(len(ordered) - 1):
            a, b = ordered[i], ordered[i + 1]
            dist = math.hypot(a["x_m"] - b["x_m"], a["y_m"] - b["y_m"])
            if 30.0 <= dist <= max_hop:
                t_sec = round(dist / speed_mps + 18.0, 1)  # +18s parada en estación
                d_round = round(dist, 1)
                transit_edges.append(
                    {"u": a["id"], "v": b["id"], "time_s": t_sec, "length_m": d_round, "mode": mode}
                )
                transit_edges.append(
                    {"u": b["id"], "v": a["id"], "time_s": t_sec, "length_m": d_round, "mode": mode}
                )

    return {
        "transit_nodes": [
            {
                "id": n["id"],
                "lat": n["lat"],
                "lon": n["lon"],
                "mode": n["mode"],
                "name": n["name"],
            }
            for n in transit_nodes
        ],
        "transit_edges": transit_edges,
    }
