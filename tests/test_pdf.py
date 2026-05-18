"""PDF reading tool."""
from __future__ import annotations

import pytest

from ai_agent.tools.base import ToolContext
from ai_agent.tools.pdf import ReadPdf, _parse_page_range


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(workspace=tmp_path, settings=None, logger=_DummyLogger())


@pytest.fixture
def sample_pdf(tmp_path):
    """A 3-page PDF with known text. Created in-process via PyMuPDF."""
    import fitz
    p = tmp_path / "sample.pdf"
    doc = fitz.open()
    for i, text in enumerate(["Hello from page one.", "Second page content.", "Third and final."], start=1):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(p))
    doc.close()
    return p


def test_parse_page_range_full():
    assert _parse_page_range(None, 10) == (1, 10)


def test_parse_page_range_single():
    assert _parse_page_range("3", 10) == (3, 3)


def test_parse_page_range_slice():
    assert _parse_page_range("2-5", 10) == (2, 5)


async def test_read_pdf_whole_doc(ctx, sample_pdf):
    r = await ReadPdf().run({"path": sample_pdf.name}, ctx)
    assert r.success, r.error
    assert "Hello from page one" in r.output
    assert "Second page content" in r.output
    assert "Third and final" in r.output
    assert r.data["total_pages"] == 3
    assert r.data["pages_read"] == 3


async def test_read_pdf_slice(ctx, sample_pdf):
    r = await ReadPdf().run({"path": sample_pdf.name, "pages": "2-3"}, ctx)
    assert r.success
    assert "Hello from page one" not in r.output
    assert "Second page content" in r.output
    assert "Third and final" in r.output
    assert r.data["pages_read"] == 2


async def test_read_pdf_single_page(ctx, sample_pdf):
    r = await ReadPdf().run({"path": sample_pdf.name, "pages": "1"}, ctx)
    assert r.success
    assert "Hello from page one" in r.output
    assert "Second page content" not in r.output


async def test_read_pdf_out_of_range(ctx, sample_pdf):
    r = await ReadPdf().run({"path": sample_pdf.name, "pages": "5-10"}, ctx)
    assert not r.success
    assert "out of bounds" in (r.error or "").lower()


async def test_read_pdf_missing_file(ctx):
    r = await ReadPdf().run({"path": "nope.pdf"}, ctx)
    assert not r.success
    assert "not found" in (r.error or "").lower()


async def test_read_pdf_truncates_large_output(ctx, sample_pdf):
    r = await ReadPdf().run({"path": sample_pdf.name, "max_chars": 50}, ctx)
    assert r.success
    assert r.data["truncated"]
    assert "truncated" in r.output
