"""COMTRADE detect / validate / parse endpoints (read-only analysis — no control)."""

from __future__ import annotations

from typing import Annotated

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.security import Role
from app.models import User
from app.dependencies.auth import CurrentUser, require_role
from app.schemas.comtrade import (
    ComtradeDetectResponse,
    ComtradeParseResponse,
    ComtradeValidateResponse,
)

router = APIRouter(prefix="/api/comtrade", tags=["comtrade"])


async def _save_uploads(files: list[UploadFile]) -> list[Path]:
    """Write uploads to a temp dir; ZIP archives are expanded to member files."""
    from app.services.file_service import expand_zip_bytes

    paths: list[Path] = []
    tmpdir = Path(tempfile.mkdtemp(prefix="comtrade_"))
    for f in files:
        name = Path(f.filename or "upload.bin").name
        data = await f.read()
        if name.lower().endswith(".zip"):
            members, _skipped = expand_zip_bytes(data)
            if not members:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP '{name}' contained no allowed files for COMTRADE processing",
                )
            for member_name, member_data in members:
                dest = tmpdir / Path(member_name).name
                # avoid collisions
                if dest.exists():
                    stem, suf = dest.stem, dest.suffix
                    n = 1
                    while dest.exists():
                        dest = tmpdir / f"{stem}_{n}{suf}"
                        n += 1
                dest.write_bytes(member_data)
                paths.append(dest)
        else:
            dest = tmpdir / name
            dest.write_bytes(data)
            paths.append(dest)
    return paths


@router.post("/detect", response_model=ComtradeDetectResponse)
async def detect_comtrade(
    user: User = Depends(require_role(Role.ANALYST)),
    files: list[UploadFile] = File(...),
) -> ComtradeDetectResponse:
    from comtrade.service import ComtradeService

    paths = await _save_uploads(files)
    try:
        svc = ComtradeService()
        result = svc.detect(paths)
        d = result.to_dict() if hasattr(result, "to_dict") else {}
        revision = getattr(result, "revision", d.get("revision"))
        revision_year = None
        if isinstance(revision, str) and revision.isdigit():
            revision_year = int(revision)
        elif isinstance(revision, int):
            revision_year = revision
        return ComtradeDetectResponse(
            is_comtrade=bool(getattr(result, "is_comtrade", d.get("is_comtrade", False))),
            status=str(getattr(result, "status", d.get("status", "UNKNOWN"))),
            revision_year=revision_year,
            data_format=getattr(result, "data_format", d.get("data_format")),
            container=getattr(result, "container", d.get("container")),
            encoding=getattr(result, "encoding", d.get("encoding")),
            details=d or None,
            warnings=list(getattr(result, "notes", d.get("notes") or [])),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/validate", response_model=ComtradeValidateResponse)
async def validate_comtrade(
    user: User = Depends(require_role(Role.ANALYST)),
    files: list[UploadFile] = File(...),
) -> ComtradeValidateResponse:
    from comtrade.service import ComtradeService

    paths = await _save_uploads(files)
    try:
        svc = ComtradeService()
        ingest = svc.ingest(paths, validate_after_parse=True)
        if ingest.validation is None:
            return ComtradeValidateResponse(
                status="NOT_VALIDATED",
                warnings=[ingest.error or "validation unavailable"],
                details=ingest.to_dict(),
            )
        v = ingest.validation
        vd = v.to_dict() if hasattr(v, "to_dict") else {}
        return ComtradeValidateResponse(
            status=str(getattr(v, "status", vd.get("status", "UNKNOWN"))),
            data_quality=getattr(v, "data_quality", vd.get("data_quality")),
            issues=list(getattr(v, "issues", vd.get("issues") or [])),
            warnings=list(getattr(v, "warnings", vd.get("warnings") or [])),
            details=vd or None,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/parse", response_model=ComtradeParseResponse)
async def parse_comtrade(
    user: User = Depends(require_role(Role.ANALYST)),
    files: list[UploadFile] = File(...),
) -> ComtradeParseResponse:
    from comtrade.service import ComtradeService

    paths = await _save_uploads(files)
    try:
        svc = ComtradeService()
        ingest = svc.ingest(paths, validate_after_parse=True)
        record = ingest.record
        detection = ingest.detection.to_dict() if ingest.detection else None
        validation = ingest.validation.to_dict() if ingest.validation else None
        analog = None
        digital = None
        rate = None
        if record is not None:
            analog = len(getattr(record, "analog_channels", []) or [])
            digital = len(getattr(record, "digital_channels", []) or [])
            rate = getattr(record, "sample_rate_hz", None)
        return ComtradeParseResponse(
            success=ingest.success,
            record_id=record.record_id if record else None,
            station=getattr(record, "station", None) if record else None,
            device=getattr(record, "device", None) if record else None,
            samples=getattr(record, "samples", None) if record else None,
            analog_channels=analog,
            digital_channels=digital,
            sample_rate_hz=rate,
            detection=detection,
            validation=validation,
            error=ingest.error,
            stages=ingest.stages,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
