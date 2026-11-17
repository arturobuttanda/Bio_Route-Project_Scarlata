.PHONY: setup install run-pipeline build-spa export-gis docker-up docker-down test lint typecheck clean

PYTHON ?= .venv/Scripts/python.exe

setup:
	@echo "==> Configurando entorno virtual e instalando dependencias con uv..."
	python -m uv venv --python 3.11 .venv
	python -m uv pip install -r requirements.txt --python .venv/Scripts/python.exe
	python -m uv pip install -e . --python .venv/Scripts/python.exe

install:
	@echo "==> Instalando dependencias con pip..."
	pip install -r requirements.txt
	pip install -e .

run-pipeline:
	@echo "==> Ejecutando pipeline completo End-to-End (Fases 1 a 6)..."
	$(PYTHON) run_pipeline.py --skip-osm

build-spa:
	@echo "==> Ensamblando Dashboard Web Geoespacial (SPA)..."
	$(PYTHON) -m src.export.spa_builder

export-gis:
	@echo "==> Exportando capas GeoPackage, GeoParquet y Web GeoJSON..."
	$(PYTHON) -m src.export.spatial_export

docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down

test:
	$(PYTHON) -m pytest -v

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src config

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('.ruff_cache'), pathlib.Path('.mypy_cache'), *pathlib.Path('.').rglob('__pycache__')]]"
