#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR="${VENV_DIR:-.venv}"
if [ -n "${PYTHON_BIN:-}" ]; then
  BOOTSTRAP_PYTHON="$PYTHON_BIN"
elif command -v python3.12 >/dev/null 2>&1; then
  BOOTSTRAP_PYTHON="python3.12"
else
  BOOTSTRAP_PYTHON="python3"
fi
VENV_PYTHON="$VENV_DIR/bin/python"
REQ_STAMP="$VENV_DIR/.requirements.sha256"

if ! command -v "$BOOTSTRAP_PYTHON" >/dev/null 2>&1; then
  echo "error: bootstrap python '$BOOTSTRAP_PYTHON' not found in PATH" >&2
  exit 1
fi

venv_python_works() {
  [ -x "$VENV_PYTHON" ] && "$VENV_PYTHON" -c "import sys" >/dev/null 2>&1
}

ensure_venv() {
  if venv_python_works; then
    return
  fi

  echo "Rebuilding local virtualenv in $VENV_DIR ..."
  rm -rf "$VENV_DIR"
  "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
}

requirements_hash() {
  "$BOOTSTRAP_PYTHON" - <<'PY'
from hashlib import sha256
from pathlib import Path

print(sha256(Path("requirements.txt").read_bytes()).hexdigest())
PY
}

deps_ready() {
  "$VENV_PYTHON" -c "import fastapi, uvicorn, sqlalchemy, pydantic_settings" >/dev/null 2>&1
}

ensure_venv

CURRENT_REQ_HASH="$(requirements_hash)"
INSTALLED_REQ_HASH="$(cat "$REQ_STAMP" 2>/dev/null || true)"

if ! deps_ready || [ "$CURRENT_REQ_HASH" != "$INSTALLED_REQ_HASH" ]; then
  echo "Installing Python dependencies ..."
  "$VENV_PYTHON" -m pip install -r requirements.txt
  printf '%s\n' "$CURRENT_REQ_HASH" > "$REQ_STAMP"
fi

UVICORN_ARGS=(
  app.main:app
  --host "${APP_HOST:-127.0.0.1}"
  --port "${APP_PORT:-10800}"
)

case "${APP_RELOAD:-1}" in
  0|false|FALSE|no|NO)
    ;;
  *)
    UVICORN_ARGS+=(--reload)
    ;;
esac

exec "$VENV_PYTHON" -m uvicorn "${UVICORN_ARGS[@]}"
