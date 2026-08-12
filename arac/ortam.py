"""Yerel scriptler icin .env yukleyici.

Neden burada ve neden cekirdekte degil (bkz. CLAUDE.md KK-11): MCP sunucusu
ortam degiskenlerini kendisini calistiran uygulamadan alir (Claude Desktop'in
config'i, Docker'in --env-file'i). Sunucunun .env okumasi gerekmiyor ve
gereksiz bagimlilik olurdu. .env yalnizca elle calistirilan scriptler icin.
"""
from __future__ import annotations

import pathlib


def env_yukle() -> None:
    """Proje kokundeki .env dosyasini yukler. python-dotenv yoksa sessizce gecer;
    o durumda ortam degiskeni elle verilmis olmali."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")
