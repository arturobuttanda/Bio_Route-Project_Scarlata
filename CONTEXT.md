# SYSTEM CONTEXT & STATE (Live Document)

## Current Status
- **Active Phase:** Proyecto Completo, Limpio y Listo para Repositorio (Fases 0 a 6 + Refactorización).
- **Completed Deliverables:**
  - Phase 0: Scaffolding, `uv`, Python 3.11, Docker PostGIS, `AGENTS.md`, `pyproject.toml`, `requirements.txt`.
  - Phase 1: Ingesta OSM y topología vial BJ. LSCC de 5,618 nodos y 11,062 aristas (979.46 km), 66 aristas contraflujo.
  - Phase 2: 30 POIs anclados en UTM 14N. 150 pares OD gravitatorios: tiempo medio 130.54s, dist media 1,528m.
  - Phase 3: Metaheurística NSGA-II. 20 soluciones Pareto, -18.66% tiempo viaje (106.18s vs 130.54s), hipervolumen 0.8842.
  - Phase 4: Simulación contingencias C5 (3 escenarios). Latencia recálculo: 5.37 ms (SLA < 50ms). Robustez: +6.5% vs baseline.
  - Phase 5: Exportación GIS multi-formato: OGC GeoPackage (`benito_juarez_mobility.gpkg`, 6 capas, 11,562 features), GeoParquet columnar, Web GeoJSON (RFC 7946) y estilos QGIS (`data/outputs/qgis/*.qml`).
  - Phase 6: Orquestador E2E `run_pipeline.py` (`bj-pipeline`) y SPA `dashboard_benito_juarez.html` compilada desde `src/export/templates/dashboard.html`.
- **Architecture & Hygiene:**
  - Carga unificada de grafos (`load_road_network`) y parámetros YAML tipados en `settings.spatial_params`.
  - Código obsoleto eliminado (`quick_map.py`, `pack_context.py`, `repomix.config.json`, `context_pack.md`, `cache/`).
- **Architectural Rules:** Blind Data Ingestion strictly enforced. Dual CRS: EPSG:32614 (metric) / EPSG:4326 (web).
