"""dene.py ve dogrula.py sahte veriyle uctan uca calisiyor mu.

Bu scriptler test kapsami disindaydi ve bir alan adi degisikliginde
(resolved_concept -> resolved_concepts) calisma aninda AttributeError
veriyordu. Testler yesilken script cokuyordu.
"""
from __future__ import annotations

import os
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
    assert "USD: 7 satir" in cikti
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
    assert "onbellek-bypass=7" in cikti
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


def test_enjeksiyon_aday_secimi_yalnizca_eslesenleri_calistiriyor():
    """P-24 (14 Agu 2026): bir aday enjeksiyonu denemek icin dosya ELDE
    duzenlenmisti ve geri alinmadi. Aday deneme isi de harness'in yedek/kilit/
    finally disiplininden gecmeli; `--aday` bunun icin var."""
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    assert mod.secilenler([]) == mod.ENJEKSIYONLAR, "bayraksiz calisma daralmis"

    ad = mod.ENJEKSIYONLAR[0][0]
    secili = mod.secilenler(["--aday", ad[:20]])
    assert secili and all(ad[:20].lower() in e[0].lower() for e in secili)
    assert len(secili) < len(mod.ENJEKSIYONLAR), "daraltma etkisiz"

    assert mod.secilenler(["--aday", "boyle bir enjeksiyon yok"]) == []

    # Buyuk/kucuk harf farki adayi kacirmamali
    assert mod.secilenler(["--aday", ad[:20].upper()]) == secili


def test_enjeksiyon_parametreli_testi_de_taniyor():
    """pytest parametreli testleri `test_x[deger]` diye raporlar. Duz esitlik
    arayan harness bunlari eslestiremez ve calisan bir korumayi 'KORUMASIZ'
    sanir - 14 Agu 2026'da bir kez oyle oldu."""
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    assert mod.yakalandi("test_x", ["test_x"])
    assert mod.yakalandi("test_x", ["test_x[2025Q1]", "test_y"])
    assert not mod.yakalandi("test_x", ["test_xyz"]), "onek eslesmesi cok genis"
    assert not mod.yakalandi("test_x", [])


def test_enjeksiyon_parcali_kosu_hicbir_enjeksiyonu_dusurmuyor():
    """KK-41 (16 Agu 2026): tam kosu ~3,4 saat tek surecte ve bir kez sert
    oldurmeyle 32/163'te oldu. Parcali kosu sureci kisaltiyor - ama bolme
    kaybederse harness sessizce daha az sey dogrular, yani cozdugunden buyuk
    bir sorun uretir. Birlesim TAM ve ORTUSMESIZ olmali."""
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    for n in (1, 2, 3, 4, 7, 163):
        parcalar = [mod.bol(mod.ENJEKSIYONLAR, f"{k}/{n}") for k in range(1, n + 1)]
        birlesim = [e for p in parcalar for e in p]
        assert birlesim == mod.ENJEKSIYONLAR, f"n={n}: bolme sirayi/kapsami bozdu"

    # Parca sayisi listeden buyukse bos parcalar cikar; kayip olmamali.
    cok = [mod.bol(mod.ENJEKSIYONLAR, f"{k}/500") for k in range(1, 501)]
    assert [e for p in cok for e in p] == mod.ENJEKSIYONLAR

    # `--aday` ile birlikte de calismali: once daralt, sonra bol.
    ad = mod.ENJEKSIYONLAR[0][0]
    dar = mod.secilenler(["--aday", ad[:20]])
    assert mod.secilenler(["--aday", ad[:20], "--parca", "1/1"]) == dar

    for bozuk in ("2", "0/3", "4/3", "a/b", "1/0"):
        with pytest.raises(ValueError):
            mod.bol(mod.ENJEKSIYONLAR, bozuk)


def test_enjeksiyon_kontrol_modu_yarim_kalan_kosuyu_goruyor(tmp_path, monkeypatch):
    """KK-41 (16 Agu 2026 olayi): harness sert oldurulunce `finally`, `atexit`
    ve sinyal isleyicilerinin hicbiri calismadi; `belge.py` enjekte edilmis
    halde kaldi. Kendi geri yuklemesi yalnizca BIR SONRAKI harness kosusunda
    devreye giriyor - paketleyen ya da commit eden adim harness'i calistirmiyor.
    `--kontrol` bu boslugu kapatir ve ONARMAZ: durumun gorunmesi gerekiyor."""
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    kok, yedek = tmp_path / "kok", tmp_path / "yedek"
    (kok / "src").mkdir(parents=True)
    (kok / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "KOK", kok)
    monkeypatch.setattr(mod, "YEDEK_DIZIN", yedek)
    monkeypatch.setattr(mod, "KILIT", tmp_path / "kilit")
    monkeypatch.setattr(mod, "UYGULANAN", yedek / "_uygulanan.txt")
    monkeypatch.setattr(mod, "DOSYALAR", ["src/a.py"])

    assert mod.kontrol() == 0, "artik yokken kirli raporlandi"

    mod.yedekle()
    assert mod.kontrol() == 2, "yarim kalan kosu (yedek duruyor) gorulmedi"
    yedek_var, _, farkli, _ = mod.artiklar()
    assert yedek_var and farkli == [], "enjeksiyon uygulanmadan cokme yanlis okundu"

    mod.UYGULANAN.write_text("[32/163] gizli blok filtresi -> src/a.py", encoding="utf-8")
    (kok / "src/a.py").write_text("x = 2\n", encoding="utf-8")
    _, _, farkli, not_ = mod.artiklar()
    assert farkli == ["src/a.py"], "enjekte halde kalan dosya gorulmedi"
    assert "32/163" in not_, "hangi enjeksiyonun kaldigi kaydedilmemis"
    assert mod.kontrol() == 2

    mod.geri_al()
    assert (kok / "src/a.py").read_text(encoding="utf-8") == "x = 1\n"
    assert not mod.UYGULANAN.exists(), "geri alma sonrasi isaret dosyasi kaldi"
    assert mod.kontrol() == 2, "yedek dizini dururken temiz denemez"
    mod.temizle()
    assert mod.kontrol() == 0


def test_tani_ixbrl_modu_zincirin_kapali_olup_olmadigini_soyluyor(monkeypatch, capsys):
    """--ixbrl, tasarim sirasinda olculemeyen soruyu bu makinede olcer: SEC'in
    ayikladigi instance'taki fact id'leri, dosyalayanin kendi inline
    belgesindeki isaretli parcalarin id'leriyle ayni mi. Script'in kendisi de
    test kapsaminda (KK-19/P-16): sessizce yanlis yorum yazmamali."""
    import asyncio

    from test_server import SUBS, TICKERS

    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@example.com")

    INSTANCE = ('<?xml version="1.0"?><xbrl xmlns="http://www.xbrl.org/2003/instance"'
                ' xmlns:us-gaap="http://fasb.org/us-gaap/2025">'
                '<unit id="fsdsubscription"><measure>pure</measure></unit>'
                '<us-gaap:Revenues contextRef="c-1" id="f-1">1</us-gaap:Revenues>'
                '<us-gaap:Assets contextRef="c-1" id="f-2">2</us-gaap:Assets>'
                "</xbrl>")
    INLINE_ESLESEN = '<html><body><ix:nonFraction id="f-1">1</ix:nonFraction>' \
                     '<ix:nonFraction id="f-2">2</ix:nonFraction></body></html>'
    INLINE_ESLESMEYEN = "<html><body><span>no ids here</span></body></html>"
    DIZIN = {"directory": {"item": [{"name": "aapl-20250927_htm.xml", "size": "10"}]}}

    def kur(inline_govde):
        def h(request: httpx.Request) -> httpx.Response:
            u = str(request.url)
            if "company_tickers" in u:
                return httpx.Response(200, json=TICKERS)
            if "/submissions/" in u:
                return httpx.Response(200, json=SUBS)
            if u.endswith("/index.json"):
                return httpx.Response(200, json=DIZIN)
            if u.endswith("_htm.xml"):
                return httpx.Response(200, text=INSTANCE)
            return httpx.Response(200, text=inline_govde)
        return h

    mod = _tani_modulu()
    monkeypatch.setattr(sys, "argv", ["tani.py", "AAPL", "--ixbrl"])

    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(kur(INLINE_ESLESEN)))
    assert asyncio.run(mod.main()) == 0
    cikti = capsys.readouterr().out
    assert "Zincir KAPALI:" in cikti, cikti

    monkeypatch.setattr(mod, "EdgarClient", _istemci_ile(kur(INLINE_ESLESMEYEN)))
    assert asyncio.run(mod.main()) == 0
    cikti = capsys.readouterr().out
    assert "Zincir KAPALI DEGIL:" in cikti, cikti


# ---------------------------------------------------------------- .env yukleyici
def test_env_yukleyici_bom_lu_dosyayi_okuyor(tmp_path, monkeypatch):
    """PowerShell'in `Out-File -Encoding utf8` komutu dosyanin basina BOM koyar.
    BOM'lu ilk anahtar `SEC_USER_AGENT` degil `﻿SEC_USER_AGENT` olarak
    okunur ve degisken hic tanimlanmaz (15 Agu 2026'da yasandi)."""
    import importlib

    yol = tmp_path / ".env"
    yol.write_text('SEC_USER_AGENT="Ada Lovelace ada@example.com"\n',
                   encoding="utf-8-sig")
    assert yol.read_bytes().startswith(b"\xef\xbb\xbf"), "test BOM yazmamis"

    ortam = importlib.import_module("arac.ortam")
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    ortam._elle_yukle(yol)
    assert os.environ["SEC_USER_AGENT"] == "Ada Lovelace ada@example.com"


def test_env_yukleyici_bagimlilik_olmadan_da_yukluyor(tmp_path, monkeypatch):
    """`python-dotenv` kurulu degilse eski surum SESSIZCE geciyordu: dosya
    yerinde, degisken tanimsiz, hata mesaji ise "ortam degiskeni yok" diyordu.
    Opsiyonel olan sey bagimliliktir, yuklemenin kendisi degil."""
    import builtins
    import importlib

    yol = tmp_path / ".env"
    yol.write_text("SEC_USER_AGENT=Ada ada@example.com\n", encoding="utf-8")

    ortam = importlib.import_module("arac.ortam")
    monkeypatch.setattr(ortam, "ENV_YOLU", yol)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)

    gercek_import = builtins.__import__

    def dotenv_yok(ad, *a, **k):
        if ad == "dotenv":
            raise ImportError("no dotenv")
        return gercek_import(ad, *a, **k)

    monkeypatch.setattr(builtins, "__import__", dotenv_yok)
    ortam.env_yukle()
    assert os.environ["SEC_USER_AGENT"] == "Ada ada@example.com"


def test_env_yukleyici_mevcut_degiskeni_ezmiyor(tmp_path, monkeypatch):
    """Kabuğunda degiskeni elle veren biri, dosyadaki eski degerin onu sessizce
    gecersiz kilmasini beklemez."""
    import importlib

    yol = tmp_path / ".env"
    yol.write_text("SEC_USER_AGENT=dosyadaki dosya@example.com\n", encoding="utf-8")
    ortam = importlib.import_module("arac.ortam")
    monkeypatch.setenv("SEC_USER_AGENT", "kabuktaki kabuk@example.com")
    ortam._elle_yukle(yol)
    assert os.environ["SEC_USER_AGENT"] == "kabuktaki kabuk@example.com"


@pytest.mark.parametrize("satir,beklenen", [
    ('SEC_USER_AGENT="Ada ada@example.com"', ("SEC_USER_AGENT", "Ada ada@example.com")),
    ("SEC_USER_AGENT='Ada ada@example.com'", ("SEC_USER_AGENT", "Ada ada@example.com")),
    ("export SEC_USER_AGENT=Ada", ("SEC_USER_AGENT", "Ada")),
    ("  # yorum satiri", None),
    ("", None),
    ("anahtarsiz satir", None),
    ("=degersiz", None),
])
def test_env_satir_ayristirma(satir, beklenen):
    import importlib
    ortam = importlib.import_module("arac.ortam")
    assert ortam._ayristir(satir) == beklenen


def test_enjeksiyon_kontrol_yedek_silinince_temiz_demiyor(tmp_path, monkeypatch):
    """18 Agu 2026, denetimde uretildi: `--kontrol` "enjekte kalmis dosya"
    listesini yalnizca `.enjeksiyon_yedek/` VARSA hesapliyordu ve o dizin
    `.gitignore`'da. Taze bir klon, `git clean -fdx` ya da elle temizlik tek
    kaniti siliyor; kaynak dosya enjekte kalsa bile cikti "TEMIZ: enjeksiyon
    artigi yok" diyor ve exit 0 donuyordu.

    Yani KK-41'de kapatilan bosluk, kapatan aracin KENDISINDE geri aciliyordu:
    "artik, harness'tan baska hicbir yerden gorulmuyor".

    Duzeltme iki parcali: (1) yedek yokken cikti artik "TEMIZ" DEMIYOR, neye
    bakip neye bakmadigini soyluyor; (2) `--sert` ikinci bir kaynak olarak
    git'e bakiyor ve teyit edemezse exit 3 donuyor."""
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    kok = tmp_path / "kok"
    (kok / "src").mkdir(parents=True)
    (kok / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "KOK", kok)
    monkeypatch.setattr(mod, "YEDEK_DIZIN", tmp_path / "yedek")   # YOK
    monkeypatch.setattr(mod, "KILIT", tmp_path / "kilit")         # YOK
    monkeypatch.setattr(mod, "UYGULANAN", tmp_path / "yedek" / "_uygulanan.txt")
    monkeypatch.setattr(mod, "DOSYALAR", ["src/a.py"])
    # Git yok: kaynak dogrulanamiyor.
    monkeypatch.setattr(mod, "git_temiz_mi", lambda: None)

    import contextlib
    import io

    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        kod = mod.kontrol()
    cikti = tampon.getvalue()
    assert kod == 0, "gunluk kullanimda engel olmamali"
    assert "TEMIZ" not in cikti, (
        "dogrulanmamis bir durum 'TEMIZ' diye raporlandi:\n" + cikti)
    assert "KARSILASTIRILMADI" in cikti, "neye bakilmadigi soylenmiyor"

    # Sert modda karar verilemeyen durum basarisizliktir.
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        assert mod.kontrol(sert=True) == 3
    assert "DOGRULANAMADI" in tampon.getvalue()

    # Git temiz diyorsa "TEMIZ" demek artik dayanakli.
    monkeypatch.setattr(mod, "git_temiz_mi", lambda: True)
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        assert mod.kontrol(sert=True) == 0
    assert "TEMIZ" in tampon.getvalue()


def test_harness_kaynagi_yerel_kod_sayfasindan_bagimsiz_okuyup_yaziyor():
    """18 Agu 2026, CI #15-#30 (KK-49): harness Windows'ta dort gun kirmiziydi.

    `Path.read_text()` encoding verilmezse yerel kod sayfasini kullanir.
    Windows runner'inda bu cp1252; `belge.py` icindeki `–`/`—` karakterleri
    UTF-8'den yanlis cozuluyor ve o dosyayi hedefleyen enjeksiyon dizgisi artik
    eslesmiyordu. Harness bunu dogru sekilde "ENJEKSIYON UYGULANAMADI" diye
    raporlayip exit 1 dondu (KK-10): CI kirmizi, ama sebebi korunan kod degil,
    OLCEN ARACIN kendisi.

    Test hatayi Linux'ta da URETIR: alt surec ASCII yerel ayarla ve UTF-8 modu
    KAPALI baslatilir, yani encoding'siz bir okuma ASCII'ye duser. Duzeltmeden
    once `oku()` orada `UnicodeDecodeError` firliyordu.

    Olculen sey HEDEF LISTESI DEGIL, OKUYUCUNUN KENDISI. Ilk yazimda test
    "her enjeksiyon hedefi dosyasinda bulunuyor mu" diye soruyordu; o test
    HERHANGI bir enjeksiyon uygulanmis haldeyken de kirmiziya doner, yani
    harness'in gozunde EVRENSEL BIR YAKALAYICI olur ve gercekten korumasiz
    bir enjeksiyonu "yakalandi" diye gosterirdi. Hedeflerin dosyada bulunmasi
    zaten harness'in kendi isi (KK-10, "ENJEKSIYON UYGULANAMADI"); pytest'te
    tekrarlanmamali.

    Alt surec kendi cozdugu encoding'i bildiriyor: zaten UTF-8'e dusmusse test
    hicbir sey olcmemis olur ve `skip` eder - sessizce yesil GECMEZ.
    """
    import json
    import os
    import subprocess
    import sys

    kod = """
import json, locale, pathlib, sys, tempfile
sys.path.insert(0, __KOK__)
from arac.enjeksiyon import DOSYALAR, KOK, oku, yaz

sonuc = {"encoding": locale.getpreferredencoding(False), "hata": None,
         "ascii_disi": [], "cozum_farkli": [], "yazma_farkli": []}
try:
    with tempfile.TemporaryDirectory() as d:
        for dosya in DOSYALAR:
            ham = (KOK / dosya).read_bytes()
            metin = oku(KOK / dosya)
            if any(ord(c) > 127 for c in metin):
                sonuc["ascii_disi"].append(dosya)
            if metin != ham.decode("utf-8"):
                sonuc["cozum_farkli"].append(dosya)
            gecici = pathlib.Path(d) / "k"
            yaz(gecici, metin)
            if gecici.read_bytes() != ham:
                sonuc["yazma_farkli"].append(dosya)
except Exception as e:
    sonuc["hata"] = type(e).__name__ + ": " + str(e)
print(json.dumps(sonuc))
""".replace("__KOK__", repr(str(KOK)))

    ortam = {**os.environ, "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    if os.name != "nt":
        ortam.update(LC_ALL="C", LANG="C", LC_CTYPE="C")
    r = subprocess.run([sys.executable, "-X", "utf8=0", "-c", kod],
                       cwd=KOK, env=ortam, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=120)
    assert r.returncode == 0, f"alt surec coktu:\n{r.stderr}"
    d = json.loads(r.stdout.strip().splitlines()[-1])

    if d["encoding"].lower().replace("-", "") in ("utf8", "cp65001"):
        pytest.skip("bu platformda yerel kod sayfasi zaten UTF-8; hata "
                    f"uretilemiyor ({d['encoding']})")

    assert d["hata"] is None, (
        f"yerel kod sayfasi {d['encoding']} iken kaynak okunamadi: {d['hata']}")
    assert d["ascii_disi"], (
        "korunan dosyalarin hicbirinde ASCII disi karakter kalmamis - bu test "
        "artik gercek bir senaryoyu olcmuyor")
    assert d["cozum_farkli"] == [], (
        f"yerel kod sayfasi {d['encoding']} iken su dosyalar UTF-8'den farkli "
        f"cozuldu: {d['cozum_farkli']}")
    assert d["yazma_farkli"] == [], (
        "geri yazma bayt bazinda ayni degil (encoding ya da satir sonu "
        f"cevrimi): {d['yazma_farkli']}")


def test_hicbir_metin_dosyasi_okumasi_yerel_kod_sayfasina_birakilmiyor():
    """KK-14'un ucuncu tekrari, bu kez OLCEN ARACTA (KK-49).

    Onceki iki tekrar `subprocess.run(text=True)` idi ve ikisi de tek tek
    duzeltilmisti. Bu test sinifin kendisini kapatiyor: depodaki hicbir
    `read_text`/`write_text`/`open` cagrisi metin modunda encoding'siz
    olmamali. Encoding'siz bir cagri, gelistiricinin makinesinde calisir ve
    baska bir yerel ayarda ya coker ya da SESSIZCE farkli metin dondurur -
    ikincisi daha kotusu.
    """
    import ast

    hedef = {"read_text", "write_text"}
    bulgu = []
    for yol in sorted(list(KOK.glob("src/**/*.py")) + list(KOK.glob("arac/*.py"))
                      + list(KOK.glob("tests/*.py")) + list(KOK.glob("*.py"))):
        agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
        for d in ast.walk(agac):
            if not isinstance(d, ast.Call):
                continue
            if isinstance(d.func, ast.Attribute) and d.func.attr in hedef:
                if not any(k.arg == "encoding" for k in d.keywords):
                    bulgu.append(f"{yol.relative_to(KOK)}:{d.lineno} {d.func.attr}")
            elif isinstance(d.func, ast.Name) and d.func.id == "open":
                kip = d.args[1].value if (
                    len(d.args) > 1 and isinstance(d.args[1], ast.Constant)
                    and isinstance(d.args[1].value, str)) else ""
                anahtarlar = {k.arg for k in d.keywords}
                if "b" not in kip and "encoding" not in anahtarlar:
                    bulgu.append(f"{yol.relative_to(KOK)}:{d.lineno} open")
    assert not bulgu, (
        "encoding verilmeden metin modunda dosya acan cagrilar:\n  "
        + "\n  ".join(bulgu))


def test_hicbir_tanimlayici_ascii_disi_karakter_tasimiyor():
    """18 Agu 2026, KK-49 duzeltilirken ASCII yerel ayarla kosarken bulundu:
    `test_13f_ihracci_araması_ve_siralama` adinda Turkce `ı` vardi.

    Python 3 tanimlayicilarda Unicode'a izin verir, ama ad oradan ORTAMA
    tasiniyor: pytest her testin adini `PYTEST_CURRENT_TEST` degiskenine yazar
    ve `os.putenv` onu yerel kod sayfasina cevirir. ASCII yerel ayarda bu
    `UnicodeEncodeError` ile patliyor - test ne calisiyor ne de atlaniyor,
    TOPLAMA asamasinda hata veriyor. Ayni ad ayrica `-k` ifadelerinde,
    gunluklerde ve JUnit XML'inde de kirilgan.

    Depo kurali zaten buydu (KK-9: disariya bakan yuzey Ingilizce, ic
    belgelendirme Turkce) ama YORUMLAR icin; tanimlayicilar hicbir zaman
    denetlenmiyordu. Bu test onu kapatiyor: metin Turkce kalabilir, AD kalamaz.
    """
    import ast

    bulgu = []
    for yol in sorted(list(KOK.glob("src/**/*.py")) + list(KOK.glob("arac/*.py"))
                      + list(KOK.glob("tests/*.py")) + list(KOK.glob("*.py"))):
        agac = ast.parse(yol.read_text(encoding="utf-8"), filename=str(yol))
        for d in ast.walk(agac):
            adlar = []
            if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
                adlar = [d.name] + [a.arg for a in d.args.args + d.args.kwonlyargs]
            elif isinstance(d, ast.ClassDef):
                adlar = [d.name]
            elif isinstance(d, ast.Name) and isinstance(d.ctx, ast.Store):
                adlar = [d.id]
            elif isinstance(d, ast.arg):
                adlar = [d.arg]
            for ad in adlar:
                if any(ord(c) > 127 for c in ad):
                    bulgu.append(f"{yol.relative_to(KOK)}:{d.lineno} {ad!r}")
    assert not bulgu, (
        "ASCII disi karakter iceren tanimlayicilar (yerel ayara bagli olarak "
        "kirilir):\n  " + "\n  ".join(sorted(set(bulgu))))


def test_enjeksiyon_hedefleri_dosyada_tam_bir_kez_geciyor():
    """KK-18, 13 Agu 2026'da yazildi ve 19 Agu 2026'ya kadar HICBIR SEY onu
    zorlamadi. Denetimde iki ihlal bulundu.

    Kural: her enjeksiyonun hedef dizgisi, hedef dosyada TAM BIR KEZ gecmeli.
    Sebebi `replace(..., 1)`: dizgi iki yerde geciyorsa harness her zaman
    ILKINI bozar. Sonucu iki turlu ve ikisi de kotu:

    - Beklenen test yine kirmiziya donerse koruma DOGRULANMIS GORUNUR, oysa
      ikinci sitedeki ayni koruma hic olculmemistir. 19 Agu'da olculdu: takma
      ad fallback'i `compare_companies` icinde de var ve hic sinanmamisti.
    - Iki fonksiyonun sirasi degisirse harness yanlis siteyi bozar, beklenen
      test yesil kalir ve CALISAN bir koruma KORUMASIZ diye raporlanir.

    Bu test EVRENSEL YAKALAYICI DEGIL (bkz. yukaridaki
    `test_harness_kaynagi_...` girdisinin gerekcesi): bir enjeksiyon
    uygulandiginda hedef sayisi 1'den 0'a duser, `!= 1` degil `> 1` araniyor,
    dolayisiyla enjeksiyon altinda kirmizi donmez.
    """
    import importlib

    mod = importlib.import_module("arac.enjeksiyon")
    icerik = {d: mod.oku(mod.KOK / d) for d in mod.DOSYALAR}

    coklu = []
    for ad, dosya, eski, _yeni, _bek in mod.ENJEKSIYONLAR:
        n = icerik[dosya].count(eski)
        if n > 1:
            coklu.append(f"{ad!r} -> {dosya} icinde {n} kez")
    assert not coklu, (
        "KK-18: enjeksiyon hedefi dosyada birden fazla geciyor; harness her "
        "zaman ILKINI bozar, ikinci site hic olculmez:\n  " + "\n  ".join(coklu))


def test_enjeksiyon_beklenen_testleri_gercekten_var():
    """Bayat bir `expected_tests` adi, korumayi sessizce olculemez yapar:
    enjeksiyon uygulanir, bir seyler kirmiziya doner, ama `yakandi()` aradigi
    adi bulamaz ve KORUMASIZ raporlanir. Ters yonde de kotu - var olmayan bir
    ada bakan bir kayit, hicbir zaman dogrulanmayacak bir koruma demektir."""
    import importlib
    import re

    mod = importlib.import_module("arac.enjeksiyon")
    mevcut = set()
    for yol in (KOK / "tests").glob("test_*.py"):
        mevcut |= set(re.findall(r"^(?:async )?def (test_\w+)",
                                 yol.read_text(encoding="utf-8"), re.M))
    assert len(mevcut) > 200, f"test taramasi coktu: {len(mevcut)} test bulundu"

    eksik = []
    for ad, _d, _e, _y, beklenen in mod.ENJEKSIYONLAR:
        for t in [x.strip() for x in beklenen.split(",") if x.strip()]:
            if t not in mevcut:
                eksik.append(f"{ad!r} -> {t}")
    assert not eksik, (
        "enjeksiyon var olmayan bir teste atif yapiyor:\n  " + "\n  ".join(eksik))
