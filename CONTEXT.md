# SYSTEM CONTEXT & STATE (Live Document)

## Current Status
- **Active Phase:** Fase 7 Completada — Enriquecimiento GIS Real, Siniestralidad Vial y Nuevo Dashboard SPA.
- **Completed Deliverables:**
  - Topología LSCC: 5,618 nodos, 11,062 aristas (979.46 km), 66 aristas contraflujo.
  - POIs Reales (`src/ingestion/pois_real.py`): 456 POIs en Benito Juárez (312 escuelas, 80 plazas/centros comerciales, 34 hospitales, 12 Metro, 6 Metrobús, 12 colonias).
  - Transporte Multimodal Real (`src/ingestion/transit.py`): 405 trazas y 931 paradas reales (Concesionado/camiones, RTP, Metrobús, Metro, Trolebús).
  - Accidentes Viales 24m (`src/ingestion/accidents.py`): 5,389 hechos de tránsito SSC (6,252 lesionados, 57 fallecidos), con cálculo de `risk_score` y `safe_travel_time_s` por arista para ruteo seguro y NSGA-II.
  - Exportación OGC (`benito_juarez_mobility.gpkg`): 9 capas, 18,713 features + estilos QGIS en `data/outputs/qgis/`.
  - Nuevo Dashboard SPA (`src/export/templates/dashboard.html`): KPIs dinámicos reales, gestor de capas por modo/POI, Heatmap de accidentes (`Leaflet.heat`), aristas de alto riesgo y ruteador Rápido/Seguro.
- **QA:** `pytest` (27 passed), `ruff` (0 errores), `mypy` (0 errores en 38 archivos).
- **Architectural Rules:** Blind Data Ingestion strictly enforced. Dual CRS: EPSG:32614 (metric) / EPSG:4326 (web).
