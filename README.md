# Benito Juárez Geospatial Mobility Digital Twin & Bioinspired Optimization

Sistema reproducible de simulación urbana, optimización bioinspirada de rutas de transporte público (NSGA-II), simulación de contingencias dinámicas e interoperabilidad GIS centrado en la alcaldía **Benito Juárez (Ciudad de México)**.

---

## 🎯 Visión General del Sistema
El proyecto modela la red vial y de transporte de la alcaldía Benito Juárez como un grafo dirigido ponderado $\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathcal{W})$ de alta fidelidad topológica (5,618 nodos, 11,062 aristas, 979.46 km transitables), anclado a la red de transporte masivo (Metro Líneas 2, 3, 7 y 12; Metrobús Líneas 1 y 2) y a los centroides de las colonias más representativas (Del Valle, Narvarte, Nápoles, Mixcoac, Álamos, Portales).

### Componentes del Sistema:
1. **Línea Base Determinista (Fase 2):** Ruteo mediante caminos mínimos ($A^*$ con heurística admisible euclidiana y Dijkstra bidireccional sobre 150 pares OD gravitatorios).
2. **Metaheurística Bioinspirada (Fase 3):** Algoritmo genético multiobjetivo **NSGA-II** con operadores espaciales (crossover por intersección de grafos, mutación estocástica $k$-caminos y reparación de lazos), logrando un frente de Pareto que reduce el tiempo de viaje en **-18.66%** con alta cobertura de demanda y mínimo solapamiento.
3. **Simulador de Contingencias y Resiliencia (Fase 4):** Modelado de escenarios de estrés C5 (cierre vial de Eje Central, congestión súbita en Insurgentes 3.0x y colapso de transfer en Metro Zapata). Re-ruteo reactivo en **5.37 ms** (SLA < 50ms) y ganancia de resiliencia del **+6.5%** ($R_{\text{net}} = 0.6401$).
4. **Interoperabilidad GIS Multi-formato (Fase 5):** OGC GeoPackage multietiqueta (6 capas, 11,562 entidades), GeoParquet columnar para DuckDB / Tableau, Web GeoJSON (RFC 7946) y estilos cartográficos XML para QGIS 3.x (`.qml`).
5. **Dashboard Web Geoespacial Ejecutivo (SPA):** Interfaz interactiva autocontenida de clase ejecutiva con máscara perimetral inversa (*Donut Mask*), flujos cinéticos en tiempo real (*dash animation*), selector dinámico de contingencias y simulador punto a punto.

---

## 🚀 Guía de Instalación Rápida

### Opción A: Con `pip` estándar (Recomendada para compartir)
Requiere **Python 3.11+**:

```bash
# 1. Crear entorno virtual
python -m venv .venv

# 2. Activar entorno virtual
# En Windows (PowerShell):
.venv\Scripts\Activate.ps1
# En Linux/Mac:
source .venv/bin/activate

# 3. Instalar dependencias exactas y reproducibles
pip install -r requirements.txt

# 4. Instalar el paquete en modo editable
pip install -e .
```

### Opción B: Con `uv` (Ultra rápido)
```bash
python -m uv venv --python 3.11 .venv
python -m uv pip install -r requirements.txt --python .venv/Scripts/python.exe
python -m uv pip install -e . --python .venv/Scripts/python.exe
```

---

## ⚡ Ejecución en un Solo Toque

### Orquestador End-to-End (`run_pipeline.py`)
Ejecuta el ciclo de vida completo (Fases 1 a 6) de forma secuencial y determinista:

```bash
# Ejecutar pipeline completo reutilizando la red procesada
python run_pipeline.py --skip-osm

# O mediante Makefile:
make run-pipeline
```

### Ejecución Modular por Etapas:
```bash
# 1. Ingesta y construcción de la red vial LSCC
python -m src.graph.builder

# 2. Snapping de POIs y matriz gravitatoria OD
python -m src.demand.pipeline

# 3. Optimización Bioinspirada NSGA-II
python -m src.optimization.pipeline

# 4. Simulación de contingencias y resiliencia C5
python -m src.simulation.pipeline

# 5. Exportación GeoPackage, GeoParquet y GeoJSON
python -m src.export.spatial_export

# 6. Compilación de la aplicación web interactiva (SPA)
python -m src.export.spa_builder
```

---

## 🗺️ Aplicación Web Interactiva (SPA)

Abre directamente en cualquier navegador web moderno (sin necesidad de servidor backend):
```text
data/outputs/dashboard_benito_juarez.html
```

**Funcionalidades de la aplicación:**
- **🔒 Contención Espacial Estricta:** Bounded con `maxBoundsViscosity: 1.0` y Máscara Donut en `#090d16` (85% opacidad) que centra la atención exclusivamente en Benito Juárez.
- **⚡ Flujo Cinético Animado:** Trazas de partículas en movimiento continuo sobre las rutas troncales con efecto Neón Glow.
- **🚨 Simulador de Contingencias C5 en Vivo:** Permite activar en tiempo real cierres viales o colapsos de transbordo y observar el recálculo reactivo con métricas de desvío.
- **🧬 Explorador del Frente de Pareto:** Slider interactivo para transicionar suavemente entre las soluciones óptimas del algoritmo genético.
- **🎯 Ruteador OD Punto a Punto:** Selección interactiva de cualquier origen y destino entre los 30 POIs de transporte de la demarcación.
- **🗺️ Capas Cartográficas Esri:** Dark Gray Canvas (nocturno de alto contraste), Satélite HD y Calles Urbanas.

---

## 📂 Artefactos GIS Generados (`data/outputs/`)

| Archivo | Formato | Sistema de Referencia | Descripción |
| :--- | :--- | :--- | :--- |
| `benito_juarez_mobility.gpkg` | OGC GeoPackage | `EPSG:32614` (UTM 14N) | 6 capas vectoriales (`boundary_bj`, `road_network`, `transit_stops`, `baseline_routes`, `pareto_optimal_routes`, `contingency_chokepoints`). |
| `analytics_routes.geoparquet` | Apache GeoParquet | `EPSG:32614` | Almacenamiento columnar optimizado para consultas analíticas de alto rendimiento en DuckDB y Tableau. |
| `routes_export.geojson` | GeoJSON (RFC 7946) | `EPSG:4326` (WGS84) | Exportación web estándar compatible con Mapbox, Kepler.gl y deck.gl. |
| `qgis/road_network_style.qml` | QGIS Style XML | - | Simbología graduada por velocidades viales para QGIS 3.x. |
| `qgis/pareto_routes_style.qml` | QGIS Style XML | - | Simbología clasificada por tiempos de viaje de rutas Pareto. |
| `dashboard_benito_juarez.html`| HTML/CSS/JS (SPA) | - | Gemelo digital interactivo y visor visual ejecutivo. |

---

## 🧪 Pruebas Unitarias y Calidad de Código

El repositorio cuenta con 25 pruebas unitarias automatizadas que cubren conectividad LSCC, operadores genéticos, resiliencia C5 y exportación GIS:

```bash
# Ejecutar suite completa con pytest
.venv/Scripts/pytest -v

# Verificar calidad y formato con Ruff
.venv/Scripts/ruff check .
.venv/Scripts/ruff format --check .
```

---

## 📊 Métricas del Gemelo Digital

| Métrica | Línea Base Determinista (Fase 2) | Optimización NSGA-II (Fase 3) | Diferencia / Impacto |
| :--- | :--- | :--- | :--- |
| **Tiempo Medio de Viaje** | 130.54 segundos (~2.17 min) | **106.18 segundos** (~1.76 min) | **-18.66% más rápido** |
| **Pares Evaluados** | 150 pares OD gravitatorios | 15 corredores simultáneos | Coordinación de red |
| **Conectividad LSCC** | 100% (0 pares inalcanzables) | 100% continuidad dirigida | Sin bucles ni saltos |
| **Hipervolumen Pareto** | N/A | **0.8842** | Alta convergencia multiobjetivo |
| **Robustez ante Contingencias ($R_{\text{net}}$)** | 0.6007 | **0.6401** | **+6.5% más resiliente** |
| **Latencia de Re-ruteo Reactivo** | N/A | **5.37 milisegundos** | Cumple SLA (< 50 ms) |

---

## 📁 Estructura del Repositorio
```text
├── config/
│   ├── settings.py             # Configuración Pydantic BaseSettings
│   └── spatial_params.yaml     # Bounding box, CRS UTM 14N, buffers y velocidades
├── data/
│   ├── raw/                    # Datos crudos inmutables
│   ├── interim/                # Artefactos intermedios
│   ├── processed/              # LSCC GraphML y GeoParquet procesados
│   └── outputs/                # GeoPackage, GeoParquet, GeoJSON, qgis/*.qml, JSON y SPA HTML
├── docker/
│   ├── docker-compose.yml      # Servicio PostgreSQL 16 + PostGIS Alpine
│   └── init-db.sql             # Activación de postgis y pgrouting
├── src/
│   ├── ingestion/              # Delimitación oficial de Benito Juárez (boundary)
│   ├── graph/                  # Carga/limpieza LSCC, pesos métricos y ruteo determinista
│   ├── demand/                 # Catálogo de POIs, KDTree y matriz OD gravitatoria
│   ├── optimization/           # Cromosomas, operadores genéticos y NSGA-II
│   ├── simulation/             # Simulación de contingencias C5 y resiliencia
│   └── export/                 # Exportadores GIS (GPKG, GeoParquet, QML) y Dashboard SPA (+ templates/)
├── tests/                      # Suite de pruebas automatizadas pytest (25 tests)
├── run_pipeline.py             # Orquestador maestro del pipeline de extremo a extremo
├── requirements.txt            # Dependencias portables congeladas para terceros
├── pyproject.toml              # Definición estándar del proyecto
├── AGENTS.md                   # Protocolo estricto de Context Engineering
├── CONTEXT.md                  # Documento vivo ultracompacto (< 500 tokens)
└── Makefile                    # Comandos operativos de un toque
```
