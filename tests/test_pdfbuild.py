"""Tests for the PDF assembly logic."""

from __future__ import annotations

from pathlib import Path

import pypdf
from PIL import Image

from nara.pdfbuild import (
    RECOMPRESS_MAX_DIM,
    RECOMPRESS_QUALITY,
    _recompress_to_jpeg,
    assemble_pdf,
    classify_source,
)


def _make_jpg(path: Path, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (200, 280), color=color)
    img.save(path, format="JPEG", quality=80)


def _make_large_jpg(path: Path, size: tuple[int, int] = (4000, 5200)) -> None:
    """A big high-res JPEG that exceeds the recompression threshold."""
    img = Image.new("RGB", size, color=(255, 240, 220))
    img.save(path, format="JPEG", quality=95, subsampling=0)


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


# --- recompression (roadmap #1) ---


def test_recompress_to_jpeg_shrinks_oversized_image(tmp_path):
    """A 4000x5200 JPEG is downscaled to <=2400px and re-encoded smaller."""
    src = tmp_path / "huge.jpg"
    _make_large_jpg(src)
    before = src.stat().st_size
    out = _recompress_to_jpeg(src, tmp_path / "work")
    after = out.stat().st_size
    with Image.open(out) as img:
        assert max(img.size) <= RECOMPRESS_MAX_DIM
    assert after < before, f"recompress should shrink the file (was {before}, now {after})"


def test_recompress_uses_default_quality(tmp_path):
    """Sanity: the produced JPEG is decodable and within quality bounds."""
    src = tmp_path / "in.jpg"
    _make_large_jpg(src)
    out = _recompress_to_jpeg(src, tmp_path / "work")
    with Image.open(out) as img:
        img.verify()
    # Quality constant exposed so power users can tune.
    assert 50 <= RECOMPRESS_QUALITY <= 95


def test_assemble_pdf_with_recompress_produces_smaller_output(tmp_path):
    """End-to-end: PDF built with recompress=True is meaningfully smaller."""
    pages = []
    for i in range(2):
        p = tmp_path / f"page-{i}.jpg"
        _make_large_jpg(p)
        pages.append(p)

    plain = tmp_path / "plain.pdf"
    assemble_pdf(pages, plain, work_dir=tmp_path / "w1", recompress=False)
    compressed = tmp_path / "compressed.pdf"
    assemble_pdf(pages, compressed, work_dir=tmp_path / "w2", recompress=True)

    assert compressed.stat().st_size < plain.stat().st_size
    # Page count must be unchanged.
    assert len(pypdf.PdfReader(str(plain)).pages) == len(pypdf.PdfReader(str(compressed)).pages)
