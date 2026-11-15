ifeq ($(OS),Windows_NT)
PY := backend/.venv/Scripts/python.exe
PIP := backend/.venv/Scripts/pip.exe
else
PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip
endif

SCALE ?= 1
export SCALE

.PHONY: setup seed dev dev-api dev-web test test-api test-web demo reset-demo openapi

setup:
	python -m venv backend/.venv
	$(PIP) install -e backend
	cd frontend && npm install

seed:
	cd backend && ../$(PY) -m app.seed --reset

reset-demo:
	cd backend && ../$(PY) -m app.seed --reset

dev-api:
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 dev-api dev-web

demo: seed
	$(MAKE) dev

test-api:
	cd backend && ../$(PY) -m pytest -q

test-web:
	cd frontend && npx tsc --noEmit && npm run build

test: test-api test-web

openapi:
	$(PY) scripts/export_openapi.py
	cd frontend && npx openapi-typescript openapi.json -o lib/schema.d.ts
