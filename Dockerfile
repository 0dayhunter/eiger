FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv
# Install curl + certificates for on-container Ollama bootstrap on cloud hosts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
# Install Ollama runtime so web+llm can start from one container on Render.
RUN curl -fsSL https://ollama.com/install.sh | sh
COPY pyproject.toml uv.lock ./
COPY halcyon ./halcyon
COPY labs ./labs
COPY mcp.json ./mcp.json
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN uv sync --frozen --no-dev
# Bake the ONNX embedding model into the image so the first /api/ask never triggers
# a slow, thrashing runtime download. Uses the same default chromadb EF the app uses.
RUN uv run python -c "import chromadb; c=chromadb.Client().get_or_create_collection('warm'); c.add(ids=['1'], documents=['warmup']); c.query(query_texts=['warmup'], n_results=1)"
EXPOSE 8000
RUN chmod +x /docker-entrypoint.sh
CMD ["/docker-entrypoint.sh"]
