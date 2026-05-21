"""Path-traversal protection and Range support for the /pdfs/* mount."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from actari.config import Config
from actari.server import create_app

PDF_PROLOGUE = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
PDF_BODY = b"X" * 4096 + b"%%EOF\n"


def _config(tmp_path: Path) -> Config:
    return Config(
        api_key="fake-key",
        api_base_url="https://example.test/api/v2/",
        default_rate=0.5,
        output_dir=tmp_path,
        server_host="127.0.0.1",
        server_port=8765,
        auto_open_browser=False,
        config_path=None,
        terms_acknowledged=True,
        acknowledged_at="2026-05-16T00:00:00Z",
    )


@pytest.fixture
def client_with_pdf(tmp_path):
    out = tmp_path / "out"
    pdfs = out / "pdfs"
    pdfs.mkdir(parents=True)
    pdf_bytes = PDF_PROLOGUE + PDF_BODY
    (pdfs / "0001-x_doc.pdf").write_bytes(pdf_bytes)
    # Sensitive file sitting alongside output dir — a traversal attempt
    # should never reach it.
    (tmp_path / "secret.txt").write_text("DO NOT LEAK", encoding="utf-8")

    app = create_app(_config(out))
    return TestClient(app), pdf_bytes


def test_pdf_served_with_correct_content_type(client_with_pdf):
    c, pdf_bytes = client_with_pdf
    r = c.get("/pdfs/0001-x_doc.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] in (
        "application/pdf",
        "application/pdf; charset=utf-8",
    )
    assert r.content == pdf_bytes


def test_pdf_supports_range_requests(client_with_pdf):
    c, pdf_bytes = client_with_pdf
    r = c.get("/pdfs/0001-x_doc.pdf", headers={"Range": "bytes=0-15"})
    assert r.status_code == 206
    assert r.headers["content-range"].startswith("bytes 0-15/")
    assert r.content == pdf_bytes[:16]


def test_pdf_404_for_missing(client_with_pdf):
    c, _ = client_with_pdf
    r = c.get("/pdfs/nope.pdf")
    assert r.status_code == 404


def test_path_traversal_blocked(client_with_pdf):
    c, _ = client_with_pdf
    # The URL %2F decodes to '/', so this becomes /pdfs/../secret.txt
    # — Starlette's StaticFiles resolves and rejects it.
    r = c.get("/pdfs/..%2Fsecret.txt")
    assert r.status_code in (403, 404)
    # And via explicit segment that decodes server-side.
    r = c.get("/pdfs/../secret.txt")
    assert r.status_code in (403, 404)
