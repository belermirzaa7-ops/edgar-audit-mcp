FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Streamable HTTP transport (2026-07-28 spesifikasyonu, stateless)
EXPOSE 8000
CMD ["python", "-c", "from edgar_mcp.server import mcp; mcp.run(transport='streamable-http')"]
