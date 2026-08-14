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
        self._facts_cache: dict[str, dict] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, url: str) -> dict:
        await self._limiter.acquire()
        r = await self._http.get(url)
        r.raise_for_status()
        return r.json()

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

    async def submissions(self, cik: str) -> dict:
        return await self._get(f"{SEC_DATA}/submissions/CIK{cik}.json")

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
        return await self._get(dizin_url.rstrip("/") + "/index.json")

    async def company_facts(self, cik: str) -> dict:
        """companyfacts yaniti birkac MB olabilir; CIK basina bir kez cekilir."""
        if cik not in self._facts_cache:
            self._facts_cache[cik] = await self._get(
                f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik}.json"
            )
        return self._facts_cache[cik]
