FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# MCP registry ownership check for an OCI package: the annotation must equal the
# `name` field of server.json. Measured against the registry's own package-type
# documentation (16 Aug 2026), not recalled.
LABEL io.modelcontextprotocol.server.name="io.github.belermirzaa7-ops/edgar-audit-mcp"

# LICENSE de kopyalaniyor: `pyproject.toml` `license = { file = "LICENSE" }`
# diyor ve hatchling onu build aninda ARIYOR. Eksikken imaj hic derlenmiyordu
# (`OSError: License file does not exist: LICENSE`) - iki README, PUBLISHING.md
# ve vaka calismasi calismayan bir komut gosteriyordu. P-20'nin tekrari:
# belgelenen dagitim yolu calistirilmadan dogru sayilmis.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

# Streamable HTTP transport (2026-07-28 spesifikasyonu, stateless).
#
# host="0.0.0.0" ZORUNLU: SDK varsayilani 127.0.0.1'dir ve konteyner icinde
# yalnizca loopback'e baglanir - `docker run -p 8000:8000` disaridan hicbir
# sey goremez. Olculdu, varsayilmadi (bkz. PATTERNS.md P-20).
# stateless_http=True: 2026-07-28 spesifikasyonunun durumsuz cekirdegi;
# initialize/Mcp-Session-Id el sikismasi olmadan tools/list cevaplanir.
EXPOSE 8000
CMD ["python", "-c", "from edgar_mcp.server import mcp; mcp.run(transport='streamable-http', host='0.0.0.0', stateless_http=True)"]
