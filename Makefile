.PHONY: install dev test lint clean

PYTHON ?= python3

install:
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/

lint:
	$(PYTHON) -m ruff check fatture_cli/

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
