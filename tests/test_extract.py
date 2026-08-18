"""Extraction and ledger tests. The fixture PDF is generated in-test with pypdf
so nothing here touches the network or ships a binary in the repo."""

import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meester.extract import draft_ledger, sniff_kind, to_text
from meester.profile import load_ledger, save_ledger, validate_ledger

CV_TEXT = """Jane Q. Example
jane@example.com | +1 555 010 1234 | linkedin.com/in/janeexample

Summary
Product designer with nine years across fintech and developer tools.

Experience
Acme Corp - Senior Product Designer
Jan 2021 - Present
- Led the redesign of the onboarding flow, lifting activation 23%
- Built and ran the design system used by 40 engineers

Beta Industries - Product Designer
2018 - 2020
- Shipped the mobile app from zero to 100k installs

Education
State University - BFA Design 2014 - 2018

Skills
Figma, user research, prototyping, design systems
"""


def make_pdf(text: str) -> bytes:
    """A real one-page PDF carrying the text, via pypdf's writer."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    # pypdf cannot lay out rich text, but annotation-free content streams can
    # be injected; simpler and just as valid for extraction: use free text via
    # the annotation API is overkill - instead write each line as a text object.
    from pypdf.generic import DictionaryObject, NameObject, StreamObject

    lines = text.splitlines()
    ops = ["BT", "/F1 11 Tf", "1 0 0 1 40 750 Tm", "13 TL"]
    for line in lines:
        safe = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        ops.append(f"({safe}) Tj T*")
    ops.append("ET")
    stream = StreamObject()
    stream.set_data("\n".join(ops).encode("latin-1", errors="replace"))
    stream_ref = writer._add_object(stream)
    page[NameObject("/Contents")] = stream_ref
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = writer._add_object(font)
    resources = DictionaryObject()
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_docx(text: str) -> bytes:
    buf = io.BytesIO()
    paragraphs = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text.splitlines()
    )
    doc = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}</w:body></w:document>"
    )
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def test_sniff_trusts_bytes_not_names():
    assert sniff_kind(make_pdf("x")) == "pdf"
    assert sniff_kind(make_docx("x")) == "docx"
    assert sniff_kind(b"MZ\x90\x00 an exe pretending") == ""
    assert sniff_kind(b"%PDF-1.7 real header") == "pdf"
    # A zip that is not a docx (no word/document.xml) is refused.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("innocent.txt", "hi")
    assert sniff_kind(buf.getvalue()) == ""


def test_pdf_round_trip_extracts_the_text():
    kind, text = to_text(make_pdf(CV_TEXT))
    assert kind == "pdf"
    assert "Acme Corp" in text
    assert "jane@example.com" in text


def test_docx_round_trip_extracts_the_text():
    kind, text = to_text(make_docx(CV_TEXT))
    assert kind == "docx"
    assert "Beta Industries" in text


def test_draft_ledger_finds_the_load_bearing_facts():
    ledger = draft_ledger(CV_TEXT)
    assert ledger["email"] == "jane@example.com"
    assert ledger["name"].startswith("Jane")
    employers = " ".join(e["employer"] + " " + e["title"] for e in ledger["employment"])
    assert "Acme" in employers
    assert "Beta" in employers
    assert len(ledger["employment"]) == 2
    first = ledger["employment"][0]
    assert first["end"].lower() == "present"
    assert any("onboarding" in b for b in first["bullets"])
    assert any("Figma" in s for s in ledger["skills"])
    assert ledger["verified"] is False, "a draft must never claim to be verified"


def test_ledger_validation_drops_empty_entries_and_caps_sizes():
    clean = validate_ledger(
        {"employment": [{"employer": "", "title": "", "bullets": ["x"]},
                        {"employer": "Real Co", "bullets": ["b" * 5000]}],
         "skills": ["ok", ""] * 100}
    )
    assert len(clean["employment"]) == 1
    assert len(clean["employment"][0]["bullets"][0]) == 300
    assert len(clean["skills"]) <= 60


def test_save_stamps_verified_and_round_trips(tmp_path):
    path = tmp_path / "facts_ledger.json"
    saved = save_ledger(path, draft_ledger(CV_TEXT))
    assert saved["verified"] is True, "the only path to a saved ledger is her review"
    assert saved["saved_at"]
    back = load_ledger(path)
    assert back["verified"] is True
    assert back["employment"][0]["employer"] == saved["employment"][0]["employer"]


VERTICAL_CV = """WORK EXPERIENCE
Compliance Specialist
Sep2024-April 2025
RELI Group
•
Monitor providers in the MCP model
• Provide CMS updates on the model
Data Analyst
June 2023-Sep2024
RELI Group
• Extract and analyze CMS claims data
• Build Python models for trend analysis
"""


def test_vertical_layout_with_no_space_dates():
    """The real-resume shape that broke the parser: title / date / employer on
    separate lines, dates written 'Sep2024' with no space, bullets where the
    glyph sits on its own line."""
    entries = draft_ledger(VERTICAL_CV)["employment"]
    assert len(entries) == 2, [e["title"] for e in entries]
    first, second = entries
    assert first["title"] == "Compliance Specialist"
    assert first["employer"] == "RELI Group"
    assert first["start"] == "Sep2024" and "April 2025" in first["end"]
    assert any("Monitor providers" in b for b in first["bullets"])
    assert second["title"] == "Data Analyst"
    assert any("Python models" in b for b in second["bullets"])


def test_ligatures_are_folded_not_accents():
    from meester.extract import _normalize

    assert _normalize("Snowﬂake ﬁndings") == "Snowflake findings"
    assert _normalize("café résumé") == "café résumé"


def test_corrupt_ledger_reads_as_absent(tmp_path):
    path = tmp_path / "facts_ledger.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_ledger(path) is None
