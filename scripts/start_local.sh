#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo "Create .venv and install this project first; see README.md." >&2
  exit 1
fi
exec .venv/bin/python -m uvicorn agent.main:app --host 127.0.0.1 --port "${PORT:-8090}"
