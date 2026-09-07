"""ZIP upload expansion — extract members safely for further processing."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.file_service import expand_zip_bytes, _safe_member_parts


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_safe_member_parts_rejects_traversal():
    assert _safe_member_parts("../etc/passwd") is None
    assert _safe_member_parts("__MACOSX/._foo.cfg") is None
    assert _safe_member_parts("folder/ag_fault.cfg") == ["folder", "ag_fault.cfg"]


def test_expand_zip_prefers_basename_for_cfg_dat_pair():
    data = _make_zip(
        {
            "EVT-TEST-001/EVT-TEST-001.cfg": b"cfg-content",
            "EVT-TEST-001/EVT-TEST-001.dat": b"dat-content",
            "EVT-TEST-001/notes.pdf": b"%PDF-1.4",
            "EVT-TEST-001/readme.md": b"ignore me",
        }
    )
    members, skipped = expand_zip_bytes(data)
    names = {n for n, _ in members}
    assert names == {"EVT-TEST-001.cfg", "EVT-TEST-001.dat", "notes.pdf"}
    assert any("readme.md" in s for s in skipped)


def test_expand_nested_zip():
    inner = _make_zip({"inner.cfg": b"inner", "inner.dat": b"bytes"})
    outer = _make_zip({"package.zip": inner, "outer.txt": b"soe"})
    members, _ = expand_zip_bytes(outer)
    names = {n for n, _ in members}
    assert "inner.cfg" in names
    assert "inner.dat" in names
    assert "outer.txt" in names


def test_expand_empty_allowed():
    data = _make_zip({"only.md": b"x"})
    members, skipped = expand_zip_bytes(data)
    assert members == []
    assert skipped


def test_expand_bad_zip():
    with pytest.raises(HTTPException) as ei:
        expand_zip_bytes(b"not-a-zip")
    assert ei.value.status_code == 400


def test_real_evt_test_001_zip_ingests():
    zip_path = Path(
        r"c:\Users\5863.AVAADA\Downloads\Protection_RCA_COMTRADE_Test_Pack"
        r"\protection_rca_test_samples\EVT-TEST-001.zip"
    )
    if not zip_path.is_file():
        pytest.skip("EVT-TEST-001.zip not present on this machine")
    members, skipped = expand_zip_bytes(zip_path.read_bytes())
    names = {n for n, _ in members}
    assert "EVT-TEST-001.cfg" in names
    assert "EVT-TEST-001.dat" in names
    assert "relay_settings.json" in names
    assert "soe.csv" in names

    # COMTRADE ingest on extracted members
    import tempfile

    from comtrade.service import ComtradeService

    tmp = Path(tempfile.mkdtemp(prefix="evt001_"))
    paths = []
    for name, data in members:
        if Path(name).suffix.lower() in {".cfg", ".dat", ".cff", ".hdr", ".inf"}:
            p = tmp / name
            p.write_bytes(data)
            paths.append(p)
    result = ComtradeService().ingest(paths, validate_after_parse=True)
    assert result.success, result.error or result.to_dict()
    assert result.record is not None
    assert (result.record.samples or 0) > 0
