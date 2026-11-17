# Context Engineering & Agent Protocols (Benito Juárez Geospatial AI)

Este documento rige el comportamiento de todos los agentes de codificación (LLMs) que operen en este repositorio.

---

## 1. Regla Cardinal de Token Management: "Blind Data Ingestion"
- **PROHIBIDO LEER ARCHIVOS DE DATOS:** Los agentes NUNCA deben inspeccionar, abrir o imprimir archivos crudos ni derivados espaciales:
  - `data/**` (`.geojson`, `.gpkg`, `.graphml`, `.parquet`, `.osm`, `.shp`, `.csv`, `.zip`).
  - Geometrías WKT / GeoJSON en bruto en el chat (provoca saturación de contexto y context rot inmediato).
- **CONTRATO BASADO EN ESQUEMAS:** Para razonar sobre los datos, los agentes consultan EXCLUSIVAMENTE:
  1. Schemas de Pydantic en `src/*/schemas.py`.
  2. Metadatos compactos y reportes sintéticos JSON (`network_summary.json`, `baseline_metrics.json`, `optimization_summary.json`).

---

## 2. Convenciones de Ingeniería de Software & Tipado Estricto
- **Python 3.11+**: Uso obligatorio de `type hints` nativos (`list[str]`, `dict[str, Any]`, `tuple[int, ...]`, `T | None`).
- **Pydantic v2**: Toda configuración y payload de intercambio debe modelarse con `BaseModel` o `BaseSettings`.
- **Inmutabilidad y Funciones Puras**: La lógica de negocio y operadores bioinspirados deben ser deterministas y recibir semillas (`seed: int = 42`).
- **No Side-Effects en Importaciones**: Ningún módulo de `src/` debe ejecutar computaciones costosas en el scope global.

---

## 3. Estándares Geoespaciales y CRS
- **Alcaldía Benito Juárez (CDMX):**
  - **Coordenadas Geográficas:** `EPSG:4326` (WGS 84, latitud/longitud en grados decimales). Uso exclusivo para ingestión de OSM, exportación GeoJSON web y visualización global.
  - **Coordenadas Proyectadas Métricas:** `EPSG:32614` (WGS 84 / UTM Zona 14N). Uso OBLIGATORIO para:
    - Buffers espaciales (500m de contención).
    - Longitudes métricas de aristas ($L_e$ en metros).
    - Distancias caminables ($400\text{ m}$).
    - Estimación de tiempos de viaje e impedancias físicas.
- **Topología Vial:** Grafo dirigido ponderado $\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{W})$ con garantía de componente fuertemente conexa (LSCC).

---

## 4. Flujo de Trabajo con `CONTEXT.md`
- Al iniciar cualquier interacción, el agente consulta `CONTEXT.md` para situarse en la fase activa.
- Al culminar un hito o cambio arquitectónico, el agente DEBE actualizar `CONTEXT.md` manteniendo su tamaño por debajo de **500 tokens**.
