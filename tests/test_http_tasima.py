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

import pytest

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
    Dockerfile bu yuzden host'u ACIKCA vermek zorunda.

    Test dolayli cagriyi TAKIP EDER (19 Agu 2026): `CMD` artik `main_http()`
    calistiriyor, yani host ve durumsuzluk bilgisi Dockerfile satirinda degil
    kaynakta duruyor. Yalnizca `CMD` satirini grepleyen bir test, giris noktasi
    bir fonksiyona tasindigi anda hicbir sey olcmezdi."""
    import inspect

    from edgar_mcp import server as sunucu

    docker = (KOK / "Dockerfile").read_text(encoding="utf-8")
    cmd = [s for s in docker.splitlines() if s.startswith("CMD")]
    assert cmd, "Dockerfile'da CMD yok"
    assert "main_http" in cmd[0], (
        f"CMD dogrulanan giris noktasini cagirmiyor: {cmd[0]}")

    kaynak = inspect.getsource(sunucu.main_http)
    assert 'host="0.0.0.0"' in kaynak or "host='0.0.0.0'" in kaynak, (
        "main_http loopback'e baglanir")
    assert "stateless_http=True" in kaynak, "main_http durumsuz degil"
    assert 'transport="streamable-http"' in kaynak, (
        "main_http streamable-HTTP calistirmiyor")


def test_konteyner_giris_noktasi_da_user_agent_olmadan_baslamiyor():
    """19 Agu 2026, denetimde bulundu: iki README, `server.json` ve arac
    aciklamalari "refuses to start without SEC_USER_AGENT" diyordu, ama koruma
    YALNIZCA `main()` icindeydi - stdio yolu. `Dockerfile`'in `CMD`'si `main()`i
    hic cagirmiyordu, dolayisiyla ortam degiskeni olmadan konteyner aciliyor,
    on iki araci ilan ediyor ve her canlilik kontrolunu geciyordu.

    15 Agu 2026'da (KK-32 §7) ayni hata bulunup duzeltilmisti; duzeltme tek
    tasimayi kapsiyordu ve ikinci tasima (KK-24) eklendiginde onunla birlikte
    tasinmadi. Bu test ikisini birden sabitliyor: hangi giris noktasi olursa
    olsun, ortam degiskeni yoksa surec ACILMAZ."""
    import edgar_mcp.server as sunucu

    # `mcp.run` degistiriliyor: koruma kaldirilmis olsaydi gercek sunucu
    # ayaga kalkar ve test ASILIRDI - kirmizi degil, sonsuz. Asilan bir test
    # de olcmeyen bir testtir (KK-41'in "olculemedi" ayrimi).
    calisti: list[str] = []

    def sahte_run(*a: object, **k: object) -> None:
        calisti.append("run")

    for ad in ("main", "main_http"):
        giris = getattr(sunucu, ad)
        onceki = os.environ.pop("SEC_USER_AGENT", None)
        gercek_run = sunucu.mcp.run
        sunucu.mcp.run = sahte_run          # type: ignore[method-assign]
        calisti.clear()
        try:
            with pytest.raises(RuntimeError) as hata:
                giris()
        finally:
            sunucu.mcp.run = gercek_run     # type: ignore[method-assign]
            if onceki is not None:
                os.environ["SEC_USER_AGENT"] = onceki
        assert "SEC_USER_AGENT" in str(hata.value), (
            f"{ad}() eksik ortam degiskenini eyleme donusturulebilir sekilde "
            f"bildirmiyor: {hata.value}")
        assert calisti == [], (
            f"{ad}() ortam degiskeni yokken tasimayi YINE DE baslatti")


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


def test_dockerfile_pyprojectin_istedigi_dosyalari_kopyaliyor():
    """18 Agu 2026, denetimde uretildi: imaj HIC DERLENMIYORDU. `Dockerfile`
    yalnizca `pyproject.toml README.md src/` kopyaliyordu ama `pyproject.toml`
    `license = { file = "LICENSE" }` diyor; hatchling o dosyayi build aninda
    ariyor ve `OSError: License file does not exist: LICENSE` veriyordu.

    Iki README, PUBLISHING.md ve vaka calismasi calismayan bir komut
    gosteriyordu - P-20'nin ("belgelenen dagitim yolu hic calistirilmadi")
    tekrari. Bu test metni greplemekle yetinmiyor: `pyproject.toml`'un dosya
    olarak ISTEDIGI her yolun konteynere kopyalandigini kontrol ediyor, yani
    yarin `readme` ya da baska bir alan degistiginde de tutuyor."""
    import re

    proje = (KOK / "pyproject.toml").read_text(encoding="utf-8")
    docker = (KOK / "Dockerfile").read_text(encoding="utf-8")

    kopyalanan: set[str] = set()
    for satir in docker.splitlines():
        if satir.strip().startswith("COPY "):
            parcalar = satir.split()[1:-1]
            kopyalanan.update(p.strip("./") for p in parcalar)

    # `license = { file = "X" }` ve `readme = "X"` gibi dosya referanslari
    istenen = set(re.findall(r'file\s*=\s*"([^"]+)"', proje))
    istenen |= set(re.findall(r'^readme\s*=\s*"([^"]+)"', proje, re.M))
    assert istenen, "pyproject.toml hicbir dosyaya atif yapmiyor - test bos"

    eksik = [d for d in istenen if d not in kopyalanan]
    assert not eksik, (
        f"pyproject.toml bu dosyalari istiyor ama Dockerfile kopyalamiyor: "
        f"{eksik}. Imaj build aninda patlar.")


def test_sunucunun_bildirdigi_ad_dagitim_adiyla_ayni():
    """19 Agu yeniden adlandirmasi (KK-50) el sikismada bildirilen adi atlamisti:
    sunucu kendini `sec-edgar` diye tanitiyordu. 28 Eyl 2026'da duzeltildi
    (KK-55). Ad `pyproject.toml`'dan okunuyor - iki yerde elle tutulan bir
    ad, bir sonraki yeniden adlandirmada yine ayrisir."""
    import tomllib

    from edgar_mcp.server import mcp
    ad = tomllib.loads((KOK / "pyproject.toml").read_text(encoding="utf-8"))["project"]["name"]
    assert mcp.name == ad, (mcp.name, ad)


def test_inspector_giris_noktasi_da_user_agent_olmadan_baslamiyor(monkeypatch):
    """`mcp dev` Inspector'i `mcp run inspector.py` ile baslatiyor; bu yol
    `main()`'i hic cagirmiyor. 28 Eyl 2026 bagimsiz denetimi: `initialize` ve
    `tools/list` User-Agent olmadan basariliydi, hata ancak ilk arac
    cagrisinda geliyordu. Ucuncu giris noktasi, P-40'in ucuncu hali."""
    import runpy

    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    from edgar_mcp import server
    monkeypatch.setattr(server, "_client", None)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        runpy.run_path(str(KOK / "inspector.py"))


def test_belgelenen_mcp_dev_komutu_sunucuyu_gercekten_yukluyor(monkeypatch):
    """28 Eyl 2026, denetimde uretildi: iki README ve CLAUDE.md
    `uv run mcp dev src/edgar_mcp/server.py` yaziyordu. SDK verilen dosyayi
    paket DISINDA `server_module` adiyla yukluyor ve `server.py`'nin goreli
    import'u `ImportError` veriyordu - belgelenen gelistirme komutu hic
    calismamisti (P-14, P-20).

    Belgelerde yazan HER `mcp dev` hedefi, SDK'nin kendi yukleyicisiyle
    yukleniyor. Yalnizca `inspector.py`'yi sinamak yetmez: belge baska bir
    dosyayi gosterirse test onu yuklemeli."""
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@ornek.com")
    # SDK'nin yukleyicisi dosyanin dizinini sys.path'e kalici olarak ekliyor;
    # test bittiginde geri alinmali.
    monkeypatch.setattr(sys, "path", list(sys.path))
    from mcp.cli.cli import _import_server
    from mcp.server import MCPServer

    # Yalnizca KOD BLOKLARI taraniyor: karar kayitlari eski, bozuk komutu
    # tarihce olarak alintiliyor (KK-55) ve o metin bir komut degil.
    hedefler: set[str] = set()
    for ad in ("README.md", "README.tr.md", "CLAUDE.md"):
        metin = (KOK / ad).read_text(encoding="utf-8")
        for blok in re.findall(r"```[a-z]*\n(.*?)```", metin, re.DOTALL):
            hedefler |= set(re.findall(r"mcp dev (\S+\.py)", blok))
    assert hedefler, "belgelerde `mcp dev` komutu bulunamadi"
    for yol in sorted(hedefler):
        try:
            sunucu = _import_server((KOK / yol).resolve(), None)
        except (ImportError, SystemExit) as e:
            pytest.fail(f"belgelenen `mcp dev {yol}` yuklenemiyor: {e!r}")
        assert isinstance(sunucu, MCPServer), (yol, type(sunucu))
