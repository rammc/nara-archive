"""Tests for the PDF assembly logic."""

from __future__ import annotations

from pathlib import Path

import pypdf
from PIL import Image

from nara.pdfbuild import assemble_pdf, classify_source


def _make_jpg(path: Path, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (200, 280), color=color)
    img.save(path, format="JPEG", quality=80)


def _make_pdf(path: Path, label: str) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    with path.open("wb") as fh:
        writer.write(fh)
    assert path.stat().st_size > 0
    _ = label  # marker for readability


def test_assemble_pdf_from_three_jpgs(tmp_path):
    pages = []
    colors = [(200, 50, 50), (50, 200, 50), (50, 50, 200)]
    for i, color in enumerate(colors, start=1):
        p = tmp_path / f"page-{i:03d}.jpg"
        _make_jpg(p, color)
        pages.append(p)

    out = tmp_path / "out.pdf"
    page_count = assemble_pdf(pages, out, work_dir=tmp_path / "work")

    assert out.exists()
    assert out.stat().st_size > 0
    assert page_count == 3

    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) == 3


def test_assemble_pdf_from_mixed_sources(tmp_path):
    img = tmp_path / "page-1.jpg"
    _make_jpg(img, (180, 180, 180))

    native = tmp_path / "report.pdf"
    _make_pdf(native, "report")

    out = tmp_path / "mixed.pdf"
    pages = [img, native]
    page_count = assemble_pdf(pages, out, work_dir=tmp_path / "work")

    assert out.exists()
    assert page_count == 2
    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) == 2


def test_classify_source_uses_magic_bytes_when_extension_misleads(tmp_path):
    # File named .pdf but actually a JPEG.
    fake = tmp_path / "tricky.pdf"
    _make_jpg(fake, (0, 0, 0))
    assert classify_source(fake) == "image"

    # Real PDF still classified as pdf even with weird name.
    pdfish = tmp_path / "weird.bin"
    _make_pdf(pdfish, "x")
    assert classify_source(pdfish) == "pdf"


def test_classify_source_skips_audio(tmp_path):
    audio = tmp_path / "clip.mp3"
    # ID3 tag header — common MP3 prefix.
    audio.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 32)
    assert classify_source(audio) == "skip"
