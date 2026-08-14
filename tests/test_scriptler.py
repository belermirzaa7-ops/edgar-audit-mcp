"""dene.py ve dogrula.py sahte veriyle uctan uca calisiyor mu.

Bu scriptler test kapsami disindaydi ve bir alan adi degisikliginde
(resolved_concept -> resolved_concepts) calisma aninda AttributeError
veriyordu. Testler yesilken script cokuyordu.
"""
from __future__ import annotations

import pathlib
import sys

import httpx
import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "src"))
sys.path.insert(0, str(KOK / "tests"))

from test_server import handler  # noqa: E402


def _sahte_istemci():
    from edgar_mcp.client import EdgarClient

    c = EdgarClient()
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "Test Runner test@example.com"},
    )
    return c


def _calistir(script: str, monkeypatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")
    from edgar_mcp import server as s

    s._client = _sahte_istemci()

    yol = KOK / script
    kaynak = yol.read_text(encoding="utf-8")
    # asyncio.run(...) satirini cikarip main'i biz cagiriyoruz
    kaynak = kaynak.replace("asyncio.run(main())", "").replace("asyncio.run(hepsi())", "")
    g: dict = {"__name__": "sahte", "__file__": str(yol)}
    exec(compile(kaynak, str(yol), "exec"), g)  # noqa: S102
    assert "main" in g, f"{script} icinde main() yok"

    import asyncio

    asyncio.run(g["main"]())


@pytest.mark.parametrize("script", ["dene.py"])
def test_script_sahte_veriyle_cokmeden_calisiyor(script, monkeypatch, capsys):
    _calistir(script, monkeypatch)
    cikti = capsys.readouterr().out
    assert "SIRKET" in cikti
    assert "Apple Inc." in cikti


def test_scriptler_var_olmayan_alana_erismiyor(monkeypatch, capsys):
    """Model alanlari yeniden adlandirildiginda scriptler sessizce degil,
    gurultulu bicimde kirilmali - ve bu test onu CI'da yakalamali."""
    _calistir("dene.py", monkeypatch)
    cikti = capsys.readouterr().out
    assert "cozulen etiket:" in cikti
    assert "toplam donem:" in cikti


# =============================================== arac/tani.py (KO olayi, 13 Agu)
sys.path.insert(0, str(KOK))


def _tani_modulu():
    import importlib

    return importlib.import_module("arac.tani")


def test_tani_dolu_yaniti_ozetliyor(monkeypatch, capsys):
    """Tani scripti calisan bir yanitta satir sayisini ve eksik alanlari
    raporlamali - KO olayinda ihtiyac duyulan olcum tam olarak buydu."""
    import asyncio

    from test_server import GERCEK_GELIR_ETIKETI

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")
    mod = _tani_modulu()
    monkeypatch.setattr(mod, "EdgarClient", _sahte_istemci)
    monkeypatch.setattr(sys, "argv", ["tani.py", "AAPL", GERCEK_GELIR_ETIKETI])

    kod = asyncio.run(mod.main())
    cikti = capsys.readouterr().out
    assert kod == 0, cikti
    assert "HTTP       : 200" in cikti
    assert "USD: 6 satir" in cikti
    assert "'end' eksik: 0" in cikti


def _istemci_ile(ozel_handler):
    def istemci():
        from edgar_mcp.client import EdgarClient

        c = EdgarClient()
        c._http = httpx.AsyncClient(
            transport=httpx.MockTransport(ozel_handler),
            headers={"User-Agent": "Test Runner test@example.com"},
        )
        return c

    return istemci


# KO'nun GERCEK yaniti (13 Agu 2026, ham govde): units.USD var ama icinde
# satir yok - ve dizi DEGIL, bos SOZLUK olarak geliyor:
#   {"cik":21344,...,"units":{"USD":{}}}
# Ilk sahte veri once `units: {}`, sonra `{"USD": []}` doneriyordu; ikisi de
# gercegin sozlesmesini taklit etmiyordu (P-4).
KO_BOS = {"cik": 21344, "taxonomy": "us-gaap", "tag": "Assets",
          "label": "Assets", "entityName": "COCA COLA CO", "units": {"USD": {}}}


def test_tani_birim_var_satir_yok_durumunu_isaretliyor(monkeypatch, capsys):
    """KO'nun belirtisi: HTTP 200, dogru label, units.USD VAR, icinde 0 satir.
    Script bunu sessizce gecerse hicbir ise yaramaz."""
    import asyncio

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")

    def bos_handler(request: httpx.Request) -> httpx.Response:
        if "companyconcept" in str(request.url):
            return httpx.Response(200, json=KO_BOS)
        return handler(request)

    mod = _tani_modulu()
    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(bos_handler))
    monkeypatch.setattr(sys, "argv", ["tani.py", "AAPL", "Assets"])

    kod = asyncio.run(mod.main())
    cikti = capsys.readouterr().out
    assert kod == 1, cikti
    assert "USD: 0 satir" in cikti
    assert "SATIR YOK" in cikti


def test_tani_tamamen_bos_units_durumunu_da_isaretliyor(monkeypatch, capsys):
    import asyncio

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")

    def bos_handler(request: httpx.Request) -> httpx.Response:
        if "companyconcept" in str(request.url):
            return httpx.Response(200, json={**KO_BOS, "units": {}})
        return handler(request)

    mod = _tani_modulu()
    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(bos_handler))
    monkeypatch.setattr(sys, "argv", ["tani.py", "AAPL", "Assets"])

    assert asyncio.run(mod.main()) == 1
    assert "units BOS" in capsys.readouterr().out


def test_matris_farki_yaratan_degiskeni_gosteriyor(monkeypatch, capsys):
    """Matris modunun ISI bu: ayni veriyi farkli kosullarda isteyip hangi
    kosulun sonucu degistirdigini soylemek. Burada yalnizca sorgu parametresi
    eklenmis istek dolu donuyor (kenar onbellegi hipotezinin imzasi); test
    scriptin bunu FARK ETTIGINI dogruluyor, tahmin ettigini degil."""
    import asyncio

    from test_server import CONCEPT

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")

    def onbellek_handler(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "companyconcept" in u:
            if "tani=" in u:
                return httpx.Response(200, json=CONCEPT, headers={"x-cache": "MISS"})
            return httpx.Response(200, json=KO_BOS,
                                  headers={"x-cache": "HIT", "age": "51231"})
        return handler(request)

    mod = _tani_modulu()
    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(onbellek_handler))
    monkeypatch.setattr(sys, "argv", ["tani.py", "AAPL", "Assets", "--matris"])

    kod = asyncio.run(mod.main())
    cikti = capsys.readouterr().out
    assert kod == 1, cikti
    assert "temel=0" in cikti and "tekrar=0" in cikti
    assert "onbellek-bypass=6" in cikti
    assert "'onbellek-bypass'" in cikti, "farki yaratan kosul adiyla anilmali"
    assert "age           : 51231" in cikti, "onbellek basliklari yazilmali"


def test_matris_iki_ucun_tutarsizligini_ayirt_ediyor(monkeypatch, capsys):
    """companyconcept her kosulda bos ama companyfacts ayni etiket icin dolu:
    bu, 'SEC'te veri yok' (H4) ile karistirilmamasi gereken durum."""
    import asyncio

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")

    def hep_bos(request: httpx.Request) -> httpx.Response:
        if "companyconcept" in str(request.url):
            return httpx.Response(200, json=KO_BOS)
        return handler(request)      # companyfacts: FACTS, Assets -> 1 satir

    mod = _tani_modulu()
    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(hep_bos))
    monkeypatch.setattr(sys, "argv", ["tani.py", "AAPL", "Assets", "--matris"])

    kod = asyncio.run(mod.main())
    cikti = capsys.readouterr().out
    assert kod == 1, cikti
    assert "companyfacts=1" in cikti
    assert "TUTARSIZ" in cikti


def test_tarama_etkilenen_sirketleri_sayiyor(monkeypatch, capsys):
    """Tarama modu 'kac sirket etkileniyor' sorusunu SAYARAK cevaplamali.
    Sahte ortamda yalnizca AAPL cozuluyor ve companyconcept'i bos donuyor;
    beklenen: AAPL 'yedek uc gerekli' diye isaretlensin, cozulemeyen
    tickerlar ozete etkilenen olarak GIRMESIN."""
    import asyncio

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")

    def h(request: httpx.Request) -> httpx.Response:
        if "companyconcept" in str(request.url):
            return httpx.Response(200, json=KO_BOS)
        return handler(request)

    mod = _tani_modulu()
    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(h))
    monkeypatch.setattr(mod, "TARAMA_TICKERLARI", ["AAPL", "YOKBOYLE"])
    monkeypatch.setattr(sys, "argv", ["tani.py", "--tarama"])

    kod = asyncio.run(mod.main())
    cikti = capsys.readouterr().out
    assert kod == 1, cikti
    assert "yedek uc gerekli" in cikti
    assert "ticker cozulemedi" in cikti
    assert "1/1 sirkette" in cikti, "cozulemeyen ticker paydaya girmis"


def test_envanter_taksonomileri_ve_ilginc_etiketleri_listeliyor(monkeypatch, capsys):
    """Envanter modu, sunucunun BUGUN okumadigi taksonomileri gorunur kilmali -
    Tesla raporunda segment kirilimina ulasamamamizin sebebi tam olarak buydu.
    Sahte veride ikinci bir taksonomi ve segment etiketi var."""
    import asyncio

    from test_server import FACTS

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")

    ZENGIN = {
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": FACTS["facts"]["us-gaap"],
            "dei": {"EntityPublicFloat": {"label": "Entity Public Float",
                                          "units": {"USD": [{"end": "2025-06-30",
                                                             "val": 1}]}}},
            "aapl": {"SegmentRevenueAutomotive": {"label": "Segment Revenue",
                                                  "units": {"USD": [{"end": "2025-12-31",
                                                                     "val": 2}]}}},
        },
    }

    def h(request: httpx.Request) -> httpx.Response:
        if "companyfacts" in str(request.url):
            return httpx.Response(200, json=ZENGIN)
        return handler(request)

    mod = _tani_modulu()
    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(h))
    monkeypatch.setattr(sys, "argv", ["tani.py", "AAPL", "--envanter"])

    kod = asyncio.run(mod.main())
    cikti = capsys.readouterr().out
    assert kod == 0, cikti
    assert "'us-gaap'" in cikti and "'dei'" in cikti and "'aapl'" in cikti
    assert "SegmentRevenueAutomotive" in cikti
    assert "EntityPublicFloat" in cikti
    assert "2 ilginc etiket" in cikti


def test_enjeksiyon_bozuk_sozdizimini_koruma_eksigi_sanmiyor():
    """14 Agu 2026: bir enjeksiyonun degistirme metni parantezi bozdu; dosya
    import edilemedi, ilgisiz testler kirmiziya dondu ve harness bunu
    'KORUMASIZ' diye raporladi. 'Koruma yok' ile 'enjeksiyon hatali' ayni
    gorunmemeli."""
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    assert mod.sozdizimi_gecerli("src/x.py", "def f():\n    return 1\n")
    assert not mod.sozdizimi_gecerli("src/x.py", "def f():\n    return [1\n")
    # Python olmayan dosyalar muaf: Dockerfile da enjeksiyon hedefi
    assert mod.sozdizimi_gecerli("Dockerfile", "CMD [\"python\", \"-c\", \"x(\"]")


def test_enjeksiyon_ayni_anda_iki_kez_calismiyor(tmp_path, monkeypatch):
    """14 Agu 2026 olayi: iki harness ayni anda calisti, biri dosyayi bozmusken
    oteki test kosturdu, ilgisiz testler kirmiziya dondu ve calisma dizininde
    enjekte edilmis bir dosya kaldi."""
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    kilit = tmp_path / "kilit"
    monkeypatch.setattr(mod, "KILIT", kilit)

    assert mod.kilitle() is True, "ilk kilit alinamadi"
    assert kilit.exists()
    assert mod.kilitle() is False, "ikinci calisma engellenmedi"

    mod.kilidi_birak()
    assert not kilit.exists()
    assert mod.kilitle() is True, "kilit birakildiktan sonra alinamiyor"
    mod.kilidi_birak()
