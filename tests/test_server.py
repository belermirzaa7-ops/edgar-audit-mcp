"""SEC'e canli cikmadan sunucuyu dogrular: HTTP katmani mock'lanir."""
import pathlib
import sys

import httpx
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

TICKERS = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
SUBS = {"name": "Apple Inc.", "sicDescription": "Electronic Computers",
        "fiscalYearEnd": "0927",
        # Gercek SEC submissions verisi karisik form turleri icerir; sahte veri de icermeli.
        "filings": {"recent": {
            "accessionNumber": ["0000320193-25-000073","0000320193-25-000058",
                                "0000320193-25-000041","0000320193-24-000123",
                                "0000320193-25-000012"],
            "form":            ["10-K","10-Q","8-K","10-K","4"],
            "filingDate":      ["2025-10-31","2025-08-01","2025-06-10","2024-11-01","2025-02-03"],
            "reportDate":      ["2025-09-27","2025-06-28","2025-06-09","2024-09-28",""],
            "primaryDocument": ["aapl-20250927.htm","aapl-20250628.htm","aapl-8k.htm",
                                "aapl-20240928.htm","xslF345X05/form4.xml"],
        }}}

CONCEPT = {"label": "Revenues", "units": {"USD": [
    # 2023 10-K: uc yillik karsilastirma, UCUNUN DE fy'si 2023 (SEC boyle veriyor)
    {"start":"2020-09-27","end":"2021-09-25","val":365_817_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03"},
    {"start":"2021-09-26","end":"2022-09-24","val":394_328_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03"},
    {"start":"2022-09-25","end":"2023-09-30","val":383_285_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03"},
    # ayni donem 2024 10-K'sinda tekrar raporlanmis (revize deger)
    {"start":"2022-09-25","end":"2023-09-30","val":383_290_000_000,"fy":2024,"fp":"FY","form":"10-K","filed":"2024-11-01"},
    # ceyreklik veri ayni listede
    {"start":"2023-04-02","end":"2023-07-01","val": 81_797_000_000,"fy":2023,"fp":"Q3","form":"10-Q","filed":"2023-08-04"},
]}}

# Apple gerçekte "Revenues" DEGIL bunu kullanir; ilk aday 404 vermeli ki
# takma ad fallback zinciri gercekten sinansin.
GERCEK_GELIR_ETIKETI = "RevenueFromContractWithCustomerExcludingAssessedTax"

NET_INCOME = {"label": "Net Income (Loss)", "units": {"USD": [
    {"start":"2022-09-25","end":"2023-09-30","val":96_995_000_000,"fy":2023,"fp":"FY","form":"10-K","filed":"2023-11-03"},
]}}

def _satirlar(n: int) -> list[dict]:
    """companyfacts satirlari companyconcept ile AYNI sekle sahiptir. Sahte
    veri bunu taklit etmeli: bos sozlukler koymak, companyfacts'e dusen kodu
    sinanamaz hale getirir (P-4)."""
    return [
        {"start": f"{2016 + i}-09-25", "end": f"{2017 + i}-09-30",
         "val": 100_000_000_000 + i, "fy": 2017 + i, "fp": "FY",
         "form": "10-K", "filed": f"{2017 + i}-11-03"}
        for i in range(n)
    ]


FACTS = {"facts": {"us-gaap": {
    GERCEK_GELIR_ETIKETI: {"label": "Revenue from Contract with Customer",
                           "units": {"USD": _satirlar(3)}},
    "NetIncomeLoss":      {"label": "Net Income (Loss)", "units": {"USD": _satirlar(2)}},
    "SalesRevenueNet":    {"label": "Sales Revenue, Net", "units": {"USD": _satirlar(4)}},
    "Assets":             {"label": "Assets", "units": {"USD": _satirlar(1)}},
    "DeferredRevenue":    {"label": "Deferred Revenue", "units": {"USD": _satirlar(1)}},
}}}

# Apple 2018 oncesi geliri BASKA bir etiketle raporladi. Gercek dunyada
# oldugu gibi: iki etiket, kismi ortusme, farkli dosyalama tarihleri.
SALES_REVENUE = {"label": "Sales Revenue, Net", "units": {"USD": [
    {"start":"2016-09-25","end":"2017-09-30","val":229_234_000_000,"fy":2019,"fp":"FY","form":"10-K","filed":"2019-10-31"},
    {"start":"2017-10-01","end":"2018-09-29","val":265_595_000_000,"fy":2019,"fp":"FY","form":"10-K","filed":"2019-10-31"},
    {"start":"2018-09-30","end":"2019-09-28","val":260_174_000_000,"fy":2019,"fp":"FY","form":"10-K","filed":"2019-10-31"},
    # ORTUSEN donem: modern etikette de var, ama bu kayit DAHA ESKI sunulmus
    {"start":"2020-09-27","end":"2021-09-25","val":999_000_000_000,"fy":2021,"fp":"FY","form":"10-K","filed":"2021-10-29"},
]}}

ISTEK_KAYDI: list[str] = []


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    ISTEK_KAYDI.append(u)
    assert "@" in request.headers["User-Agent"], "SEC User-Agent e-posta icermeli"
    if "company_tickers" in u:
        return httpx.Response(200, json=TICKERS)
    if "/submissions/" in u:
        return httpx.Response(200, json=SUBS)
    if "companyfacts" in u:
        return httpx.Response(200, json=FACTS)
    if "companyconcept" in u:
        if GERCEK_GELIR_ETIKETI in u:
            return httpx.Response(200, json=CONCEPT)
        if "NetIncomeLoss" in u:
            return httpx.Response(200, json=NET_INCOME)
        if "SalesRevenueNet" in u:
            return httpx.Response(200, json=SALES_REVENUE)
        return httpx.Response(404)          # SEC bilinmeyen etikete 404 doner
    return httpx.Response(404)

@pytest.fixture
def srv(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@ornek.com")
    from edgar_mcp import server as s
    from edgar_mcp.client import EdgarClient
    c = EdgarClient()
    c._http = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                headers={"User-Agent": "Test Runner test@ornek.com"})
    s._client = c
    return s

@pytest.mark.anyio
async def test_profile(srv):
    p = await srv.get_company_profile(ticker="aapl")
    assert p.cik == "0000320193" and p.name == "Apple Inc." and p.ticker == "AAPL"

@pytest.mark.anyio
async def test_filings_filter(srv):
    """Karisik form turleri arasindan SADECE istenen tur donmeli."""
    s = await srv.list_recent_filings(ticker="AAPL", form_type="10-K", limit=5)
    assert [x.form for x in s.filings] == ["10-K", "10-K"], "10-K disi form sizdi"
    assert s.filings[0].primary_document_url.endswith(
        "000032019325000073/aapl-20250927.htm"
    )


@pytest.mark.anyio
async def test_filings_filtresiz_hepsini_dondurur(srv):
    """Kontrol testi: filtre yokken gercekten baska turler var mi?
    Bu olmadan yukaridaki test bos bir kumeyi 'filtrelenmis' sanabilir."""
    s = await srv.list_recent_filings(ticker="AAPL", limit=10)
    assert {x.form for x in s.filings} == {"10-K", "10-Q", "8-K", "4"}


@pytest.mark.anyio
async def test_filings_limit_uygulanir(srv):
    s = await srv.list_recent_filings(ticker="AAPL", limit=2)
    assert len(s.filings) == 2


@pytest.mark.anyio
async def test_filings_sayfalama_bilgisi_verir(srv):
    """Standart §16: limit tek basina yetmez. Model, listenin tamami mi yoksa
    kirpilmis mi oldugunu bilmeden 'sirketin N dosyalamasi var' diyebilir."""
    kirpik = await srv.list_recent_filings(ticker="AAPL", limit=2)
    assert kirpik.total_matching == 5
    assert kirpik.returned == 2
    assert kirpik.has_more is True

    tam = await srv.list_recent_filings(ticker="AAPL", limit=50)
    assert tam.total_matching == 5
    assert tam.returned == 5
    assert tam.has_more is False


@pytest.mark.anyio
async def test_filings_sayfalama_filtreyle_birlikte_dogru(srv):
    """total_matching, filtre UYGULANDIKTAN sonraki sayi olmali - filtresiz
    toplami raporlamak modeli yaniltir."""
    s = await srv.list_recent_filings(ticker="AAPL", form_type="10-K", limit=1)
    assert s.total_matching == 2, "filtre disi dosyalamalar sayima girmis"
    assert s.returned == 1
    assert s.has_more is True


@pytest.mark.anyio
async def test_seri_sayfalama_bilgisi_verir(srv):
    az = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=2)
    assert az.returned == 2
    assert az.has_more is True
    assert az.total_periods > 2

    hepsi = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=60)
    assert hepsi.has_more is False
    assert hepsi.returned == hepsi.total_periods


@pytest.mark.anyio
async def test_seri_kirpmada_EN_YENI_donemler_kalir(srv):
    """Kirpma yonu onemli: model trend analizi yapiyorsa en yeni donemleri
    gormeli, en eskileri degil."""
    az = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=2)
    hepsi = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=60)
    assert [p.period_end for p in az.points] == [p.period_end for p in hepsi.points[-2:]]


# ============================================== §19: annotations ipucudur
@pytest.mark.anyio
async def test_tum_araclar_salt_okunur_ilan_ediyor():
    from edgar_mcp.server import mcp

    for t in await mcp.list_tools():
        a = t.annotations
        assert a is not None, f"{t.name}: annotations yok"
        assert a.read_only_hint is True, f"{t.name}: read_only_hint True degil"
        assert a.destructive_hint is False, f"{t.name}: destructive_hint False degil"


def test_kodda_hicbir_yazma_yolu_yok():
    """Standart §19: annotations bir IPUCUDUR, garanti degil. Gercek garanti,
    yazma yolunun hic BULUNMAMASI. Bu test ipucunu kanita cevirir - biri
    ileride bir POST ekler ve read_only_hint'i guncellemeyi unutursa yakalanir."""
    import pathlib
    import re

    kok = pathlib.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    yasak = re.compile(r"\.(post|put|patch|delete)\s*\(", re.I)
    for f in kok.glob("*.py"):
        metin = f.read_text(encoding="utf-8")
        bulunan = yasak.findall(metin)
        assert not bulunan, f"{f.name} yazma cagrisi iceriyor: {bulunan}"


@pytest.mark.anyio
async def test_donem_yili_bitis_tarihinden_gelir(srv):
    """SEC'in fy alani DOSYALAMANIN yilidir. Bir 10-K'daki 3 yillik karsilastirmanin
    ucu de ayni fy'ye sahiptir; yil mutlaka donem sonundan turetilmelidir."""
    s = await srv.get_concept_series(
        ticker="AAPL", concept=GERCEK_GELIR_ETIKETI, period="annual"
    )
    assert [p.fiscal_year for p in s.points] == [2021, 2022, 2023]
    deger = {p.fiscal_year: p.value for p in s.points}
    assert deger[2021] == 365_817_000_000
    assert deger[2022] == 394_328_000_000


@pytest.mark.anyio
async def test_ceyreklik_yillik_seriye_sizmaz(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", period="annual")
    assert all(300 <= p.days <= 400 for p in s.points)
    assert 81_797_000_000 not in [p.value for p in s.points]


@pytest.mark.anyio
async def test_ayni_donem_tekrar_raporlanirsa_en_guncel_alinir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", period="annual")
    fy23 = [p for p in s.points if p.fiscal_year == 2023][0]
    assert fy23.filed == "2024-11-01"
    assert fy23.value == 383_290_000_000


@pytest.mark.anyio
async def test_ua_zorunlu(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    from edgar_mcp.client import EdgarClient
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        EdgarClient()

@pytest.fixture
def anyio_backend(): return "asyncio"


# ---------------------------------------------------------------- ISS-1: takma adlar
@pytest.mark.anyio
async def test_takma_ad_gercek_etikete_cozulur(srv):
    """'revenue' takma adi, sirketin fiilen kullandigi etikete cozulmeli."""
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue")
    assert GERCEK_GELIR_ETIKETI in s.resolved_concepts
    assert s.requested_concept == "revenue"


@pytest.mark.anyio
async def test_takma_ad_ilk_aday_404_verirse_sonrakini_dener(srv):
    """Fallback zinciri gercekten calisiyor mu: 'Revenues' 404, ucuncu aday tutuyor."""
    ISTEK_KAYDI.clear()
    await srv.get_concept_series(ticker="AAPL", concept="revenue")
    denenen = [u.rsplit("/", 1)[-1].replace(".json", "")
               for u in ISTEK_KAYDI if "companyconcept" in u]
    assert denenen[0] == GERCEK_GELIR_ETIKETI, "aday sirasi bozulmus"


@pytest.mark.anyio
async def test_ham_gaap_etiketi_de_kabul_edilir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="NetIncomeLoss")
    assert s.resolved_concepts == ["NetIncomeLoss"]


@pytest.mark.anyio
async def test_buyuk_harf_ve_bosluk_toleransi(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="  REVENUE ")
    assert GERCEK_GELIR_ETIKETI in s.resolved_concepts


@pytest.mark.anyio
async def test_bilinmeyen_etiket_eyleme_donusturulebilir_hata_verir(srv):
    """Standart §18: hata mesaji modele ne yapacagini soylemeli."""
    with pytest.raises(ValueError) as e:
        await srv.get_concept_series(ticker="AAPL", concept="UyduRulmusEtiket")
    m = str(e.value)
    assert "sec_edgar_list_available_concepts" in m, "kesif araci onerilmiyor"
    assert "revenue" in m, "gecerli takma adlar listelenmiyor"


# ---------------------------------------------------------------- kesif araci
@pytest.mark.anyio
async def test_kesif_araci_arama_filtreler(srv):
    k = await srv.list_available_concepts(ticker="AAPL", search="revenue")
    etiketler = [c.tag for c in k.concepts]
    assert GERCEK_GELIR_ETIKETI in etiketler
    assert "DeferredRevenue" in etiketler
    assert "Assets" not in etiketler, "filtre disi etiket sizdi"


@pytest.mark.anyio
async def test_kesif_araci_etiket_metninde_de_arar(srv):
    k = await srv.list_available_concepts(ticker="AAPL", search="net income")
    assert "NetIncomeLoss" in [c.tag for c in k.concepts]


@pytest.mark.anyio
async def test_kesif_araci_sayfalama_bilgisi_verir(srv):
    """Standart §16: limit tek basina yetmez, toplam ve has_more da lazim."""
    k = await srv.list_available_concepts(ticker="AAPL", limit=2)
    assert k.total_matching == 5
    assert k.returned == 2
    assert len(k.concepts) == 2
    assert k.has_more is True

    hepsi = await srv.list_available_concepts(ticker="AAPL", limit=50)
    assert hepsi.has_more is False


@pytest.mark.anyio
async def test_kesif_araci_veri_yogunluguna_gore_siralar(srv):
    k = await srv.list_available_concepts(ticker="AAPL", limit=50)
    sayilar = [c.data_points for c in k.concepts]
    assert sayilar == sorted(sayilar, reverse=True), "azalan siralama bozuk"
    assert k.concepts[0].data_points == max(sayilar)


@pytest.mark.anyio
async def test_companyfacts_bir_kez_cekilir(srv):
    """companyfacts birkac MB; iki cagri tek HTTP istegi yapmali (onbellek)."""
    ISTEK_KAYDI.clear()
    await srv.list_available_concepts(ticker="AAPL")
    await srv.list_available_concepts(ticker="AAPL", search="assets")
    assert sum("companyfacts" in u for u in ISTEK_KAYDI) == 1


# ---------------------------------------------------------------- IS-2: isim onegi
@pytest.mark.anyio
async def test_arac_isimleri_servis_onekli():
    """Standart §15: jenerik isimler baska sunucularla cakisir.
    Bu test, ileride oneki dusuren bir degisikligi yapisal olarak yakalar."""
    from edgar_mcp.server import mcp
    isimler = {t.name for t in await mcp.list_tools()}
    assert isimler == {
        "sec_edgar_get_company_profile",
        "sec_edgar_list_filings",
        "sec_edgar_get_concept_series",
        "sec_edgar_list_available_concepts",
    }, f"beklenmeyen arac isimleri: {isimler}"


# ---------------------------------------------------------------- hiz siniri
@pytest.mark.anyio
async def test_hiz_sinirlayici_gercekten_bekletir():
    """Testlerde hiz siniri ortam degiskeniyle gevsetiliyor; sinirlayicinin
    KENDISI burada dogrudan sinaniyor ki koruma kaldirilmis olmasin."""
    import time

    from edgar_mcp.client import RateLimiter

    r = RateLimiter(rate_per_sec=20.0)          # 50 ms araliK
    t0 = time.monotonic()
    for _ in range(3):
        await r.acquire()
    gecen = time.monotonic() - t0
    assert gecen >= 0.09, f"sinirlayici bekletmedi ({gecen:.3f}s)"


def test_varsayilan_hiz_sec_sinirinin_altinda():
    from edgar_mcp.client import RateLimiter
    assert RateLimiter.VARSAYILAN_HIZ < 10.0, "SEC ust siniri 10 istek/sn"


# ================================================================ H-1: mali yil
def test_kayma_apple_tipi_sifir():
    """Bitis yiliyla adlandiran sirket (Apple, Walmart, Microsoft): kayma 0."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [
        {"start":"2022-09-25","end":"2023-09-30","fy":2023,"fp":"FY","form":"10-K"},
        {"start":"2021-09-26","end":"2022-09-24","fy":2023,"fp":"FY","form":"10-K"},
        {"start":"2023-10-01","end":"2024-09-28","fy":2024,"fp":"FY","form":"10-K"},
    ]
    assert _fy_kaymasi(rows) == (0, True)


def test_kayma_target_tipi_eksi_bir():
    """Baslangic yiliyla adlandiran perakendeci (Target/Gap): 3 Subat 2024'te
    biten yil 'fiscal 2023'tur. Kayma -1 olarak TURETILMELI, varsayilmamali."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [
        {"start":"2023-01-29","end":"2024-02-03","fy":2023,"fp":"FY","form":"10-K"},
        {"start":"2022-01-30","end":"2023-01-28","fy":2023,"fp":"FY","form":"10-K"},
    ]
    assert _fy_kaymasi(rows) == (-1, True)


def test_kayma_capa_yoksa_turetilmedi_isaretlenir():
    """10-K capasi yoksa uydurma yapma - 0 dondur ama TURETILMEDI de."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [{"start":"2024-01-01","end":"2024-03-31","fy":2024,"fp":"Q1","form":"10-Q"}]
    assert _fy_kaymasi(rows) == (0, False)


def test_kayma_ceyreklik_satirlari_capa_saymaz():
    """Ilk yazdigim bu test KUSURLUYDU: filtre kaldirilinca da ayni sonucu
    veriyordu, yani hicbir sey korumuyordu (enjeksiyon yakaladi).
    Yeniden kuruldu: kisa donemler capa sayilirsa mod 0'dan 1'e KAYMALI."""
    from edgar_mcp.server import _fy_kaymasi
    rows = [
        # tek gecerli capa: yillik donem, kayma 0
        {"start":"2022-09-25","end":"2023-09-30","fy":2023,"fp":"FY","form":"10-K"},
        # kisa donemler; capa sayilirlarsa ikisi de kayma 1 verir ve mod'u calar
        {"start":"2024-07-01","end":"2024-09-28","fy":2025,"fp":"FY","form":"10-K"},
        {"start":"2025-07-01","end":"2025-09-27","fy":2026,"fp":"FY","form":"10-K"},
    ]
    assert _fy_kaymasi(rows) == (0, True), "kisa donemler capa sayilmis"


@pytest.mark.anyio
async def test_seri_mali_yilin_turetildigini_bildirir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue")
    assert s.fiscal_year_derived is True


# ================================================================ H-2: birlestirme
@pytest.mark.anyio
async def test_etiket_degisiminde_gecmis_kirpilmaz(srv):
    """Muhasebe standardi degisikligi 10 yillik gecmisi sessizce siliyordu."""
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=40)
    yillar = sorted(p.fiscal_year for p in s.points)
    assert 2017 in yillar, "eski etiketten gelen donemler kayip"
    assert 2023 in yillar, "yeni etiketten gelen donemler kayip"
    assert set(s.resolved_concepts) == {GERCEK_GELIR_ETIKETI, "SalesRevenueNet"}


@pytest.mark.anyio
async def test_her_nokta_kaynak_etiketini_tasir(srv):
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=40)
    kaynaklar = {p.source_tag for p in s.points}
    assert kaynaklar == {GERCEK_GELIR_ETIKETI, "SalesRevenueNet"}


@pytest.mark.anyio
async def test_ortusen_donemde_en_son_sunulan_kazanir(srv):
    """2021 donemi iki etikette de var. Eski etiketteki kayit 2021'de,
    yenisi 2023'te sunulmus -> yeni kazanmali (999 milyar SAHTE degerdir)."""
    s = await srv.get_concept_series(ticker="AAPL", concept="revenue", limit=40)
    fy21 = [p for p in s.points if p.period_end == "2021-09-25"]
    assert len(fy21) == 1, "ortusen donem cift sayilmis"
    assert fy21[0].value == 365_817_000_000
    assert fy21[0].source_tag == GERCEK_GELIR_ETIKETI


@pytest.mark.anyio
async def test_tum_adaylar_denenir_ilk_eslesende_durulmaz(srv):
    ISTEK_KAYDI.clear()
    await srv.get_concept_series(ticker="AAPL", concept="revenue")
    cagrilan = [u.rsplit("/", 1)[-1].replace(".json", "")
                for u in ISTEK_KAYDI if "companyconcept" in u]
    assert "SalesRevenueNet" in cagrilan, "ilk eslesende durulmus"


# ================================================== §15: tanim = arayuzun kendisi
@pytest.mark.anyio
async def test_her_arac_ve_parametre_aciklamali():
    """Standart §15: modelin gordugu tek sey tanimlardir. Aciklamasiz bir
    parametre, modelin tahmin etmesi demektir. Bu test, ileride aciklamasiz
    arac/parametre eklenmesini yapisal olarak engeller."""
    from edgar_mcp.server import mcp

    for t in await mcp.list_tools():
        assert t.description and len(t.description) >= 80, \
            f"{t.name}: tanim yok veya cok kisa"
        for ad, sema in (t.input_schema.get("properties") or {}).items():
            assert sema.get("description"), f"{t.name}.{ad}: parametre aciklamasi yok"


# --- Dil kontrolu: iki kat, tests/dil.py ------------------------------------
# Eski surum " ve " gibi bosluk-cevreli alt dizgiler ariyordu ve YALNIZCA
# t.description'a bakiyordu. Ikisi de yetersizdi; ustelik kara listenin kendisi
# ayni gun uc kez yetersiz kaldi. Bkz. PATTERNS.md P-17, CLAUDE.md KK-21/KK-22.
from dil import bilinmeyen_kelimeler, turkce_izleri, yabanci_izler  # noqa: E402


def _disa_bakan_yuzey(t) -> list[tuple[str, str]]:
    """Modelin/musterinin gordugu TUM metinler: arac tanimi, parametre
    aciklamalari ve donus semasindaki alan aciklamalari."""
    parcalar = [(f"{t.name}.description", t.description or "")]
    for ad, sema in (t.input_schema.get("properties") or {}).items():
        parcalar.append((f"{t.name}.in.{ad}", sema.get("description") or ""))
    cikti = t.output_schema or {}
    for model, tanim in (cikti.get("$defs") or {}).items():
        for ad, sema in (tanim.get("properties") or {}).items():
            parcalar.append((f"{t.name}.out.{model}.{ad}", sema.get("description") or ""))
    for ad, sema in (cikti.get("properties") or {}).items():
        parcalar.append((f"{t.name}.out.{ad}", sema.get("description") or ""))
    return parcalar


def test_dil_kontrolu_bilinen_ornekleri_ayirt_ediyor():
    """Sezicinin kendisi olculur, varsayilmaz (§2). Ilk iki dizge 13 Agu
    2026'da canlida bulunan gercek kacaklardir - regresyon capasi. Ikincisi
    ayni zamanda kara listenin NEDEN yetmedigini gosterir: icinde Turkceye
    ozgu harf yok ve hicbir kelimesi elle yazilmis listede degildi."""
    TURKCE = [
        "Takma ad (revenue, net_income, total_assets, ...) veya ham "
        "US-GAAP etiketi (orn. NetIncomeLoss)",
        "Ticker bulunamadi: AAPL",
        "Sirketin dosyalamalarini dondurur",
        "Dondurulecek maksimum donem sayisi",
    ]
    INGILIZCE = [
        "Stock ticker symbol, e.g. AAPL",
        "Maximum number of periods to return, most recent last",
        "True if more filings matched than were returned; raise limit",
        "Period end date - the only reliable identifier of a period",
        "US-GAAP tag this value was reported under",
    ]
    for m in TURKCE:
        assert yabanci_izler(m), f"Turkce dizge temiz sayildi: {m!r}"
    for m in INGILIZCE:
        assert not yabanci_izler(m), f"Ingilizce dizge yabanci sanildi: {m!r}"

    # Kara listenin siniri: bu dizgeyi YALNIZCA pozitif liste yakalar.
    assert not turkce_izleri("Ticker bulunamadi: AAPL".replace("bulunamadi", "yok")), \
        "kara liste beklenmedik bicimde eslesti - test artik neyi olctugunu bilmiyor"
    assert bilinmeyen_kelimeler("Ticker yok: AAPL") == ["yok"]


def test_kelime_dagarcigi_kullanilmayan_kelime_biriktirmiyor():
    """Dagarcik disa bakan metinlerden turetildi; olu kelime birikirse liste
    zamanla her seyi kabul eden bir sunger haline gelir (§11)."""
    import asyncio

    from dil import DAGARCIK

    from edgar_mcp.server import mcp

    async def metinler():
        out = []
        for t in await mcp.list_tools():
            out += [m for _, m in _disa_bakan_yuzey(t)]
        return out

    import ast
    import pathlib

    hepsi = " ".join(asyncio.run(metinler()))
    kok = pathlib.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    for f in kok.glob("*.py"):
        for dugum in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(dugum, ast.Raise):
                for alt in ast.walk(dugum):
                    if isinstance(alt, ast.Constant) and isinstance(alt.value, str):
                        hepsi += " " + alt.value

    import re as _re

    kullanilan = {
        w.lower()
        for w in _re.findall(r"[A-Za-z]+", hepsi)
        if len(w) >= 2 and not any(c.isupper() for c in w[1:])
    }
    olu = sorted(DAGARCIK - kullanilan)
    assert not olu, f"kelime dagarciginda artik kullanilmayan kelimeler var: {olu}"


def test_hata_mesajlari_ingilizce():
    """Hata mesajlari semada gorunmez ama modele ve musteriye AYNEN gider.
    Sema taramasi bunlari kacirir; bu yuzden kaynak agacindan `raise`
    ifadelerinin icindeki dizgiler ayrica taranir. 13 Agu 2026'da bu tarama
    `client.py` icinde "Ticker bulunamadi: ..." mesajini yakaladi."""
    import ast
    import pathlib

    kok = pathlib.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    bakilan = 0
    for f in sorted(kok.glob("*.py")):
        agac = ast.parse(f.read_text(encoding="utf-8"))
        for dugum in ast.walk(agac):
            if not isinstance(dugum, ast.Raise):
                continue
            for alt in ast.walk(dugum):
                if isinstance(alt, ast.Constant) and isinstance(alt.value, str):
                    bakilan += 1
                    izler = yabanci_izler(alt.value)
                    assert not izler, (
                        f"{f.name}: hata mesaji Ingilizce degil {izler} -> "
                        f"{alt.value!r}"
                    )
    assert bakilan >= 5, f"hata mesaji taramasi bos donuyor ({bakilan} dizge)"


@pytest.mark.anyio
async def test_arac_tanimlari_ingilizce():
    """Disariya bakan yuzeyin TAMAMI Ingilizce olmali - musteri ABD/AB.
    Kod yorumlari ve karar kayitlari Turkce kalir, onlar ic belgelendirme."""
    from edgar_mcp.server import mcp

    for t in await mcp.list_tools():
        for etiket, metin in _disa_bakan_yuzey(t):
            izler = yabanci_izler(metin)
            assert not izler, f"{etiket} Ingilizce degil: {izler} -> {metin!r}"


# ============================================== KK-11: cekirdek .env okumaz
def test_cekirdek_dotenv_bagimliligi_tasimaz():
    """MCP sunucusu ortamini kendisini calistiran uygulamadan alir. Cekirdege
    dotenv sizarsa gereksiz bir calisma-zamani bagimliligi olur ve Docker/
    Claude Desktop yolunda hicbir sey kazandirmaz."""
    import pathlib

    kok = pathlib.Path(__file__).resolve().parents[1] / "src" / "edgar_mcp"
    for f in kok.glob("*.py"):
        assert "dotenv" not in f.read_text(), f"{f.name} dotenv'e bagimli olmus"


def test_env_example_gercekten_okunan_degiskeni_belgeler():
    """Dokuman ile davranis ortusmeli (§1): .env.example'daki degisken adi,
    kodun gercekte okudugu degisken olmali."""
    import pathlib
    import re

    kok = pathlib.Path(__file__).resolve().parents[1]
    ornek = (kok / ".env.example").read_text()
    istemci = (kok / "src" / "edgar_mcp" / "client.py").read_text()
    belgelenen = set(re.findall(r"^([A-Z_]+)=", ornek, re.M))
    assert belgelenen, ".env.example hicbir degisken belgelemiyor"
    for ad in belgelenen:
        assert ad in istemci, f"{ad} belgelenmis ama kod okumuyor"


# ========================= KO olayi (13 Agu 2026): bos companyconcept yaniti
def _srv_ozel(monkeypatch, ozel_handler):
    monkeypatch.setenv("SEC_USER_AGENT", "Test Runner test@ornek.com")
    from edgar_mcp import server as s
    from edgar_mcp.client import EdgarClient

    c = EdgarClient()
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(ozel_handler),
        headers={"User-Agent": "Test Runner test@ornek.com"},
    )
    s._client = c
    return s


def _bos_units_handler(bos_facts: bool = False):
    """SEC'in KO icin verdigi gercek yanit: HTTP 200, dogru label, units.USD
    VAR ama icinde satir YOK. 404 degil, hata degil - bos basari."""
    def h(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "companyconcept" in u:
            ISTEK_KAYDI.append(u)
            # Gercek govde (KO, 13 Agu 2026): USD bir dizi degil, BOS SOZLUK.
            return httpx.Response(200, json={"cik": 320193, "taxonomy": "us-gaap",
                                             "label": "Assets", "units": {"USD": {}}})
        if "companyfacts" in u and bos_facts:
            ISTEK_KAYDI.append(u)
            bos = {"facts": {"us-gaap": {t: {"label": t, "units": {"USD": []}}
                                         for t in FACTS["facts"]["us-gaap"]}}}
            return httpx.Response(200, json=bos)
        return handler(request)
    return h


@pytest.mark.anyio
async def test_bos_companyconcept_yanitinda_companyfacts_e_dusulur(monkeypatch):
    """Olculdu (13 Agu 2026, KO): companyconcept bes farkli kosulda da bos
    dondu, ayni etiket companyfacts'te 144 satirdi. Bos yanit basari sayilirsa
    model 'bu sirket bunu raporlamiyor' diye okur - yanlis cevap, hata yok."""
    ISTEK_KAYDI.clear()
    s = _srv_ozel(monkeypatch, _bos_units_handler())
    seri = await s.get_concept_series(ticker="AAPL", concept="revenue")

    assert seri.source_endpoint == "companyfacts", "yedek uca dusulmemis"
    assert seri.total_periods > 0, "companyfacts'te veri varken bos donuldu"
    assert any("companyfacts" in u for u in ISTEK_KAYDI)


@pytest.mark.anyio
async def test_normal_durumda_companyfacts_cekilmez(srv):
    """companyfacts birkac MB. Yedek yol yalnizca gerektiginde acilmali,
    her cagride degil."""
    ISTEK_KAYDI.clear()
    seri = await srv.get_concept_series(ticker="AAPL", concept="revenue")
    assert seri.source_endpoint == "companyconcept"
    assert not any("companyfacts" in u for u in ISTEK_KAYDI), \
        "gerek yokken 5 MB'lik uc cekilmis"


@pytest.mark.anyio
async def test_iki_uc_da_bossa_sessiz_basari_yerine_hata(monkeypatch):
    """Ikisi de bossa donecek veri yok. O zaman bos bir 'basari' degil,
    eyleme donusturulebilir hata verilir (P-13)."""
    s = _srv_ozel(monkeypatch, _bos_units_handler(bos_facts=True))
    with pytest.raises(ValueError) as e:
        await s.get_concept_series(ticker="AAPL", concept="revenue")
    mesaj = str(e.value)
    assert "companyfacts" in mesaj and "companyconcept" in mesaj
    assert "sec_edgar_list_available_concepts" in mesaj


@pytest.mark.anyio
async def test_liste_olmayan_birim_govdesi_cokertmez(monkeypatch):
    """SEC'in bos yaniti `units.USD` icin dizi degil SOZLUK veriyor ({}).
    Bos sozluk zaten sifir satir sayilir; bu test bir adim otesini,
    BOS OLMAYAN bir sozlugu kapsiyor. Boyle bir yanit gozlenmedi - bu
    savunma amacli bir koruma: beklenmedik sekil ne cokertmeli ne de
    sessizce basari gibi gorunmeli."""
    def h(request: httpx.Request) -> httpx.Response:
        u = str(request.url)
        if "companyconcept" in u:
            return httpx.Response(200, json={
                "label": "Assets",
                "units": {"USD": {"0": {"end": "2025-12-31", "val": 1}}},
            })
        return handler(request)

    s = _srv_ozel(monkeypatch, h)
    seri = await s.get_concept_series(ticker="AAPL", concept="revenue")
    # companyconcept kullanilamaz sekilde geldi -> yedek uc devreye girmeli
    assert seri.source_endpoint == "companyfacts"
    assert seri.total_periods > 0


@pytest.mark.anyio
async def test_karisik_birim_sekli_gecerli_satirlari_korur(monkeypatch):
    """Bir birim kullanilabilir liste, digeri kullanilamaz sekil olabilir.
    Bu durumda gecerli satirlar KAYBOLMAMALI ve kod cokmemeli - yani
    kullanilamaz birim atlanir, yedek uca da dusulmez (veri zaten var)."""
    def h(request: httpx.Request) -> httpx.Response:
        if "companyconcept" in str(request.url):
            return httpx.Response(200, json={
                "label": "Revenues",
                "units": {"USD": CONCEPT["units"]["USD"], "shares": {"0": {}}},
            })
        return handler(request)

    s = _srv_ozel(monkeypatch, h)
    seri = await s.get_concept_series(ticker="AAPL", concept="revenue")
    assert seri.source_endpoint == "companyconcept", "gereksiz yere yedege dusuldu"
    assert seri.total_periods > 0
    assert all(p.unit == "USD" for p in seri.points)
