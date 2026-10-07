"""Extract plain text from PDF / Word for settings and event-report ingest.

Deterministic, no GenAI, no OCR. Text-based PDFs and ``.docx`` work.
Scanned (image-only) PDFs and legacy binary ``.doc`` without extractable
text return ``NOT_CALCULABLE`` with an actionable reason.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any, Optional

DOCUMENT_EXTS = frozenset({".pdf", ".docx", ".doc"})


def is_document_bytes(data: bytes, filename: str = "") -> bool:
    ext = Path(filename or "").suffix.lower()
    if ext in DOCUMENT_EXTS:
        return True
    if len(data) >= 5 and data[:5] == b"%PDF-":
        return True
    if len(data) >= 4 and data[:2] == b"PK" and ext in {".docx", ".doc", ""}:
        return True
    if len(data) >= 8 and data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return True
    return False


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse extreme runs of spaces while keeping line structure
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def _normalize_settings_lines(text: str) -> str:
    """Turn common PDF/Word table rows into KEY=VALUE for settings_ingest."""
    out: list[str] = []
    for line in text.splitlines():
        out.append(line)
        if "=" in line or (":" in line and not re.match(r"^\d{1,2}:\d{2}", line)):
            continue
        # Label …… 123.4 A / Enabled / IEC S Inverse
        m = re.match(
            r"^([A-Za-z][A-Za-z0-9 /<>\-_().%]{2,60}?)\s{2,}([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*([A-Za-z%/°]*)\s*$",
            line,
        )
        if m:
            key = re.sub(r"\s+", "_", m.group(1).strip())
            out.append(f"{key}={m.group(2)}")
            continue
        m2 = re.match(
            r"^([A-Za-z][A-Za-z0-9 /<>\-_().%]{2,60}?)\s{2,}(Enabled|Disabled|On|Off|Yes|No|DT|IDMT|IEC\s+\S.+|ANSI\s+\S.+)\s*$",
            line,
            re.I,
        )
        if m2:
            key = re.sub(r"\s+", "_", m2.group(1).strip())
            out.append(f"{key}={m2.group(2).strip()}")
    return "\n".join(out)


def extract_pdf_text(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"%PDF"):
        return {
            "status": "NOT_CALCULABLE",
            "reason": "Not a PDF file",
            "text": "",
            "page_count": 0,
            "format": "pdf",
        }
    try:
        from pypdf import PdfReader
    except ImportError:
        return {
            "status": "NOT_CALCULABLE",
            "reason": "pypdf package NOT AVAILABLE — install pypdf to read PDF settings",
            "text": "",
            "page_count": 0,
            "format": "pdf",
        }
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "NOT_CALCULABLE",
            "reason": f"Unable to open PDF: {exc}",
            "text": "",
            "page_count": 0,
            "format": "pdf",
        }
    parts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            t = ""
        if t.strip():
            parts.append(t)
    text = _clean_text("\n".join(parts))
    if len(text) < 40:
        return {
            "status": "NOT_CALCULABLE",
            "reason": (
                "PDF has little or no extractable text (likely scanned/image-only). "
                "Export text PDF, or paste settings as TXT/CSV/JSON / MiCOM .set"
            ),
            "text": text,
            "page_count": len(reader.pages),
            "format": "pdf",
        }
    return {
        "status": "OK",
        "reason": None,
        "text": text,
        "page_count": len(reader.pages),
        "format": "pdf",
        "char_count": len(text),
    }


def extract_docx_text(data: bytes) -> dict[str, Any]:
    if not (len(data) >= 4 and data[:2] == b"PK"):
        return {
            "status": "NOT_CALCULABLE",
            "reason": "Not a ZIP-based Word .docx file",
            "text": "",
            "format": "docx",
        }
    try:
        from docx import Document
    except ImportError:
        return {
            "status": "NOT_CALCULABLE",
            "reason": "python-docx package NOT AVAILABLE — install python-docx to read Word settings",
            "text": "",
            "format": "docx",
        }
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "NOT_CALCULABLE",
            "reason": f"Unable to open Word .docx: {exc}",
            "text": "",
            "format": "docx",
        }
    parts: list[str] = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)
    for table in doc.tables:
        for row in table.rows:
            cells = [(c.text or "").strip() for c in row.cells]
            cells = [c for c in cells if c]
            if not cells:
                continue
            if len(cells) >= 2:
                # Prefer KEY=VALUE shape for settings tables
                parts.append(f"{cells[0]}={cells[1]}")
                parts.append("  ".join(cells))
            else:
                parts.append(cells[0])
    text = _clean_text("\n".join(parts))
    if len(text) < 20:
        return {
            "status": "NOT_CALCULABLE",
            "reason": "Word document has little or no extractable text",
            "text": text,
            "format": "docx",
        }
    return {
        "status": "OK",
        "reason": None,
        "text": text,
        "format": "docx",
        "char_count": len(text),
    }


def _extract_ole_doc_text(data: bytes) -> dict[str, Any]:
    """Best-effort printable extract from legacy Word ``.doc`` (OLE)."""
    try:
        import olefile
    except ImportError:
        return {
            "status": "NOT_CALCULABLE",
            "reason": (
                "Legacy Word .doc needs olefile, or re-save as .docx / export TXT. "
                "olefile package NOT AVAILABLE"
            ),
            "text": "",
            "format": "doc",
        }
    if not olefile.isOleFile(io.BytesIO(data)):
        return {
            "status": "NOT_CALCULABLE",
            "reason": "Not a valid OLE Word .doc — re-save as .docx or export TXT/CSV",
            "text": "",
            "format": "doc",
        }
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "NOT_CALCULABLE",
            "reason": f"Unable to open Word .doc OLE: {exc}",
            "text": "",
            "format": "doc",
        }
    chunks: list[bytes] = []
    try:
        for entry in ole.listdir(streams=True, storages=False):
            name = "/".join(entry).lower()
            if "worddocument" in name or "1table" in name or name.endswith("document"):
                try:
                    chunks.append(ole.openstream(entry).read())
                except Exception:  # noqa: BLE001
                    continue
    finally:
        try:
            ole.close()
        except Exception:  # noqa: BLE001
            pass
    if not chunks:
        return {
            "status": "NOT_CALCULABLE",
            "reason": "Legacy Word .doc has no readable WordDocument stream — re-save as .docx",
            "text": "",
            "format": "doc",
        }
    raw = b"\n".join(chunks)
    # UTF-16LE runs (common in Word binary)
    utf16_parts: list[str] = []
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", raw):
        try:
            utf16_parts.append(m.group().decode("utf-16le", errors="ignore"))
        except Exception:  # noqa: BLE001
            continue
    ascii_parts = re.findall(rb"[\x20-\x7e]{6,}", raw)
    ascii_text = "\n".join(p.decode("ascii", errors="ignore") for p in ascii_parts)
    text = _clean_text("\n".join(utf16_parts) + "\n" + ascii_text)
    # Drop obvious Word binary noise tokens
    text = "\n".join(
        ln
        for ln in text.splitlines()
        if not re.fullmatch(r"[A-Za-z]{1,3}", ln)
        and "Microsoft Word" not in ln
    )
    if len(text) < 40:
        return {
            "status": "NOT_CALCULABLE",
            "reason": (
                "Legacy Word .doc text extract too weak — re-save as .docx or export "
                "settings as TXT/CSV/JSON"
            ),
            "text": text,
            "format": "doc",
        }
    return {
        "status": "OK",
        "reason": "Legacy .doc best-effort extract — prefer .docx for reliable mapping",
        "text": text,
        "format": "doc",
        "char_count": len(text),
    }


def extract_document_text(data: bytes, *, filename: str = "") -> dict[str, Any]:
    """Extract plain text from PDF / Word bytes."""
    name = Path(filename or "").name
    ext = Path(name).suffix.lower()
    head = data[:8] if data else b""

    if ext == ".pdf" or data.startswith(b"%PDF"):
        result = extract_pdf_text(data)
    elif ext == ".docx" or (
        head[:2] == b"PK"
        and ext in {".docx", ".doc", ""}
        and _zip_has_word_xml(data)
    ):
        result = extract_docx_text(data)
    elif ext == ".doc" or head == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        # Misnamed docx?
        if head[:2] == b"PK" and _zip_has_word_xml(data):
            result = extract_docx_text(data)
        else:
            result = _extract_ole_doc_text(data)
    else:
        return {
            "status": "NOT_CALCULABLE",
            "reason": f"Unsupported document type for text extract: {ext or 'unknown'}",
            "text": "",
            "format": ext.lstrip(".") or "unknown",
        }

    if result.get("status") == "OK" and result.get("text"):
        result = dict(result)
        result["text"] = _normalize_settings_lines(result["text"])
        result["filename"] = name
    return result


def _zip_has_word_xml(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = {n.lower() for n in zf.namelist()}
        return "word/document.xml" in names
    except Exception:  # noqa: BLE001
        return False


def document_text_for_ingest(
    data: bytes, *, filename: str = "", purpose: str = "settings"
) -> tuple[Optional[str], Optional[str]]:
    """Return ``(text, error_reason)`` suitable for re-entering text ingest."""
    extracted = extract_document_text(data, filename=filename)
    if extracted.get("status") != "OK" or not extracted.get("text"):
        return None, extracted.get("reason") or f"Unable to extract text from {purpose} document"
    return extracted["text"], None
