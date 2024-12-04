.PHONY : env update-lock install test cov type-check linting-check docs publish init update build publish
.DEFAULT_GOAL := init

PY_PATH = 3.11

env :
	poetry env use '$(PY_PATH)'

update-lock :
	poetry lock --no-update

install :
	poetry install --no-interaction

test :
	poetry run pytest

cov :
	poetry run pytest --cov=fhir_converter --cov-report=html

type-check :
	poetry run mypy fhir_converter

linting-check :
	poetry run flake8 fhir_converter --count --select=E9,F63,F7,F82 --show-source --statistics    
	poetry run flake8 fhir_converter --count --ignore=E203,E721 --exit-zero --max-complexity=10 --max-line-length=120 --statistics

docs :
	poetry run lazydocs --output-path="./docs/docstrings" --overview-file="README.md" --src-base-url="https://github.com/chaseastewart/fhir-converter/blob/master/" fhir_converter
	poetry run mkdocs build --site-dir ./_site

init: env install
update : update-lock install
build : init linting-check type-check cov