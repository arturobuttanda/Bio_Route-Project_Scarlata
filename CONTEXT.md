# SYSTEM CONTEXT & STATE (Live Document)

## Current Status
- **Active Phase:** Fase 10 Completada — Tráfico Vial INFOVIAL, Ruteador Tipo Google Maps y Simulador de Estrés RTP.
- **Completed Deliverables:**
  - Tráfico Vial (`src/ingestion/traffic.py`): 226,916 registros INFOVIAL + calibración horaria `AM/Día/PM/Noche` y Nivel de Servicio (LOS) en 11,062 aristas.
  - Ruteador Tipo Google Maps (`src/export/templates/dashboard.html`): Marcado A→B con clic en mapa (arrastrable), modos Automóvil y Transporte Público, y 4 rutas simultáneas (Rápida, Evitando Riesgos, Eco, Balanceada NSGA-II).
  - Simulador de Estrés RTP: Estrés configurable (`1.8x`, `2.8x`, `4.0x`) sobre cualquier ruta RTP con Desvío Resiliente y Rediseño Completo.
  - Basemaps Esri ArcGIS (`Nocturno`, `Satélite`, `Calles`) + respaldo vectorial LSCC.
- **Architectural Rules:** Blind Data Ingestion strictly enforced. Dual CRS: EPSG:32614 (metric) / EPSG:4326 (web).
