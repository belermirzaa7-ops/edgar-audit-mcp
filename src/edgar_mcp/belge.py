"""Dosyalama belgesini metne cevirir ve bolumlerine ayirir.

Neden bagimlilik yok: cekirdek yalnizca mcp/httpx/pydantic'e dayaniyor
(KK-3). HTML ayristirmasi icin stdlib `html.parser` yetiyor; BeautifulSoup
eklemek calisma-zamani bagimliligini sirf birkac satir icin buyuturdu.

Iki tuzak burada cozuluyor, ikisi de olculebilir:

1. **Icindekiler tablosu.** Bir 10-K'da "Item 7. Management's Discussion..."
   ifadesi en az iki kez gecer: once icindekiler tablosunda, sonra bolumun
   kendisinde. Ilk eslesmeyi almak, modele iki satirlik bir baglanti listesi
   dondurur ve bolum "bos" gorunur. Cozum: bir baslik adayi, ancak kendisinden
   sonraki metin ANLAMLI uzunluktaysa gercek bolum sayilir.
2. **Tablolar.** Mali tablolar HTML tablosudur; etiketler duz atilirsa satirlar
   birbirine yapisir ve sayilar okunamaz hale gelir. Hucreler ` | ` ile,
   satirlar yeni satirla ayriliyor.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# Bir bolum basligi sayilmak icin ardindan gelmesi gereken en az karakter.
# Icindekiler tablosundaki girisler birbirini birkac on karakterde izler;
# gercek bolumler binlerce karakter surer. 400 ikisinin arasinda genis bir
# aralikta duruyor - olculdu: tipik icindekiler girisi < 120 karakter.
BOLUM_ESIGI = 400

_ATLANAN = {"script", "style", "head", "title", "meta", "link"}
_BLOK = {"p", "div", "br", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6",
         "li", "ul", "ol", "section", "article", "header", "footer"}


class _MetinToplayici(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parcalar: list[str] = []
        self._atla = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _ATLANAN:
            self._atla += 1
        elif tag in ("td", "th"):
            self.parcalar.append(" | ")
        elif tag in _BLOK:
            self.parcalar.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _ATLANAN and self._atla:
            self._atla -= 1
        elif tag in _BLOK:
            self.parcalar.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._atla:
            self.parcalar.append(data)


def metne_cevir(govde: str) -> str:
    """HTML (ya da duz metin) -> okunabilir duz metin."""
    if "<" not in govde:
        return _bosluk_topla(govde)
    ayristirici = _MetinToplayici()
    ayristirici.feed(govde)
    ayristirici.close()
    return _bosluk_topla("".join(ayristirici.parcalar))


def _bosluk_topla(metin: str) -> str:
    metin = metin.replace("\xa0", " ").replace("​", "")
    metin = re.sub(r"[ \t]+", " ", metin)
    metin = re.sub(r" *\n *", "\n", metin)
    metin = re.sub(r"\n{3,}", "\n\n", metin)
    return metin.strip()


# "Item 7.", "ITEM 1A -", "Item 9B." ... Baslik satirin basinda olmali.
# Satir basindaki `|`, tire ve yildizlar: gercek dosyalamalarda basliklar
# HTML TABLOSU icinde durur, metne cevrilince satir " | " ile baslar. Bu izni
# vermezsek tablo yerlesimli 10-K'larda hicbir bolum bulunamaz.
_ONEK = r"^[\s|>*\-–—.]*"
_ITEM = re.compile(_ONEK + r"item\s+(\d{1,2}[a-c]?)\s*[.\-:—|]?\s*(.{0,90})$",
                   re.IGNORECASE | re.MULTILINE)
# "Note 12. Income Taxes" ya da tek basina "Income Taxes" gibi dipnot basliklari
_NOT = re.compile(_ONEK + r"note\s+(\d{1,2})\s*[.\-:—|]?\s*(.{0,90})$",
                  re.IGNORECASE | re.MULTILINE)


def bolumler(metin: str, esik: int = BOLUM_ESIGI) -> list[tuple[str, int, int]]:
    """(baslik, baslangic, bitis) listesi. Icindekiler tablosu elenir.

    Eleme kurali: bir aday basliktan sonraki metin, bir sonraki adaya kadar
    `esik` karakterden kisaysa o aday gercek bolum degildir.
    """
    adaylar: list[tuple[str, int]] = []
    for kalip in (_ITEM, _NOT):
        for m in kalip.finditer(metin):
            baslik = " ".join(m.group(0).split()).strip(" |*-.")
            adaylar.append((baslik, m.start()))
    adaylar.sort(key=lambda x: x[1])

    out: list[tuple[str, int, int]] = []
    for i, (baslik, bas) in enumerate(adaylar):
        son = adaylar[i + 1][1] if i + 1 < len(adaylar) else len(metin)
        if son - bas >= esik:
            out.append((baslik, bas, son))
    return out


def bolum_sec(
    bolumler_listesi: list[tuple[str, int, int]], istek: str
) -> tuple[str, int, int] | None:
    """Kullanicinin verdigi ifadeye en iyi uyan bolum.

    Once "item 7" gibi kod eslesmesi, sonra baslik icinde alt dize aramasi.
    Birden fazla eslesirse EN UZUN bolum secilir: ayni kod hem ozet hem asil
    bolumde gecebilir, asil olan uzun olandir.
    """
    q = " ".join(istek.split()).lower().rstrip(".")
    kod = re.match(r"^item\s+(\d{1,2}[a-c]?)$", q)

    if kod:
        hedef = f"item {kod.group(1)}"
        eslesen = [
            b for b in bolumler_listesi
            if re.match(rf"^item\s+{re.escape(kod.group(1))}\b", b[0].lower())
        ]
    else:
        hedef = q
        eslesen = [b for b in bolumler_listesi if hedef in b[0].lower()]

    if not eslesen:
        return None
    return max(eslesen, key=lambda b: b[2] - b[1])
