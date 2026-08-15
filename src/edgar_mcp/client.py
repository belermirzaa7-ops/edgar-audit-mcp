"""SEC EDGAR REST istemcisi.

SEC kurallari (kaynak: sec.gov/os/webmaster-faq#developers):
  - API anahtari YOK.
  - User-Agent zorunlu, iletisim e-postasi icermeli.
  - Ust sinir 10 istek/saniye.
"""
from __future__ import annotations

import asyncio
import os
import time

import httpx

SEC_DATA = "https://data.sec.gov"
SEC_WWW = "https://www.sec.gov"


def _durum_mesaji(kod: int, url: str) -> str:
    if kod == 403:
        return (
            f"SEC refused the request with HTTP 403 for {url}. SEC blocks "
            "clients it considers undeclared automated tools: check that "
            "SEC_USER_AGENT names a real person or company and a working "
            "contact email, then retry. A burst of requests can also trigger "
            "this even with a valid header."
        )
    if kod in (429, 503):
        return (
            f"SEC is throttling or temporarily unavailable (HTTP {kod}) for "
            f"{url}. This server already self-limits to 8 requests per second; "
            "wait a few seconds and retry the same call."
        )
    return (
        f"SEC returned HTTP {kod} for {url}. This is an upstream failure, not "
        "a missing value: retrying shortly is reasonable, and a persistent "
        "failure means the endpoint or the identifier in the URL is wrong."
    )


class RateLimiter:
    """SEC'in 10 istek/sn sinirini asmayan basit token-bucket."""

    VARSAYILAN_HIZ = 8.0  # SEC ust siniri 10/sn; altinda kaliyoruz

    def __init__(self, rate_per_sec: float | None = None) -> None:
        rate_per_sec = rate_per_sec or float(
            os.environ.get("SEC_RATE_LIMIT_PER_SEC", self.VARSAYILAN_HIZ)
        )
        self._min_interval = 1.0 / rate_per_sec
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class EdgarClient:
    def __init__(self, user_agent: str | None = None) -> None:
        ua = user_agent or os.environ.get("SEC_USER_AGENT")
        if not ua or "@" not in ua:
            raise RuntimeError(
                "SEC_USER_AGENT environment variable is required and must "
                "contain a contact email. "
                'Example: SEC_USER_AGENT="Jane Doe jane@example.com"'
            )
        self._limiter = RateLimiter()
        self._http = httpx.AsyncClient(
            headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )
        self._ticker_cache: dict[str, str] | None = None
        # Onbelleklerin hepsi SINIRLI. companyfacts en buyuk nesne (olculdu:
        # 11 MB JSON -> 45 MB yerlesik, 4,1 kat); sinirsiz birakmak, stdio
        # surecinin masaustu istemci acik kaldigi surece yasadigi bir ortamda
        # yirmi sirket taranınca ~1 GB demekti (15 Agu 2026'da bulundu).
        self._facts_cache: dict[str, dict] = {}
        self._subs_cache: dict[str, dict] = {}
        self._index_cache: dict[str, dict] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _sinirla(onbellek: dict, anahtar: str, deger, sinir: int) -> None:
        if anahtar not in onbellek and len(onbellek) >= sinir:
            onbellek.pop(next(iter(onbellek)))
        onbellek[anahtar] = deger

    async def _get(self, url: str) -> dict:
        """SEC'ten JSON. Hata durumlari MODELE ANLAMLI mesaj dondurur.

        Neden (15 Agu 2026'da bulundu): yalnizca 404 ele aliniyordu; 403, 429,
        5xx ve "JSON yerine HTML hata sayfasi" durumlari cig `HTTPStatusError`
        ya da `JSONDecodeError` olarak modele gidiyordu. SEC'in gercek
        kisitlama yaniti HTTP 403 + HTML govde ("Your Request Originates from
        an Undeclared Automated Tool") - yani en olasi hata, en anlamsiz mesaji
        uretiyordu. §18/P-13: hata mesaji ne yapilacagini soylemeli.
        """
        await self._limiter.acquire()
        r = await self._http.get(url)

        if r.status_code == 404:
            # 404 kontrol akisi: cagiran taraf "bu etiket/cerceve yok" diye
            # okuyor. Istisna turu korunuyor.
            r.raise_for_status()

        if r.status_code >= 400:
            raise ValueError(_durum_mesaji(r.status_code, url))

        try:
            return r.json()
        except ValueError as e:
            bas = (r.text or "").lstrip()[:60].replace("\n", " ")
            raise ValueError(
                f"SEC returned a body that is not JSON for {url}. It began "
                f"with: {bas!r}. An HTML body here is usually SEC's throttling "
                "or block page rather than data; wait a few seconds and retry, "
                "and check that SEC_USER_AGENT names a real contact email."
            ) from e

    async def cik_for_ticker(self, ticker: str) -> str:
        """Ticker -> 10 haneli sifir dolgulu CIK."""
        if self._ticker_cache is None:
            data = await self._get(f"{SEC_WWW}/files/company_tickers.json")
            self._ticker_cache = {
                row["ticker"].upper(): str(row["cik_str"]).zfill(10)
                for row in data.values()
            }
        cik = self._ticker_cache.get(ticker.upper())
        if cik is None:
            raise ValueError(
                f"Ticker '{ticker}' is not in SEC's company_tickers.json. "
                "Check the symbol; that file lists only registrants that file "
                "with the SEC, so foreign private issuers, funds and delisted "
                "names may be absent."
            )
        return cik

    async def ticker_for_cik(self, cik: str) -> str | None:
        """CIK -> ticker. Ayni CIK birden fazla sembol tasiyabilir (GOOG/GOOGL
        gibi hisse siniflari); alfabetik ilki doner ve bu bilincli bir
        sadelestirmedir - cerceve verisi CIK basina tek satir tasidigi icin
        hangi sinifin gosterildigi sorusu orada zaten yok."""
        if self._ticker_cache is None:
            await self.cik_for_ticker("AAPL")     # haritayi doldurur
        assert self._ticker_cache is not None
        eslesen = sorted(t for t, c in self._ticker_cache.items() if c == cik)
        return eslesen[0] if eslesen else None

    async def frame(self, taxonomy: str, tag: str, unit: str, frame: str) -> dict | None:
        """Bir donemin TUM sirketlerdeki degeri. Cerceve yoksa None.

        404 burada hata degil bilgidir: istenen etiket/donem/birim ucluşu icin
        SEC'in cercevesi ya hic yoktur ya da suresel/anlik turu tutmamistir
        (bilanco kalemleri `CY2025Q1I`, gelir tablosu kalemleri `CY2025Q1`).
        Cagiran taraf bu ayrimi kullanip otekini deniyor.
        """
        url = f"{SEC_DATA}/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{frame}.json"
        try:
            return await self._get(url)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def submissions(self, cik: str) -> dict:
        """1-2 MB, dokuz aracin besi kullaniyor. Onbelleksiz birakmak her
        cagride yeniden indirmek demekti."""
        if cik not in self._subs_cache:
            self._sinirla(self._subs_cache, cik,
                          await self._get(f"{SEC_DATA}/submissions/CIK{cik}.json"), 4)
        return self._subs_cache[cik]

    async def company_concept(self, cik: str, concept: str, taxonomy: str = "us-gaap") -> dict:
        return await self._get(
            f"{SEC_DATA}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
        )

    async def filing_document(self, url: str) -> str:
        """Dosyalama belgesinin HAM govdesi (HTML ya da duz metin).

        JSON degil metin doner; `_get` kullanilamaz. Onbellek BURADA DEGIL:
        cagiran taraf ham HTML'i degil, cevrilmis metni saklar (bkz.
        server._belge_metni). 10 MB'lik HTML'i saklamak, ondan uretilen
        0,5 MB'lik metni saklamaktan yirmi kat pahali.
        """
        await self._limiter.acquire()
        r = await self._http.get(url)
        r.raise_for_status()
        return r.text

    async def filing_index(self, dizin_url: str) -> dict:
        """Bir dosyalamanin dosya listesi (SEC her klasor icin index.json verir).

        Bir 8-K'nin govdesi genellikle BIRINCIL belgede degil, ekindedir:
        olculdu (14 Agu 2026) - TSLA'nin 2026 Q2 teslimat bulteni 8-K'nin
        birincil belgesinde degil `exhibit...htm` ekinde, ve arac yalnizca
        birincil belgeyi okuyordu.
        """
        url = dizin_url.rstrip("/") + "/index.json"
        if url not in self._index_cache:
            self._sinirla(self._index_cache, url, await self._get(url), 4)
        return self._index_cache[url]

    async def company_facts(self, cik: str) -> dict:
        """companyfacts yaniti birkac MB olabilir; CIK basina bir kez cekilir."""
        if cik not in self._facts_cache:
            self._sinirla(self._facts_cache, cik, await self._get(
                f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json"), 2)
        return self._facts_cache[cik]
