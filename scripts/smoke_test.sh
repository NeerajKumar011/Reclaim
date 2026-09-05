#!/usr/bin/env bash
set -eo pipefail

echo "=========================================================="
echo "  RECLAIM Clean-Clone Smoke Test Runner"
echo "=========================================================="

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"

cd "$PROJECT_ROOT"

if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_BIN=".venv/Scripts/python.exe"
else
    PYTHON_BIN="python"
fi

export PYTHONPATH="$PROJECT_ROOT"
"$PYTHON_BIN" "$SCRIPT_DIR/smoke_test.py"
