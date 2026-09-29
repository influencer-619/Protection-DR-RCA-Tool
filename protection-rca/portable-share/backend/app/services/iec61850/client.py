"""Read-only IEC 61850 MMS client (libiec61850 via pyiec61850-ng).

Only ACSI read services are used: GetServerDirectory, GetLogicalDeviceDirectory,
GetDataValues, GetDataDefinition, GetFileDirectory and GetFile. Nothing is
written to the IED, no controls are issued and no files are deleted.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Optional

try:  # optional native dependency
    import pyiec61850.pyiec61850 as _iec

    _IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # noqa: BLE001
    _iec = None
    _IMPORT_ERROR = str(exc)


class Iec61850Unavailable(RuntimeError):
    """pyiec61850-ng / libiec61850 is not installed on the server."""


class Iec61850Error(RuntimeError):
    """Connection or service error reported by the IED."""


def library_status() -> dict[str, Any]:
    if _iec is None:
        return {"available": False, "reason": _IMPORT_ERROR or "pyiec61850 not installed"}
    return {"available": True, "reason": None}


def _require() -> Any:
    if _iec is None:
        raise Iec61850Unavailable(
            "IEC 61850 client library is not installed on the server "
            "(pip install pyiec61850-ng). " + (_IMPORT_ERROR or "")
        )
    return _iec


# Relays accept only a few MMS associations; serialise sessions per IED.
_HOST_LOCKS: dict[tuple[str, int], threading.Lock] = {}
_HOST_LOCKS_GUARD = threading.Lock()


def _host_lock(host: str, port: int) -> threading.Lock:
    with _HOST_LOCKS_GUARD:
        return _HOST_LOCKS.setdefault((host, port), threading.Lock())


def split_ln_name(ln: str) -> tuple[str, str, str]:
    """``PHLPTOC1`` → (``PHL``, ``PTOC``, ``1``); ``LLN0`` → ("", "LLN0", "")."""
    if ln.upper() == "LLN0":
        return "", "LLN0", ""
    m = re.match(r"^(.*)([A-Z]{4})(\d*)$", ln)
    if not m:
        return "", ln, ""
    return m.group(1), m.group(2), m.group(3)


@dataclass
class FileEntry:
    name: str  # exactly as reported by the IED (used for GetFile)
    size: int
    last_modified_ms: int

    @property
    def path(self) -> str:
        p = self.name.replace("\\", "/")
        while p.startswith("./"):
            p = p[2:]
        return p if p.startswith("/") else "/" + p

    @property
    def is_dir(self) -> bool:
        return self.name.endswith("/")

    @property
    def basename(self) -> str:
        return PurePosixPath(self.path.rstrip("/")).name

    @property
    def last_modified_iso(self) -> Optional[str]:
        if not self.last_modified_ms:
            return None
        try:
            return datetime.fromtimestamp(self.last_modified_ms / 1000.0, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None


class MmsSession:
    """One MMS association to an IED. Use as a context manager."""

    def __init__(
        self,
        host: str,
        port: int = 102,
        *,
        connect_timeout_s: float = 10.0,
        request_timeout_s: float = 20.0,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.connect_timeout_ms = int(connect_timeout_s * 1000)
        self.request_timeout_ms = int(request_timeout_s * 1000)
        self._con = None
        self._lock = _host_lock(host, self.port)
        self._locked = False

    # --- lifecycle ---

    def __enter__(self) -> "MmsSession":
        self.open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def open(self) -> None:
        iec = _require()
        if not self._lock.acquire(timeout=self.connect_timeout_ms / 1000.0 + 30):
            raise Iec61850Error(f"Another session to {self.host}:{self.port} is still running")
        self._locked = True
        con = iec.IedConnection_create()
        iec.IedConnection_setConnectTimeout(con, self.connect_timeout_ms)
        iec.IedConnection_setRequestTimeout(con, self.request_timeout_ms)
        result = iec.IedConnection_connect(con, self.host, self.port)
        err = result[-1] if isinstance(result, tuple) else result
        if err not in (None, iec.IED_ERROR_OK):
            iec.IedConnection_destroy(con)
            self._release_lock()
            raise Iec61850Error(
                f"Cannot connect to {self.host}:{self.port} — {self._err_text(err)}"
            )
        self._con = con

    def close(self) -> None:
        if self._con is not None and _iec is not None:
            try:
                _iec.IedConnection_close(self._con)
            finally:
                _iec.IedConnection_destroy(self._con)
                self._con = None
        self._release_lock()

    def _release_lock(self) -> None:
        if self._locked:
            self._locked = False
            self._lock.release()

    @staticmethod
    def _err_text(err: Any) -> str:
        try:
            return str(_iec.IedClientError_toString(err))
        except Exception:  # noqa: BLE001
            return f"error {err}"

    def _check(self, result: Any, what: str) -> Any:
        if isinstance(result, tuple):
            value, err = result[0], result[-1]
        else:
            value, err = result, _iec.IED_ERROR_OK
        if err != _iec.IED_ERROR_OK:
            raise Iec61850Error(f"{what}: {self._err_text(err)}")
        return value

    @staticmethod
    def _string_list(lst: Any) -> list[str]:
        out: list[str] = []
        if not lst:
            return out
        el = _iec.LinkedList_getNext(lst)
        while el:
            out.append(str(_iec.toCharP(_iec.LinkedList_getData(el))))
            el = _iec.LinkedList_getNext(el)
        _iec.LinkedList_destroy(lst)
        return out

    # --- data model ---

    def logical_devices(self) -> list[str]:
        return self._string_list(
            self._check(_iec.IedConnection_getLogicalDeviceList(self._con), "GetServerDirectory")
        )

    def ln_fcs(self, ld: str) -> dict[str, set[str]]:
        """``{LN: {FC, …}}`` for one logical device (single MMS GetNameList)."""
        names = self._string_list(
            self._check(
                _iec.IedConnection_getLogicalDeviceVariables(self._con, ld),
                f"GetLogicalDeviceDirectory {ld}",
            )
        )
        out: dict[str, set[str]] = {}
        for n in names:
            parts = n.split("$")
            if len(parts) == 2:
                out.setdefault(parts[0], set()).add(parts[1])
            elif len(parts) == 1:
                out.setdefault(parts[0], set())
        return out

    def read_fc(self, ref: str, fc_name: str) -> dict[str, Any]:
        """Read one LN (or DO) under a functional constraint, flattened to leaf paths."""
        fc = getattr(_iec, f"IEC61850_FC_{fc_name}")
        value = self._check(_iec.IedConnection_readObject(self._con, ref, fc), f"Read {ref} [{fc_name}]")
        try:
            spec = self._check(
                _iec.IedConnection_getVariableSpecification(self._con, ref, fc),
                f"GetDataDefinition {ref} [{fc_name}]",
            )
        except Iec61850Error:
            spec = None
        try:
            out: dict[str, Any] = {}
            _flatten(spec, value, "", out)
            return out
        finally:
            if spec is not None:
                _iec.MmsVariableSpecification_destroy(spec)
            _iec.MmsValue_delete(value)

    def nameplate(self, lds: list[str]) -> dict[str, Optional[str]]:
        """Vendor / model / firmware from LPHD.PhyNam, falling back to LLN0.NamPlt."""
        info: dict[str, Optional[str]] = {
            "vendor": None, "model": None, "swRev": None, "hwRev": None, "serNum": None, "configRev": None,
        }
        for ld in lds:
            for ref in (f"{ld}/LPHD1.PhyNam", f"{ld}/LLN0.NamPlt"):
                try:
                    vals = self.read_fc(ref, "DC")
                except Iec61850Error:
                    continue
                for k, v in vals.items():
                    key = k.split(".")[-1]
                    if key in info and not info[key] and v not in (None, ""):
                        info[key] = str(v)
            if info["vendor"] and info["model"]:
                break
        return info

    # --- file services ---

    def list_dir(self, directory: str) -> list[FileEntry]:
        lst = self._check(
            _iec.IedConnection_getFileDirectory(self._con, directory or "/"),
            f"GetFileDirectory {directory}",
        )
        entries: list[FileEntry] = []
        if not lst:
            return entries
        base = directory.strip("/")
        el = _iec.LinkedList_getNext(lst)
        while el:
            fe = _iec.toFileDirectoryEntry(_iec.LinkedList_getData(el))
            name = str(_iec.FileDirectoryEntry_getFileName(fe))
            bare = name.lstrip("./")
            if base and "/" not in bare.rstrip("/") and not bare.startswith(base):
                name = f"{directory.rstrip('/')}/{bare}"
            entries.append(
                FileEntry(
                    name=name,
                    size=int(_iec.FileDirectoryEntry_getFileSize(fe) or 0),
                    last_modified_ms=int(_iec.FileDirectoryEntry_getLastModified(fe) or 0),
                )
            )
            el = _iec.LinkedList_getNext(el)
        _iec.LinkedList_destroy(lst)
        return entries

    def walk(
        self,
        roots: list[str],
        *,
        max_depth: int = 4,
        max_entries: int = 5000,
        deadline: Optional[float] = None,
    ) -> list[FileEntry]:
        """Collect files under ``roots``; unreadable directories are skipped."""
        files: dict[str, FileEntry] = {}
        visited: set[str] = set()
        stack: list[tuple[str, int]] = [(r, 0) for r in reversed(roots)]
        while stack and len(files) < max_entries:
            if deadline and time.monotonic() > deadline:
                break
            directory, depth = stack.pop()
            key = directory.strip("/").lower()
            if key in visited:
                continue
            visited.add(key)
            try:
                entries = self.list_dir(directory)
            except Iec61850Error:
                continue
            for e in entries:
                looks_dir = e.is_dir or (e.size == 0 and "." not in e.basename)
                if looks_dir:
                    if depth + 1 <= max_depth:
                        stack.append((e.path.rstrip("/") + "/", depth + 1))
                    continue
                files.setdefault(e.path.lower(), e)
        return list(files.values())

    def download(self, remote_name: str, *, max_bytes: int) -> bytes:
        mms = _iec.IedConnection_getMmsConnection(self._con)
        if not mms:
            raise Iec61850Error("MMS connection unavailable")
        fd, tmp = tempfile.mkstemp(prefix="iec61850_", suffix=".bin")
        os.close(fd)
        err = _iec.MmsError_create()
        try:
            ok = _iec.MmsConnection_downloadFile(mms, err, remote_name, tmp)
            code = _iec.MmsError_getValue(err)
            if not ok or code != 0:
                raise Iec61850Error(
                    f"GetFile {remote_name}: {_iec.MmsError_toString(code)}"
                )
            size = os.path.getsize(tmp)
            if size > max_bytes:
                raise Iec61850Error(f"GetFile {remote_name}: {size} bytes exceeds upload limit")
            with open(tmp, "rb") as fh:
                return fh.read()
        finally:
            _iec.MmsErrror_destroy(err)
            try:
                os.remove(tmp)
            except OSError:
                pass


# --- MmsValue conversion ---


def _leaf(value: Any) -> Any:
    t = _iec.MmsValue_getType(value)
    if t == _iec.MMS_FLOAT:
        return round(float(_iec.MmsValue_toDouble(value)), 9)
    if t in (_iec.MMS_INTEGER, _iec.MMS_UNSIGNED):
        return int(_iec.MmsValue_toInt64(value))
    if t == _iec.MMS_BOOLEAN:
        return bool(_iec.MmsValue_getBoolean(value))
    if t in (_iec.MMS_VISIBLE_STRING, _iec.MMS_STRING):
        return str(_iec.MmsValue_toString(value) or "")
    if t == _iec.MMS_UTC_TIME:
        ms = int(_iec.MmsValue_getUtcTimeInMs(value) or 0)
        if ms <= 0:
            return None
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat(timespec="milliseconds")
    if t == _iec.MMS_BIT_STRING:
        return int(_iec.MmsValue_getBitStringAsInteger(value))
    if t == _iec.MMS_OCTET_STRING:
        n = int(_iec.MmsValue_getOctetStringSize(value) or 0)
        return "".join(f"{_iec.MmsValue_getOctetStringOctet(value, i):02x}" for i in range(n))
    if t == _iec.MMS_DATA_ACCESS_ERROR:
        return None
    return str(_iec.MmsValue_getTypeString(value))


def _flatten(spec: Any, value: Any, prefix: str, out: dict[str, Any]) -> None:
    if value is None:
        return
    t = _iec.MmsValue_getType(value)
    if t in (_iec.MMS_STRUCTURE, _iec.MMS_ARRAY):
        n = int(_iec.MmsValue_getArraySize(value))
        for i in range(n):
            child_spec = None
            name = str(i)
            if spec is not None:
                try:
                    if t == _iec.MMS_STRUCTURE:
                        child_spec = _iec.MmsVariableSpecification_getChildSpecificationByIndex(spec, i)
                        name = str(_iec.MmsVariableSpecification_getName(child_spec) or i)
                    else:
                        child_spec = _iec.MmsVariableSpecification_getArrayElementSpecification(spec)
                except Exception:  # noqa: BLE001
                    child_spec = None
            _flatten(child_spec, _iec.MmsValue_getElement(value, i), f"{prefix}.{name}" if prefix else name, out)
        return
    out[prefix or "value"] = _leaf(value)
