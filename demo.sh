#!/usr/bin/env bash
# demo.sh — prove the full break -> harden -> refuse loop, headless, in one command.
# No paid API keys required: runs in CEKURA_MOCK mode. (The live Nemotron
# patch-writer still fires if NVIDIA_API_KEY is set; otherwise it uses the
# cached fallback patch — identical visible outcome.)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8080}"
PY="${PYTHON:-.venv/bin/python}"
[ -x "$PY" ] || PY="python3"

echo "==> Starting SENTRY orchestrator (MOCK) on :$PORT"
CEKURA_MOCK=1 PORT="$PORT" "$PY" -m uvicorn orchestrator.main:app \
  --host 127.0.0.1 --port "$PORT" --log-level warning &
ORCH_PID=$!
trap 'kill $ORCH_PID 2>/dev/null || true' EXIT

# wait for the orchestrator to answer
for _ in $(seq 1 30); do
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/status"; then break; fi
  sleep 0.5
done

echo "==> Running the red->green proof"
CEKURA_MOCK=1 PORT="$PORT" "$PY" prove_loop.py
