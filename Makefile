# Makefile — SatGuard
# Target principale: `make check-all` esegue TUTTI i controlli in sequenza.

.PHONY: check-all types lint test smoke deps clean

## check-all: Esegue tutti i controlli (deps, types, lint, test, smoke)
check-all: deps types lint test smoke
	@echo ""
	@echo "=== ALL CHECKS PASSED ==="
	@echo ""

## types: Type checking con mypy
types:
	mypy src/

## lint: Linting con ruff
lint:
	ruff check src/ tests/

## test: Unit + integration tests
test:
	pytest tests/ -v

## smoke: Smoke test E2E (ingest → propagate → screen → Pc)
smoke:
	python -m satguard.cli.main screen --norad-id 25544 --days 3

## deps: Verifica che verified-deps.toml esista e non sia vuoto
deps:
	@echo "--- Checking verified-deps.toml ---"
	@test -f verified-deps.toml || (echo "ERROR: verified-deps.toml not found" && exit 1)
	@echo "verified-deps.toml found"

## clean: Pulizia artefatti
clean:
	@echo "Cleaning build artifacts..."
	rm -rf __pycache__ .mypy_cache .pytest_cache .ruff_cache dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
