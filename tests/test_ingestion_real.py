"""Pruebas unitarias para la ingesta real de POIs, transporte, accidentes y ruteo seguro."""

import geopandas as gpd
from shapely.geometry import Point

from src.demand.schemas import POIKind, PointOfInterest
from src.graph.builder import generate_synthetic_benito_juarez_grid
from src.graph.cleaner import extract_lscc, project_node_coordinates
from src.graph.routing_baseline import compute_baseline_routes
from src.graph.weights import assign_edge_weights
from src.ingestion.accidents import enrich_graph_with_accident_risk
from src.ingestion.schemas import (
    AccidentsSummarySchema,
    POISummarySchema,
    QAReportSchema,
    TransitSummarySchema,
)


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
