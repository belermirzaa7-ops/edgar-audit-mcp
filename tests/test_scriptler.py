"""dene.py ve dogrula.py sahte veriyle uctan uca calisiyor mu.

Bu scriptler test kapsami disindaydi ve bir alan adi degisikliginde
(resolved_concept -> resolved_concepts) calisma aninda AttributeError
veriyordu. Testler yesilken script cokuyordu.
"""
from __future__ import annotations

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
