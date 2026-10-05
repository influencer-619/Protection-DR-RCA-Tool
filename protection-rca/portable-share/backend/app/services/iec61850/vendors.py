"""Vendor profiles for IEC 61850 MMS file-store retrieval.

Market tools (ABB 800xA, GeoSCADA, Elipse, WinCC OA, Digsi/PCM600) do **not**
download directory maps from the internet. They:

1. Walk the IED MMS file store from ``/`` (and known COMTRADE folders), or
2. Let the engineer set a **remote COMTRADE directory** from the relay tool /
   vendor manual (e.g. PCM600 → Communication → IEC 61850 → file path).

Profiles only seed directories each family commonly uses so records are found
even when the IED does not list sub-directories at the root.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence


@dataclass(frozen=True)
class VendorProfile:
    id: str
    label: str
    families: str
    dr_dirs: tuple[str, ...] = ()
    event_dirs: tuple[str, ...] = ()
    settings_dirs: tuple[str, ...] = ()
    nameplate_markers: tuple[str, ...] = ()
    notes: str = ""
    extra: dict = field(default_factory=dict)


# Paths widely cited by SCADA IEC 61850 drivers and vendor manuals.
_COMMON_DR = (
    "/COMTRADE/",
    "COMTRADE/",
    "/Comtrade/",
    "/comtrade/",
    "\\COMTRADE\\",
)

PROFILES: tuple[VendorProfile, ...] = (
    VendorProfile(
        id="AUTO",
        label="Auto-detect (read nameplate)",
        families="Any IEC 61850 Ed1 / Ed2 / Ed2.1 server with MMS file services",
        dr_dirs=_COMMON_DR,
        notes=(
            "Same approach as GeoSCADA / WinCC OA: list the file store, prefer /COMTRADE/. "
            "If empty, set Remote COMTRADE path from the relay configuration tool."
        ),
    ),
    VendorProfile(
        id="ABB",
        label="ABB / Hitachi Energy",
        families="Relion 605/611/615/620/630/640, 650/670 series (REL/RED/RET/REB/REC/REF/REM)",
        dr_dirs=_COMMON_DR + ("/DR/", "/DR/COMTRADE/", "/WAV/", "/WAVE/"),
        event_dirs=("/EVENTS/", "/EVENT/"),
        nameplate_markers=("abb", "hitachi", "relion"),
        notes=(
            "PCM600: enable MMS file transfer (Communication → IEC 61850). "
            "800xA uses ‘Disturbance Recorder Remote Directory’ — paste that path here if Browse is empty."
        ),
    ),
    VendorProfile(
        id="SIEMENS",
        label="Siemens",
        families="SIPROTEC 5 (7SA/7SD/7SL/7UT/7SJ/7VK/6MD), SIPROTEC 4 with EN100, Reyrolle 7SR5",
        dr_dirs=_COMMON_DR + ("/FAULTREC/", "/REC/", "/DR/", "/COMTRADE/LD0/", "/COMTRADE/CTRL/"),
        event_dirs=("/LOG/", "/EVENTS/"),
        nameplate_markers=("siemens", "siprotec", "reyrolle"),
        notes="SIPROTEC 5 often stores records under /COMTRADE/<LD>/. Digsi: enable file services on the EN100/ETH-BD.",
    ),
    VendorProfile(
        id="GE",
        label="GE Vernova (Multilin)",
        families="UR / UR+ (D60, L90, T60, F60, B30, C60 …), 8 Series (850/869/889), MiCOM Alstom legacy",
        dr_dirs=_COMMON_DR + ("/OSCILLOGRAPHY/", "/OSC/", "/"),
        event_dirs=("/EVENTS/", "/FAULTREPORT/"),
        nameplate_markers=("ge ", "general electric", "multilin", "grid solutions", "vernova"),
        notes="UR series often names records OSC*.CFG / OSC*.DAT at the file-store root.",
    ),
    VendorProfile(
        id="SCHNEIDER",
        label="Schneider Electric",
        families="MiCOM Px40 / Agile, Easergy P3/P5, Sepam series 80/40 (ACE850)",
        dr_dirs=_COMMON_DR + ("/DR/", "/DISTURBANCE/", "/FAULT/", "/OSCILLO/"),
        event_dirs=("/EVENTS/", "/FAULT/"),
        nameplate_markers=("schneider", "micom", "easergy", "sepam", "areva", "alstom"),
        notes="GeoSCADA expects COMTRADE under root or under a logical device — Browse walks both.",
    ),
    VendorProfile(
        id="SEL",
        label="Schweitzer (SEL)",
        families="SEL-4xx (411L/421/487), SEL-7xx (751/787/751A), SEL-2440, RTAC",
        dr_dirs=_COMMON_DR + ("/EVENTS/", "/EVENT/", "/REPORTS/"),
        event_dirs=("/EVENTS/", "/REPORTS/"),
        settings_dirs=("/SETTINGS/", "/SET/"),
        nameplate_markers=("sel", "schweitzer"),
        notes="SEL exposes COMTRADE, EVENTS and SETTINGS (SET_*.TXT) over MMS when file transfer is enabled.",
    ),
    VendorProfile(
        id="NR",
        label="NR Electric",
        families="PCS-9xx series (PCS-931/902/978/915)",
        dr_dirs=_COMMON_DR + ("/RECORD/", "/WAVE/", "/DR/", "/FAULT/"),
        event_dirs=("/EVENT/", "/EVENTS/"),
        nameplate_markers=("nr electric", "nari", "pcs-"),
    ),
    VendorProfile(
        id="TOSHIBA",
        label="Toshiba",
        families="GR series (GRL100/GRZ100/GRT100/GRD200)",
        dr_dirs=_COMMON_DR + ("/DR/", "/OSC/"),
        nameplate_markers=("toshiba",),
    ),
    VendorProfile(
        id="ZIV",
        label="ZIV / Hitachi Energy Spain",
        families="ZLV / DLX / IDV series",
        dr_dirs=_COMMON_DR + ("/OSCILO/", "/OSC/", "/DR/"),
        nameplate_markers=("ziv",),
    ),
    VendorProfile(
        id="OTHER",
        label="Other vendor (generic)",
        families="Ingeteam, Arteche, Efacec, Sifang, XJ, Woodward, Beckwith, Eaton, Hyosung …",
        dr_dirs=_COMMON_DR + ("/DR/", "/RECORDS/", "/RECORD/", "/WAVE/", "/OSC/"),
        event_dirs=("/EVENTS/", "/LOG/", "/EVENT/"),
        notes="Set Remote COMTRADE path from the IED configuration tool if Browse finds nothing.",
    ),
)

_BY_ID = {p.id: p for p in PROFILES}


def get_profile(profile_id: Optional[str]) -> VendorProfile:
    return _BY_ID.get((profile_id or "AUTO").upper(), _BY_ID["AUTO"])


def detect_profile(nameplate: dict[str, Optional[str]]) -> VendorProfile:
    """Pick a profile from LPHD.PhyNam / LLN0.NamPlt vendor + model strings."""
    blob = " ".join(str(v or "") for v in nameplate.values()).lower()
    if not blob.strip():
        return _BY_ID["OTHER"]
    for prof in PROFILES:
        for marker in prof.nameplate_markers:
            if marker.strip() == "sel":
                if re.search(r"(^|[^a-z])sel([^a-z]|$)", blob):
                    return prof
            elif marker in blob:
                return prof
    return _BY_ID["OTHER"]


def _norm_dir(d: str) -> str:
    s = (d or "").strip().replace("\\", "/")
    if not s:
        return ""
    if not s.startswith("/") and not s.lower().startswith("comtrade"):
        s = "/" + s
    if not s.endswith("/"):
        s += "/"
    return s


def search_dirs(profile: VendorProfile, *, extra: Sequence[str] = ()) -> list[str]:
    """Directory search order: engineer override → vendor hints → whole store.

    Matches SCADA practice: optional fixed COMTRADE path, then walk ``/``.
    """
    seen: list[str] = []
    for d in (
        *(_norm_dir(x) for x in extra if x),
        *profile.dr_dirs,
        *profile.event_dirs,
        *profile.settings_dirs,
        *_COMMON_DR,
        "/",
    ):
        n = _norm_dir(d) if d != "/" else "/"
        # Keep both "/" and relative COMTRADE/ forms when vendors use either.
        candidates = [n]
        if n not in ("/", "") and n.startswith("/"):
            candidates.append(n.lstrip("/"))
        for c in candidates:
            if c and c not in seen:
                seen.append(c)
    return seen
