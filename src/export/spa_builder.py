"""Generador de la Aplicación Web Geoespacial Completa (SPA) de Benito Juárez.

Construye un dashboard HTML interactivo autocontenido de clase ejecutiva a partir
de la plantilla estática ``src/export/templates/dashboard.html``.
"""

import json
from pathlib import Path

from config.settings import settings
from src.export.data_compiler import compile_spa_data

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "dashboard.html"


def build_spa_dashboard(output_html: Path | None = None) -> Path:
    """Compila e inyecta los datos espaciales y de optimización en la SPA interactiva."""
    if output_html is None:
        output_html = settings.outputs_dir / "dashboard_benito_juarez.html"
    output_html.parent.mkdir(parents=True, exist_ok=True)

    print("[1/2] Compilando datos espaciales, genomas de Pareto y contingencias...")
    data = compile_spa_data()
    data_json_str = json.dumps(data)

    print("[2/2] Ensamblando la interfaz Single Page Application (HTML/CSS/JS)...")
    template_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html_content = template_html.replace("__SPA_DATA_JSON__", data_json_str)

    output_html.write_text(html_content, encoding="utf-8")
    print(f"==> SPA Geoespacial construida con éxito en: {output_html}")
    return output_html


if __name__ == "__main__":
    build_spa_dashboard()
