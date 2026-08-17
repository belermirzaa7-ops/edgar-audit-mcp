"""HTTP tasimasi gercekten ayaga kalkiyor mu, ve Dockerfile onu dogru cagiriyor mu.

Neden var (13 Agu 2026): README ve CLAUDE.md Docker uzerinden streamable-HTTP
kullanimini VAAT EDIYORDU ama bu yol hic calistirilmamisti. SDK'nin
`run_streamable_http_async` varsayilani `host="127.0.0.1"`; konteyner icinde
bu yalnizca loopback'e baglanir, yani `docker run -p 8000:8000` disaridan
bos doner. Belge davranisi anlatiyordu, davranis oyle degildi (P-14, P-20).

Bu dosya SEC'e cikmaz: `tools/list` ag erisimi gerektirmiyor.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

KOK = pathlib.Path(__file__).resolve().parents[1]


def _bos_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _sunucu(port: int, host: str = "127.0.0.1", stateless: bool = True):
    kod = (
        "from edgar_mcp.server import mcp; "
        f"mcp.run(transport='streamable-http', host='{host}', port={port}, "
        f"stateless_http={stateless})"
    )
    env = {**os.environ,
           "SEC_USER_AGENT": "Test Runner test@example.com",
           "PYTHONPATH": str(KOK / "src"),
           "PYTHONUNBUFFERED": "1"}
    return subprocess.Popen(
        [sys.executable, "-c", kod], env=env, cwd=str(KOK),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )


def _tools_list(port: int, sure: float = 25.0) -> str:
    """Sunucu ayaga kalkana kadar dener; ilk basarili yanitin govdesini doner."""
    istek = urllib.request.Request(
        f"http://127.0.0.1:{port}/mcp",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    son = None
    bitis = time.monotonic() + sure
    while time.monotonic() < bitis:
        try:
            with urllib.request.urlopen(istek, timeout=5) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            son = e
            time.sleep(0.5)
    raise AssertionError(f"HTTP tasimasi {sure}s icinde cevap vermedi: {son}")


def test_http_tasimasi_araclari_el_sikismasiz_listeler():
    """2026-07-28 spesifikasyonu: durumsuz cekirdek. initialize/Mcp-Session-Id
    olmadan tools/list cevaplanmali."""
    port = _bos_port()
    p = _sunucu(port)
    try:
        govde = _tools_list(port)
        assert "sec_edgar_get_concept_series" in govde
        assert govde.count("sec_edgar_") >= 6, govde[:300]
    finally:
        p.terminate()
        try:
            p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


def test_dockerfile_loopback_disina_baglaniyor():
    """SDK varsayilani 127.0.0.1. Konteynerde bu, yayinlanan portu olu birakir.
    Dockerfile bu yuzden host'u ACIKCA vermek zorunda; bu test o satirin
    sessizce geri alinmasini engeller."""
    docker = (KOK / "Dockerfile").read_text(encoding="utf-8")
    cmd = [s for s in docker.splitlines() if s.startswith("CMD")]
    assert cmd, "Dockerfile'da CMD yok"
    assert "host='0.0.0.0'" in cmd[0], f"CMD loopback'e baglanir: {cmd[0]}"
    assert "stateless_http=True" in cmd[0], f"CMD durumsuz degil: {cmd[0]}"


def test_sdk_varsayilani_hala_loopback():
    """Yukaridaki testin GEREKCESI olculur: SDK varsayilani degisirse bu test
    kirmiziya doner ve Dockerfile'daki acik host gereksiz hale gelmis olur.
    Varsayimi belgeye degil, imzaya bagliyoruz."""
    import inspect

    from mcp.server import MCPServer

    imza = inspect.signature(MCPServer.run_streamable_http_async)
    assert imza.parameters["host"].default == "127.0.0.1", (
        "SDK varsayilani degismis - Dockerfile yorumu ve P-20 guncellenmeli"
    )


def test_readme_docker_komutu_calisan_bicimde_belgeleniyor():
    """Belge ile davranis ortusmeli (§1): README'deki docker run komutu portu
    yayinlamali, yoksa okuyucu calismayan bir komut kopyalar."""
    for ad in ("README.md", "README.tr.md"):
        metin = (KOK / ad).read_text(encoding="utf-8")
        satirlar = [s for s in metin.splitlines() if "docker run" in s]
        assert satirlar, f"{ad}: docker run komutu yok"
        for s in satirlar:
            assert re.search(r"-p\s+\d+:8000", s), f"{ad}: port yayinlanmamis -> {s}"


def test_stdio_tasimasi_resmi_istemciyle_araclari_listeliyor():
    """Claude Desktop'in kullandigi yol tam olarak budur:
    `python -m edgar_mcp.server` + stdio. Elle JSON-RPC cercevesi kurmak
    yerine SDK'nin KENDI istemcisi kullaniliyor - elle kurulan cerceve
    2026-07-28 wire kurallarini (params/_meta) tasimadigi icin sunucuyu degil
    testi yanlis yapar.

    Bu test ayni zamanda `python -m` giris noktasini sabitler: pyproject'teki
    konsol scripti ve README'deki Claude Desktop config'i ona bagli.
    """
    import asyncio

    async def calistir():
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        env = {**os.environ,
               "SEC_USER_AGENT": "Test Runner test@example.com",
               "PYTHONPATH": str(KOK / "src")}
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "edgar_mcp.server"], env=env,
        )
        async with stdio_client(params) as (oku, yaz), ClientSession(oku, yaz) as oturum:
            await oturum.initialize()
            return [t.name for t in (await oturum.list_tools()).tools]

    adlar = asyncio.run(calistir())
    # Arac kumesi test_server.py'deki test_arac_isimleri_servis_onekli ile
    # sabitleniyor; burada GERCEK tel uzerinden ayni kumenin geldigi dogrulanir.
    assert "sec_edgar_get_concept_series" in adlar
    assert "sec_edgar_get_fact_revisions" in adlar
    assert len(adlar) == 12, adlar
    assert all(a.startswith("sec_edgar_") for a in adlar), adlar
