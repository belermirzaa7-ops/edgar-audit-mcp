"""Disa bakan metinlerin dilini olcen yardimcilar (KK-9, KK-22).

Iki kat, biri otekinin acigini kapatiyor:

1. `turkce_izleri` - Turkceye ozgu harfler ve sik gecen islev kelimeleri.
   Ucuz ve hizli, ama KARA LISTE: yalnizca yazarinin akil ettigini gorur.
2. `bilinmeyen_kelimeler` - POZITIF liste. Metindeki her kelime
   `kelime_dagarcigi.txt` icinde olmali. Tanimadigi kelimede kirmiziya doner,
   dolayisiyla dilden bagimsizdir; "bulunamadi" da yakalanir, "Wortliste" de.

Ikinci katin varlik sebebi olculdu: 13 Agustos 2026'da kara liste ayni gun
uc kez yetersiz kaldi (parametre aciklamasi, donus semasi, hata mesaji).
"""
from __future__ import annotations

import pathlib
import re

KOK = pathlib.Path(__file__).resolve().parent

_TR_KELIME = re.compile(
    r"\b(?:ve|veya|ile|icin|için|bir|olarak|degil|değil|gibi|ancak|"
    r"orn|örn|takma|bulunamadi|bulunamadı|"
    r"etiket|etiketi|etiketler|etiketleri|"
    r"sirket|şirket|sirketin|şirketin|sirketler|şirketler|"
    r"donem|dönem|donemi|dönemi|donemler|dönemler|"
    r"veri|verisi|veriler|verileri|"
    r"deger|değer|degeri|değeri|"
    r"dosyalama|dosyalamalar|dosyalamalari|"
    r"dondur|döndür|dondurur|döndürür|kullanilir|kullanılır|cagir|çağır|"
    r"hata|arac|araç|araci|aracı|sayfa|sayfalama|adet|tarih|kayit|kayıt)\b",
    re.IGNORECASE,
)
_TR_HARF = re.compile(r"[ışğçöüİŞĞÇÖÜ]")
_TOKEN = re.compile(r"[A-Za-zçğıöşüÇĞİÖŞÜ]+")


def turkce_izleri(metin: str) -> list[str]:
    """Kara liste kati. Bos liste = bu katta temiz."""
    return sorted(set(_TR_KELIME.findall(metin)) | set(_TR_HARF.findall(metin)))


def _dagarcik() -> set[str]:
    satirlar = (KOK / "kelime_dagarcigi.txt").read_text(encoding="utf-8").splitlines()
    return {s.strip() for s in satirlar if s.strip() and not s.startswith("#")}


DAGARCIK = _dagarcik()


def bilinmeyen_kelimeler(metin: str) -> list[str]:
    """Pozitif liste kati. Tanimlayici gorunumlu tokenlar (ilk harften sonra
    buyuk harf iceren: NetIncomeLoss, USD, CIK, AAPL) ve tek harfliler atlanir;
    geri kalan her kelime dagarcikta olmali."""
    bulunan = []
    for token in _TOKEN.findall(metin):
        if len(token) < 2 or any(c.isupper() for c in token[1:]):
            continue
        if token.lower() not in DAGARCIK:
            bulunan.append(token.lower())
    return sorted(set(bulunan))


def yabanci_izler(metin: str) -> list[str]:
    """Iki kat birlikte. Disa bakan her metin bundan temiz gecmeli."""
    return sorted(set(turkce_izleri(metin)) | set(bilinmeyen_kelimeler(metin)))
