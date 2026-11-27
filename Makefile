.PHONY: check lint test doctor doctor-readiness doctor-delivery test-delivery self-test

test:
	uv run --locked python -m unittest discover -s tests -v

lint:
	uv run --locked ruff check src scripts tests
	uv run --locked ruff format --check src scripts tests

check: lint test
	uv run --locked python -m compileall -q src scripts

doctor:
	uv run --locked collegium-pipeline doctor --config config/pilot.json

doctor-readiness:
	uv run --locked collegium-pipeline doctor --config config/readiness.json

self-test:
	uv run --locked collegium-pipeline self-test --task-id controller-readiness-live-v1

doctor-delivery:
	uv run --locked collegium-pipeline doctor --config config/delivery.example.json

test-delivery:
	uv run --locked python -m unittest discover -s tests -p test_delivery.py -v
