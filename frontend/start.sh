#!/bin/bash

cd "$(dirname "$0")"

set -euo pipefail

# LlamaStack endpoint for models, vector DBs, and tool groups.
# Override with: LLAMA_STACK_ENDPOINT=http://your-url ./start.sh
if [ -z "${LLAMA_STACK_ENDPOINT:-}" ]; then
    # Auto-detect from OpenShift route if oc is available and logged in
    if command -v oc &>/dev/null && oc whoami &>/dev/null 2>&1; then
        ROUTE_HOST=$(oc get route llamastack-http -n "${NAMESPACE:-f5-ai-security}" -o jsonpath='{.spec.host}' 2>/dev/null || true)
        if [ -n "$ROUTE_HOST" ]; then
            export LLAMA_STACK_ENDPOINT="http://$ROUTE_HOST"
        fi
    fi
fi
export LLAMA_STACK_ENDPOINT="${LLAMA_STACK_ENDPOINT:-http://llamastack:8321}"
echo "[INFO] LlamaStack endpoint: $LLAMA_STACK_ENDPOINT"

# Ensure project dependencies and the local venv exist.
uv sync

PYTHON_BIN=".venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo "[ERROR] Expected Python interpreter not found: $PYTHON_BIN"
    exit 1
fi

echo "[INFO] Using Python interpreter: $("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
echo "[INFO] Python version: $("$PYTHON_BIN" --version)"

"$PYTHON_BIN" -m streamlit run llama_stack_ui/distribution/ui/app.py --server.port=8501
