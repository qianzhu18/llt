#!/usr/bin/env bash
# Local dev / one-shot start
cd "$(dirname "$0")"
source .venv/bin/activate
exec uvicorn app.main:app --host "${APP_HOST:-127.0.0.1}" --port "${APP_PORT:-10800}" --reload
