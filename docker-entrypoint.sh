#!/bin/sh
set -eu

: "${OLLAMA_URL:=http://127.0.0.1:11434}"
: "${OLLAMA_MODEL:=llama3.1:8b}"
: "${OLLAMA_HOST:=${OLLAMA_URL#*://}}"
OLLAMA_HOST="${OLLAMA_HOST%%/}"

export OLLAMA_HOST

if command -v ollama >/dev/null 2>&1; then
  echo "[entrypoint] launching ollama on ${OLLAMA_HOST}"
  ( ollama serve >/tmp/ollama.log 2>&1 ) &
  OLLAMA_PID="$!"
else
  echo "[entrypoint] ollama binary missing"
  OLLAMA_PID=""
fi

if [ -n "$OLLAMA_PID" ]; then
  i=0
  while [ "$i" -lt 30 ]; do
    if curl -fsS "http://${OLLAMA_HOST}/api/tags" >/tmp/ollama-tags.json 2>/dev/null; then
      break
    fi
    sleep 1
    i=$((i + 1))
  done

  if [ "$i" -ge 30 ]; then
    echo "[entrypoint] ollama did not report ready; continuing anyway"
  else
    echo "[entrypoint] ollama ready"
  fi

  (ollama pull "${OLLAMA_MODEL}" >/tmp/ollama-pull.log 2>&1 || true) &
  trap 'trap - INT TERM; kill "$OLLAMA_PID" 2>/dev/null || true' INT TERM
  trap 'trap - EXIT; kill "$OLLAMA_PID" 2>/dev/null || true' EXIT
fi

exec uv run uvicorn halcyon.main:app --host 0.0.0.0 --port 8000
