#!/bin/sh
set -eu

: "${OLLAMA_URL:=http://127.0.0.1:11434}"
: "${OLLAMA_MODEL:=smollm2:135m-instruct-q4_0}"
: "${OLLAMA_HOST:=${OLLAMA_URL#*://}}"
: "${OLLAMA_CONTEXT_LENGTH:=2048}"
: "${OLLAMA_NUM_PARALLEL:=1}"
: "${OLLAMA_MAX_LOADED_MODELS:=1}"
: "${OLLAMA_MAX_QUEUE:=8}"
OLLAMA_HOST="${OLLAMA_HOST%%/}"

export OLLAMA_HOST OLLAMA_CONTEXT_LENGTH OLLAMA_NUM_PARALLEL
export OLLAMA_MAX_LOADED_MODELS OLLAMA_MAX_QUEUE

case "$OLLAMA_HOST" in
  localhost:*|127.0.0.1:*) LOCAL_OLLAMA=1 ;;
  *) LOCAL_OLLAMA=0 ;;
esac

if [ "$LOCAL_OLLAMA" -eq 1 ] && command -v ollama >/dev/null 2>&1; then
  echo "[entrypoint] launching ollama on ${OLLAMA_HOST}"
  ( ollama serve >/tmp/ollama.log 2>&1 ) &
  OLLAMA_PID="$!"
elif [ "$LOCAL_OLLAMA" -eq 1 ]; then
  echo "[entrypoint] ollama binary missing"
  exit 1
else
  echo "[entrypoint] using external ollama at ${OLLAMA_HOST}"
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

  if ! ollama show "${OLLAMA_MODEL}" >/dev/null 2>&1; then
    echo "[entrypoint] pulling ${OLLAMA_MODEL}"
    if ! ollama pull "${OLLAMA_MODEL}" >/tmp/ollama-pull.log 2>&1; then
      cat /tmp/ollama-pull.log
      exit 1
    fi
  fi
  echo "[entrypoint] model ${OLLAMA_MODEL} ready"
fi

exec /app/.venv/bin/uvicorn halcyon.main:app --host 0.0.0.0 --port "${PORT:-8000}"
