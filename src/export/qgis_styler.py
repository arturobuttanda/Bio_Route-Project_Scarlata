"""Generador de estilos cartográficos QGIS (.qml) para capas de movilidad de Benito Juárez.

Crea archivos XML estándar de QGIS 3.x para renderizado de la red vial y rutas de transporte.
"""

from pathlib import Path


def generate_road_network_qml(output_path: Path) -> Path:
    """Genera archivo .qml con simbología graduada según velocidad permitida (km/h)."""
    qml_content = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" styleCategories="Symbology|Labeling">
  <renderer-v2 type="graduatedSymbol" attr="speed_kph" symbollevels="0">
    <ranges>
      <range render="true" symbol="0" lower="0.0" upper="30.0" label="Zonas 30 (Residencial / Calma)"/>
      <range render="true" symbol="1" lower="30.0" upper="50.0" label="Vías Secundarias (40-50 km/h)"/>
      <range render="true" symbol="2" lower="50.0" upper="80.0" label="Vías Primarias / Ejes (50-70 km/h)"/>
      <range render="true" symbol="3" lower="80.0" upper="120.0" label="Vías de Acceso Controlado (80+ km/h)"/>
    </ranges>
    <symbols>
      <symbol type="line" name="0" clip_to_extent="1">
        <layer pass="0" class="SimpleLine" locked="0">
          <prop k="line_color" v="100,116,139,200"/>
          <prop k="line_width" v="0.6"/>
          <prop k="line_style" v="solid"/>
        </layer>
      </symbol>
      <symbol type="line" name="1" clip_to_extent="1">
        <layer pass="0" class="SimpleLine" locked="0">
          <prop k="line_color" v="59,130,246,230"/>
          <prop k="line_width" v="1.0"/>
          <prop k="line_style" v="solid"/>
        </layer>
      </symbol>
      <symbol type="line" name="2" clip_to_extent="1">
        <layer pass="0" class="SimpleLine" locked="0">
          <prop k="line_color" v="245,158,11,255"/>
          <prop k="line_width" v="1.6"/>
          <prop k="line_style" v="solid"/>
        </layer>
      </symbol>
      <symbol type="line" name="3" clip_to_extent="1">
        <layer pass="0" class="SimpleLine" locked="0">
          <prop k="line_color" v="239,68,68,255"/>
          <prop k="line_width" v="2.2"/>
          <prop k="line_style" v="solid"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(qml_content, encoding="utf-8")
    return output_path


def generate_pareto_routes_qml(output_path: Path) -> Path:
    """Genera archivo .qml con simbología para rutas Pareto graduadas por tiempo de viaje."""
    qml_content = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" styleCategories="Symbology|Labeling">
  <renderer-v2 type="graduatedSymbol" attr="travel_time_s" symbollevels="0">
    <ranges>
      <range render="true" symbol="0" lower="0.0" upper="100.0" label="Rápido (&lt; 100s) - Alta Eficiencia"/>
      <range render="true" symbol="1" lower="100.0" upper="150.0" label="Medio (100 - 150s)"/>
      <range render="true" symbol="2" lower="150.0" upper="300.0" label="Extenso (&gt; 150s)"/>
    </ranges>
    <symbols>
      <symbol type="line" name="0" clip_to_extent="1">
        <layer pass="0" class="SimpleLine" locked="0">
          <prop k="line_color" v="16,185,129,255"/>
          <prop k="line_width" v="1.8"/>
          <prop k="line_style" v="solid"/>
        </layer>
      </symbol>
      <symbol type="line" name="1" clip_to_extent="1">
        <layer pass="0" class="SimpleLine" locked="0">
          <prop k="line_color" v="6,182,212,230"/>
          <prop k="line_width" v="1.4"/>
          <prop k="line_style" v="solid"/>
        </layer>
      </symbol>
      <symbol type="line" name="2" clip_to_extent="1">
        <layer pass="0" class="SimpleLine" locked="0">
          <prop k="line_color" v="249,115,22,230"/>
          <prop k="line_width" v="1.2"/>
          <prop k="line_style" v="dash"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(qml_content, encoding="utf-8")
    return output_path
