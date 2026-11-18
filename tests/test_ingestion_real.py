"""Pruebas unitarias para la ingesta real de POIs, transporte, accidentes y ruteo seguro."""

import geopandas as gpd
from shapely.geometry import Point

from src.demand.schemas import POIKind, PointOfInterest
from src.graph.builder import generate_synthetic_benito_juarez_grid
from src.graph.cleaner import extract_lscc, project_node_coordinates
from src.graph.multimodal import build_multimodal_layer
from src.graph.routing_baseline import compute_baseline_routes
from src.graph.weights import assign_edge_weights
from src.ingestion.accident_analytics import classify_time_band, run_accident_analytics
from src.ingestion.accidents import enrich_graph_with_accident_risk
from src.ingestion.schemas import (
    AccidentsSummarySchema,
    POISummarySchema,
    QAReportSchema,
    TrafficSummarySchema,
    TransitSummarySchema,
)
from src.ingestion.traffic import enrich_graph_with_traffic


def test_ingestion_schemas_validation():
    """Valida los esquemas Pydantic v2 de POIs, transporte y accidentes."""
    poi = PointOfInterest(
        id="HOSP_001",
        name="Hospital General Xoco",
        kind=POIKind.HOSPITAL,
        lon=-99.164,
        lat=19.361,
        x_m=482780.0,
        y_m=2140900.0,
        weight=4.2,
    )
    assert poi.kind == POIKind.HOSPITAL

    t_sum = TransitSummarySchema(
        total_lines=10,
        total_stops=50,
        lines_by_mode={"metro": 4, "rtp": 6},
        stops_by_mode={"metro": 10, "rtp": 40},
        total_length_km=42.5,
    )
    assert t_sum.crs_projected == "EPSG:32614"

    a_sum = AccidentsSummarySchema(total_accidents=120, window_months=24, total_injured=95)
    assert a_sum.window_months == 24

    p_sum = POISummarySchema(total_pois=80, counts_by_kind={"hospital": 12, "school": 68})
    assert p_sum.total_pois == 80

    qa = QAReportSchema(
        pois_total=100,
        pois_containment_pct=100.0,
        pois_mean_snap_m=45.0,
        passed=True,
    )
    assert qa.passed is True


def test_enrich_graph_with_accident_risk_and_safe_routing():
    """Verifica el enriquecimiento de riesgo vial y ruteo seguro sobre red sintética."""
    G = extract_lscc(
        project_node_coordinates(assign_edge_weights(generate_synthetic_benito_juarez_grid()))
    )

    # Tomar una arista real del grafo y colocar un accidente exactamente sobre su nodo origen
    u, v = next(iter(G.edges()))
    ux, uy = G.nodes[u]["x_m"], G.nodes[u]["y_m"]

    acc_gdf = gpd.GeoDataFrame(
        [{"severity_weight": 4.0, "geometry": Point(ux, uy)}],
        crs="EPSG:32614",
    )

    G_risk, edges_with_acc = enrich_graph_with_accident_risk(
        G, accidents_gdf=acc_gdf, buffer_m=25.0
    )
    assert edges_with_acc >= 1

    edge_data = next(iter(G_risk[u][v].values()))
    assert edge_data["accident_count"] >= 1
    assert edge_data["risk_score"] >= 4.0
    assert edge_data["safe_travel_time_s"] > edge_data["travel_time_s"]

    # Verificar que compute_baseline_routes soporta weight_attr='safe_travel_time_s'
    nodes = list(G_risk.nodes())
    from src.demand.schemas import ODPair

    od = [
        ODPair(
            origin_id="A",
            destination_id="B",
            origin_node=nodes[0],
            dest_node=nodes[-1],
            trip_volume=50.0,
        )
    ]
    routes, summary = compute_baseline_routes(
        G_risk, od, algorithm="astar", weight_attr="safe_travel_time_s"
    )
    assert len(routes) == 1
    assert summary.unreachable_pairs == 0


def test_dbscan_accident_analytics(tmp_path):
    """Verifica el clustering espacial DBSCAN y el perfil horario 24h."""
    rows = []
    for i in range(18):
        rows.append(
            {
                "folio": f"F_{i}",
                "latitud": 19.375 + i * 0.00005,
                "longitud": -99.165 + i * 0.00005,
                "colonia": "Del Valle",
                "tipo_evento": "Choque",
                "hora_evento": "08:30" if i < 10 else "19:15",
                "personas_lesionadas": 1,
                "personas_fallecidas": 0,
                "severity_weight": 1.5,
                "geometry": Point(-99.165 + i * 0.00005, 19.375 + i * 0.00005),
            }
        )
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326").to_crs("EPSG:32614")
    res = run_accident_analytics(
        accidents_gdf=gdf,
        eps_meters=120.0,
        min_samples=15,
        output_json=tmp_path / "acc_analytics.json",
    )
    assert res.cluster_count == 1
    assert res.clusters[0].accident_count == 18
    assert res.band_counts["pico_am"] == 10
    assert res.band_counts["pico_pm"] == 8
    assert classify_time_band(23) == "noche"


def test_multimodal_layer_builder():
    """Verifica que las paradas de Metro/Metrobús se conecten al grafo LSCC."""
    G = extract_lscc(
        project_node_coordinates(assign_edge_weights(generate_synthetic_benito_juarez_grid()))
    )
    nodes = list(G.nodes(data=True))
    p1 = nodes[0][1]
    p2 = nodes[1][1]
    stops_gdf = gpd.GeoDataFrame(
        [
            {
                "stop_id": "S1",
                "stop_name": "Estación A",
                "mode": "metro",
                "route_name": "L3",
                "geometry": Point(p1["x"], p1["y"]),
            },
            {
                "stop_id": "S2",
                "stop_name": "Estación B",
                "mode": "metro",
                "route_name": "L3",
                "geometry": Point(p2["x"], p2["y"]),
            },
        ],
        crs="EPSG:4326",
    ).to_crs("EPSG:32614")

    mm = build_multimodal_layer(G, transit_stops=stops_gdf)
    assert len(mm["transit_nodes"]) == 2
    # 2 nodos * 2 aristas transfer + 2 aristas troncales (bidireccional) = 6 aristas
    assert len(mm["transit_edges"]) >= 4


def test_traffic_enrichment(tmp_path):
    """Verifica la asignación de factores de tráfico y LOS por franja horaria."""
    G = extract_lscc(
        project_node_coordinates(assign_edge_weights(generate_synthetic_benito_juarez_grid()))
    )
    G_tr, summary = enrich_graph_with_traffic(
        G, output_summary=tmp_path / "traffic_summary.json", use_infovial=False
    )
    assert isinstance(summary, TrafficSummarySchema)
    assert summary.total_edges_evaluated == G_tr.number_of_edges()
    assert summary.mean_factor_by_band["pm"] >= summary.mean_factor_by_band["noche"]
    edge_d = next(iter(G_tr.edges(data=True)))[2]
    assert "traffic_pm" in edge_d
    assert edge_d["los_pm"] in {"A", "B", "C", "D", "E", "F"}
