# pad-research — developer targets. Never launches training (use the commands in
# .claude/rules/experiment-safety.md so the launch gate hook can inspect them).
export UV_NO_SYNC := 1
export PAD_DATA_ROOT ?= $(CURDIR)/data/processed
UV := uv run --no-sync
.PHONY: setup lock lint format typecheck test test-all ci-local manifests validate-protocols verify-dod mlflow-ui clean-outputs

setup:            ## first-time / after lock change (sync is the ONLY target allowed to touch .venv)
	UV_NO_SYNC= uv sync
lock:
	UV_NO_SYNC= uv lock
lint:
	$(UV) ruff check . && $(UV) ruff format --check .
format:
	$(UV) ruff format . && $(UV) ruff check --fix .
typecheck:
	$(UV) pyright src scripts
test:
	$(UV) pytest -m "not slow" -q
test-all:
	$(UV) pytest -q
ci-local: lint typecheck test
manifests:
	$(UV) python scripts/prepare_dataset.py --adapter synthetic --dataset-id synthetic_a --dataset-id synthetic_b
validate-protocols:
	@for f in configs/protocol/*.yaml; do $(UV) python scripts/validate_protocol.py --path $$f || exit 1; done
verify-dod:
	$(UV) pytest tests/test_dod_files.py -v
mlflow-ui:
	$(UV) mlflow ui --backend-store-uri sqlite:///$(CURDIR)/mlruns.db --port 5000
clean-outputs:    ## only run outputs; never data/, mlruns, checkpoints
	rm -rf outputs multirun
