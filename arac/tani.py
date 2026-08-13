"""SEC'in tek bir companyconcept yanitini HAM haliyle olcer.

Neden var: 13 Agu 2026'da KO (CIK 0000021344) icin `get_concept_series` her
kavramda `total_periods: 0` dondu, ama ayni sunucudaki `list_available_concepts`
(companyfacts) ayni etiket icin 144 veri noktasi bildirdi. Olcum, SEC'in
`HTTP 200` + dogru `label` + **bos `units.USD`** (346 bayt) dondurdugunu
gosterdi; ayni adres baska bir agdan dolu geldi. Ham govde:
`{"cik":21344,...,"units":{"USD":{}}}` - dizi beklenen yerde bos SOZLUK.

Tek istek modu bunu gosterir. `--matris` modu SEBEBI ayirt eder: ayni yaniti
farkli kosullarda tekrar ister ve hangi degiskenin sonucu degistirdigini
gosterir. Hipotezler ve hangi satirin onlari ayirt ettigi:

  H1 kenar onbelleginde bozuk nesne -> "onbellek-bypass" dolu doner, "tekrar"
     bos kalir; `age` yuksek, `x-cache` HIT.
  H2 User-Agent'a bagli kisitlama  -> "farkli-ua" dolu doner.
  H3 sikistirma/istemci sorunu     -> "sikistirmasiz" dolu doner.
  H4 SEC'te gercekten yok          -> hepsi bos VE companyfacts da bos.
     (companyfacts dolu ise ucun kendisi tutarsiz demektir.)

Kullanim:
    python arac/tani.py KO Assets
    python arac/tani.py KO Assets --matris     # sebep ayirt etme
    python arac/tani.py AAPL Assets --matris   # calisan referans
    python arac/tani.py --tarama               # kac sirket etkileniyor
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "src"))

from arac.ortam import env_yukle  # noqa: E402

env_yukle()

from edgar_mcp.client import SEC_DATA, EdgarClient  # noqa: E402

# Onbellek/dagitim katmanini ele veren basliklar. Yoksa "-" yazilir; olmayan
# basligi var saymak, olmayan veriyi var saymak kadar kotudur.
BASLIKLAR = ("age", "x-cache", "via", "x-amz-cf-pop", "x-amz-cf-id",
             "cache-control", "etag", "last-modified", "date", "server")


def _satir_sayisi(d: dict) -> tuple[int, list[str]]:
    """companyconcept yanitindaki toplam satir sayisi ve birim anahtarlari."""
    birimler = d.get("units", {}) or {}
    return sum(len(v) for v in birimler.values()), list(birimler)


def _basliklari_yaz(r, girinti: str = "  ") -> None:
    for ad in BASLIKLAR:
        print(f"{girinti}{ad:<14}: {r.headers.get(ad, '-')}")


async def _iste(c: EdgarClient, url: str, basliklar: dict | None = None):
    await c._limiter.acquire()
    return await c._http.get(url, headers=basliklar)


async def _olc(c: EdgarClient, etiket: str, url: str, basliklar: dict | None = None) -> int:
    """Tek olcum satiri: durum, bayt, satir sayisi. Satir sayisini dondurur."""
    r = await _iste(c, url, basliklar)
    if r.status_code != 200:
        print(f"{etiket:<16} HTTP {r.status_code}  ({len(r.content)} bayt)")
        return -1
    try:
        d = r.json()
    except json.JSONDecodeError:
        print(f"{etiket:<16} JSON COZULEMEDI ({len(r.content)} bayt)")
        return -1
    satir, birimler = _satir_sayisi(d)
    durum = "BOS" if satir == 0 else f"{satir} satir"
    print(f"{etiket:<16} HTTP 200  {len(r.content):>7} bayt  birim={birimler}  {durum}")
    _basliklari_yaz(r, girinti="    ")
    return satir


async def _tek_istek(c: EdgarClient, url: str) -> int:
    print(f"URL        : {url}")
    r = await _iste(c, url)
    print(f"HTTP       : {r.status_code}")
    print(f"Encoding   : {r.headers.get('content-encoding')!r}")
    print(f"Icerik tipi: {r.headers.get('content-type')!r}")
    print(f"Govde      : {len(r.content)} bayt (cozulmus: {len(r.text)} karakter)")
    _basliklari_yaz(r)
    if r.status_code != 200:
        print("--- govde (ilk 500) ---")
        print(r.text[:500])
        return 1

    try:
        d = r.json()
    except json.JSONDecodeError as e:
        print(f"JSON COZULEMEDI: {e}")
        print("--- govde (ilk 500) ---")
        print(r.text[:500])
        return 1

    print(f"Ust anahtarlar: {sorted(d)}")
    print(f"label      : {d.get('label')!r}")
    units = d.get("units", {})
    print(f"units      : {list(units)} ({len(units)} birim)")
    if not units:
        print(">>> units BOS. Sunucu 200 dondu ama veri yok.")
        print("--- govde (ilk 500) ---")
        print(r.text[:500])
        return 1
    bos = True
    for birim, satirlar in units.items():
        print(f"  {birim}: {len(satirlar)} satir")
        if satirlar:
            bos = False
            print(f"    ilk : {json.dumps(satirlar[0])}")
            print(f"    son : {json.dumps(satirlar[-1])}")
            eksik_end = sum(1 for s in satirlar if not s.get("end"))
            eksik_val = sum(1 for s in satirlar if "val" not in s)
            print(f"    'end' eksik: {eksik_end}, 'val' eksik: {eksik_val}")
    if bos:
        print(">>> Birim var ama SATIR YOK. Sunucu 200 dondu, veri gelmedi.")
        print("--- govde (ilk 500) ---")
        print(r.text[:500])
        return 1
    return 0


async def _matris(c: EdgarClient, cik: str, tag: str, url: str) -> int:
    print(f"URL        : {url}")
    print("Her satir ayni veriyi FARKLI bir kosulda istiyor. Hangi satirin")
    print("dolu dondugu sebebi soyler (bkz. dosya basindaki H1-H4).")
    print("-" * 78)

    sonuc: dict[str, int] = {}
    sonuc["temel"] = await _olc(c, "temel", url)
    sonuc["tekrar"] = await _olc(c, "tekrar", url)

    # Onbellek anahtari yolu iceriyor; ise yaramaz bir sorgu parametresi
    # nesneyi degistirmeden anahtari degistirir.
    tuz = os.urandom(4).hex()
    sonuc["onbellek-bypass"] = await _olc(c, "onbellek-bypass", f"{url}?tani={tuz}")

    sonuc["farkli-ua"] = await _olc(
        c, "farkli-ua", url,
        {"User-Agent": "Research Diagnostic diagnostic@example.com"},
    )
    sonuc["sikistirmasiz"] = await _olc(
        c, "sikistirmasiz", url, {"Accept-Encoding": "identity"},
    )

    # Ayni veriyi BASKA bir uctan iste: companyfacts.
    print("-" * 78)
    facts_url = f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json"
    r = await _iste(c, facts_url)
    if r.status_code != 200:
        print(f"companyfacts     HTTP {r.status_code}")
        sonuc["companyfacts"] = -1
    else:
        gaap = (r.json().get("facts", {}) or {}).get("us-gaap", {}) or {}
        kayit = gaap.get(tag)
        n = sum(len(v) for v in (kayit or {}).get("units", {}).values()) if kayit else 0
        etiketli = "etiket YOK" if kayit is None else f"{n} satir"
        print(f"companyfacts     HTTP 200  {len(r.content):>7} bayt  "
              f"us-gaap/{tag}: {etiketli}")
        sonuc["companyfacts"] = n

    print("-" * 78)
    print("OZET:", ", ".join(f"{k}={v}" for k, v in sonuc.items()))
    cc_dolu = [k for k in ("temel", "tekrar", "onbellek-bypass", "farkli-ua",
                           "sikistirmasiz") if sonuc.get(k, 0) > 0]
    if not cc_dolu and sonuc.get("companyfacts", 0) > 0:
        print("YORUM: companyconcept hicbir kosulda veri vermedi ama companyfacts")
        print("       ayni etiket icin veri veriyor -> iki uc TUTARSIZ (H4 degil).")
        return 1
    if sonuc.get("temel", 0) == 0 and cc_dolu:
        print(f"YORUM: temel istek bos, ama su kosul(lar) dolu dondu: {cc_dolu}")
        print("       Farki yaratan degisken bu -> yukaridaki hipotez listesine bak.")
        return 1
    if sonuc.get("temel", 0) > 0:
        print("YORUM: temel istek dolu dondu. Bu ticker/etiket icin sorun yok")
        print("       (ya da sorun araliklı - tekrar calistirmakta fayda var).")
        return 0
    print("YORUM: hicbir uc veri vermedi. SEC'te bu etiket bu sirket icin")
    print("       gercekten olmayabilir (H4).")
    return 1


TARAMA_TICKERLARI = ["AAPL", "MSFT", "JNJ", "PEP", "KO", "WMT", "TGT", "NVDA",
                     "JPM", "NKE", "XOM", "PG", "INTC", "CSCO", "DIS"]


async def _tarama(c: EdgarClient, tag: str) -> int:
    """Etkinin buyuklugunu olcer: kac sirkette companyconcept bos donuyor.
    Tek bir sirketten 'bu SEC'in genel sorunu' sonucu cikarilamaz; bu yuzden
    sayiliyor, tahmin edilmiyor."""
    print(f"Etiket: us-gaap/{tag}   (concept = companyconcept, facts = companyfacts)")
    print(f"{'ticker':<8} {'concept':>9} {'facts':>9}  durum")
    print("-" * 52)
    bos, hatali = [], []
    for ticker in TARAMA_TICKERLARI:
        try:
            cik = await c.cik_for_ticker(ticker)
        except ValueError:
            print(f"{ticker:<8} {'-':>9} {'-':>9}  ticker cozulemedi")
            hatali.append(ticker)
            continue

        url = f"{SEC_DATA}/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
        r = await _iste(c, url)
        n_concept = _satir_sayisi(r.json())[0] if r.status_code == 200 else -1

        rf = await _iste(c, f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json")
        n_facts = 0
        if rf.status_code == 200:
            kayit = ((rf.json().get("facts") or {}).get("us-gaap") or {}).get(tag)
            n_facts = sum(len(v) for v in (kayit or {}).get("units", {}).values())

        if n_concept < 0:
            durum = "concept HTTP hatasi"
        elif n_concept == 0 and n_facts > 0:
            durum = "BOS -> yedek uc gerekli"
            bos.append(ticker)
        elif n_concept == 0:
            durum = "iki uc da bos"
            bos.append(ticker)
        else:
            durum = "ok"
        print(f"{ticker:<8} {n_concept:>9} {n_facts:>9}  {durum}")

    print("-" * 52)
    print(f"OZET: {len(bos)}/{len(TARAMA_TICKERLARI) - len(hatali)} sirkette "
          f"companyconcept bos" + (f" -> {bos}" if bos else ""))
    return 1 if bos else 0


async def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    bayraklar = {a for a in sys.argv[1:] if a.startswith("--")}
    if bayraklar - {"--matris", "--tarama"}:
        print(__doc__)
        return 2

    if "--tarama" in bayraklar:
        if len(argv) > 1:
            print(__doc__)
            return 2
        c = EdgarClient()
        try:
            return await _tarama(c, argv[0] if argv else "Assets")
        finally:
            await c.aclose()

    if len(argv) != 2:
        print(__doc__)
        return 2
    ticker, tag = argv

    c = EdgarClient()
    try:
        cik = await c.cik_for_ticker(ticker)
        url = f"{SEC_DATA}/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
        if "--matris" in bayraklar:
            return await _matris(c, cik, tag, url)
        return await _tek_istek(c, url)
    finally:
        await c.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
