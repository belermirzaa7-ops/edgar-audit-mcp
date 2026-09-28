"""`mcp dev` icin giris noktasi: `uv run mcp dev inspector.py`.

Neden ayri bir dosya (28 Eyl 2026, olculdu): `mcp dev`, verilen dosyayi paket
disinda `server_module` adiyla yukluyor. `src/edgar_mcp/server.py` goreli
import kullaniyor (`from .belge import ...`), yani o dosyayi dogrudan vermek
`ImportError: attempted relative import with no known parent package` ile
basarisiz oluyordu - ve iki README ile CLAUDE.md tam da o komutu yaziyordu.
Bu dosya kurulu paketi mutlak import ile aliyor; SDK `mcp` adli nesneyi
kendisi buluyor.

`_c()` BURADA da cagriliyor. Inspector sunucuyu `mcp run inspector.py` ile
baslatiyor ve bu `main()`'i hic cagirmiyor - yani bu dosya UCUNCU bir giris
noktasi ve "SEC_USER_AGENT olmadan baslamaz" korumasi onunla tasinmazsa
P-40'in aynisi olur (bagimsiz denetimde bulundu, 28 Eyl 2026: `initialize` ve
`tools/list` basariliydi, hata ancak ilk arac cagrisinda geliyordu).
"""
from edgar_mcp.server import _c, mcp

_c()

__all__ = ["mcp"]
