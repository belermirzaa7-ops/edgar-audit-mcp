"""Yerel scriptler icin .env yukleyici.

Neden burada ve neden cekirdekte degil (bkz. CLAUDE.md KK-11): MCP sunucusu
ortam degiskenlerini kendisini calistiran uygulamadan alir (Claude Desktop'in
config'i, Docker'in --env-file'i). Sunucunun .env okumasi gerekmiyor ve
gereksiz bagimlilik olurdu. .env yalnizca elle calistirilan scriptler icin.

Yukleme neden kendi ayristiricisini de tasiyor (15 Agu 2026 olayi): eski surum
`python-dotenv` yoksa SESSIZCE geciyordu. O gun tani araci
"SEC_USER_AGENT ... is required" diye patladi; dosya yerindeydi, okunmamisti.
Iki bagimsiz sebep ayni sessiz yola cikiyor:
  - script sanal ortam disindaki bir Python ile calistirilirsa `dotenv` orada
    kurulu olmayabilir,
  - PowerShell'in `Out-File -Encoding utf8` komutu dosyanin basina BOM koyar ve
    ilk anahtar `﻿SEC_USER_AGENT` olarak okunur.
Kullaniciya gorunen belirti ikisinde de ayni: "ortam degiskeni yok". Bagimlilik
opsiyoneldir, ama opsiyonel olan sey YUKLEMENIN KENDISI degil.
"""
from __future__ import annotations

import os
import pathlib

ENV_YOLU = pathlib.Path(__file__).resolve().parents[1] / ".env"


def _ayristir(satir: str) -> tuple[str, str] | None:
    """`KEY="value"` -> ("KEY", "value"). Yorum, bos satir ve anahtarsiz satir
    None doner. `export KEY=deger` bicimi de kabul ediliyor: kopyala-yapistir
    ile gelen en yaygin varyant."""
    # BOM burada DEGIL, dosya cozulurken yutuluyor (`utf-8-sig`). Iki yerde
    # birden ele almak, ikisinden birini bozan bir degisikligin hicbir testi
    # kirmiziya dondurmemesi demekti - olculdu: enjeksiyon "KORUMASIZ" dedi.
    s = satir.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    if s.startswith("export "):
        s = s[len("export "):].lstrip()
    anahtar, _, deger = s.partition("=")
    anahtar = anahtar.strip()
    if not anahtar:
        return None
    deger = deger.strip()
    if len(deger) >= 2 and deger[0] == deger[-1] and deger[0] in "\"'":
        deger = deger[1:-1]
    return anahtar, deger


def _elle_yukle(yol: pathlib.Path) -> None:
    """Bagimliliksiz yedek okuyucu. `utf-8-sig` BOM'u yutar.

    Mevcut ortam degiskenleri EZILMEZ: kabuğunda degiskeni elle veren biri,
    dosyadaki eski degerin onu sessizce gecersiz kilmasini beklemez.
    """
    try:
        metin = yol.read_text(encoding="utf-8-sig")
    except OSError:
        return
    for satir in metin.splitlines():
        cift = _ayristir(satir)
        if cift:
            os.environ.setdefault(cift[0], cift[1])


def env_yukle() -> None:
    """Proje kokundeki .env dosyasini yukler.

    `python-dotenv` varsa once o calisir (quote/escape kurallarini bizim
    ayristiricimizdan daha eksiksiz uygular), ardindan yedek okuyucu dosyada
    kalan anahtarlari tamamlar. Ikisi de `setdefault` semantigiyle davranir.
    """
    if not ENV_YOLU.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv(ENV_YOLU, encoding="utf-8-sig")
    _elle_yukle(ENV_YOLU)
