.PHONY: setup dev run demo soki agent-cli terminal terminal-run terminal-demo terminal-check test lint backend frontend android-build android-test android-link android-install worker clean

PYTHONPATH := packages/shared/src:apps/api/src
TUI_PYTHONPATH := packages/shared/src:apps/terminal-tui/src

setup:
	uv sync
	npm ci --prefix apps/soki-code-web

dev: run

run:
	./infrastructure/scripts/run.sh

demo:
	./infrastructure/scripts/demo.sh

soki:
	./soki

agent-cli:
	PYTHONPATH=$(PYTHONPATH) uv run python -m qforge.gateway_cli $(ARGS)

terminal:
	PYTHONPATH=$(TUI_PYTHONPATH) uv run python -m qforge_tui.main

terminal-run:
	./infrastructure/scripts/terminal-run.sh

terminal-demo:
	./infrastructure/scripts/terminal-demo.sh

terminal-check:
	PYTHONPATH=$(TUI_PYTHONPATH) uv run python -m qforge_tui.main --check

test:
	PYTHONPATH=$(PYTHONPATH) uv run pytest
	npm test --prefix apps/soki-code-web
	cd apps/soki-code-android && ./gradlew testDebugUnitTest

lint:
	uv run ruff check .
	uv run mypy packages/shared/src apps/api/src apps/worker/src apps/terminal-tui/src
	npm run lint --prefix apps/soki-code-web

backend:
	PYTHONPATH=$(PYTHONPATH) uv run uvicorn qforge_api.main:app --host 127.0.0.1 --port 8000 --reload

frontend:
	npm run dev --prefix apps/soki-code-web

android-build:
	cd apps/soki-code-android && ./gradlew assembleDebug

android-test:
	cd apps/soki-code-android && ./gradlew testDebugUnitTest

android-link:
	adb reverse tcp:8000 tcp:8000
	@echo "Android can now reach the laptop API at http://127.0.0.1:8000"

android-install: android-build android-link
	adb install -r apps/soki-code-android/app/build/outputs/apk/debug/app-debug.apk

worker:
	PYTHONPATH=packages/shared/src:apps/worker/src uv run celery -A qforge_worker.main:worker worker --loglevel=INFO

clean:
	rm -rf apps/soki-code-web/dist .mypy_cache .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
