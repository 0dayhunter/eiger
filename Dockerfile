FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv
# Install curl + certificates for on-container Ollama bootstrap on cloud hosts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl zstd \
    && rm -rf /var/lib/apt/lists/*
# Install Ollama runtime so web+llm can start from one container on Render.
RUN curl -fsSL https://ollama.com/install.sh | sh
ARG BAKED_OLLAMA_MODEL=smollm2:135m-instruct-q4_0
ENV OLLAMA_MODEL=${BAKED_OLLAMA_MODEL} \
    OLLAMA_URL=http://127.0.0.1:11434 \
    OLLAMA_CONTEXT_LENGTH=2048 \
    OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_MAX_QUEUE=8
# Render's filesystem is ephemeral. Bake a small, tool-capable model into the image so
# cold starts never expose the web app before its default model is available.
RUN OLLAMA_HOST=127.0.0.1:11434 sh -ec '\
    ollama serve >/tmp/ollama-build.log 2>&1 & \
    pid=$!; \
    trap "kill $pid 2>/dev/null || true" EXIT; \
    i=0; \
    until curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do \
      i=$((i + 1)); \
      if [ "$i" -ge 30 ]; then cat /tmp/ollama-build.log; exit 1; fi; \
      sleep 1; \
    done; \
    ollama pull "$OLLAMA_MODEL"'
COPY pyproject.toml uv.lock ./
COPY halcyon ./halcyon
COPY labs ./labs
COPY mcp.json ./mcp.json
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN uv sync --frozen --no-dev
# Bake the ONNX embedding model into the image so the first /api/ask never triggers
# a slow, thrashing runtime download. Uses the same default chromadb EF the app uses.
RUN .venv/bin/python -c "import chromadb; c=chromadb.Client().get_or_create_collection('warm'); c.add(ids=['1'], documents=['warmup']); c.query(query_texts=['warmup'], n_results=1)"
EXPOSE 8000
RUN chmod +x /docker-entrypoint.sh
CMD ["/docker-entrypoint.sh"]
