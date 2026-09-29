"""Vendor profiles for IEC 61850 MMS file-store retrieval.

Every conformant IEC 61850 server exposes disturbance records through the
standard MMS file services (ISO 9506 FileDirectory / FileOpen / FileRead), so
the generic strategy (walk the file store from ``/``) works for any vendor.
Profiles only add the directories each family is known to use, so records are
still found on IEDs that do not list sub-directories at the root.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


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


_COMMON_DR = ("/COMTRADE/", "COMTRADE/")

PROFILES: tuple[VendorProfile, ...] = (
    VendorProfile(
        id="AUTO",
        label="Auto-detect (read nameplate)",
        families="Any IEC 61850 Ed1 / Ed2 / Ed2.1 server with MMS file services",
        dr_dirs=_COMMON_DR,
    ),
    VendorProfile(
        id="ABB",
        label="ABB / Hitachi Energy",
        families="Relion 605/611/615/620/630/640, 650/670 series (REL/RED/RET/REB/REC/REF/REM)",
        dr_dirs=("/COMTRADE/", "COMTRADE/", "/DR/"),
        event_dirs=("/EVENTS/",),
        nameplate_markers=("abb", "hitachi", "relion"),
        notes="Enable 'MMS file transfer' in PCM600 (Communication → IEC 61850).",
    ),
    VendorProfile(
        id="SIEMENS",
        label="Siemens",
        families="SIPROTEC 5 (7SA/7SD/7SL/7UT/7SJ/7VK/6MD), SIPROTEC 4 with EN100, Reyrolle 7SR5",
        dr_dirs=("/COMTRADE/", "COMTRADE/", "/FAULTREC/", "/REC/"),
        event_dirs=("/LOG/",),
        nameplate_markers=("siemens", "siprotec", "reyrolle"),
        notes="SIPROTEC 5 stores records per function group under /COMTRADE/<LD>/.",
    ),
    VendorProfile(
        id="GE",
        label="GE Vernova (Multilin)",
        families="UR / UR+ (D60, L90, T60, F60, B30, C60 …), 8 Series (850/869/889), MiCOM Alstom legacy",
        dr_dirs=("/COMTRADE/", "COMTRADE/", "/OSCILLOGRAPHY/", "/"),
        event_dirs=("/EVENTS/", "/FAULTREPORT/"),
        nameplate_markers=("ge ", "general electric", "multilin", "grid solutions", "vernova"),
        notes="UR series names records OSC*.CFG / OSC*.DAT at the file-store root.",
    ),
    VendorProfile(
        id="SCHNEIDER",
        label="Schneider Electric",
        families="MiCOM Px40 / Agile, Easergy P3/P5, Sepam series 80/40 (ACE850)",
        dr_dirs=("/COMTRADE/", "COMTRADE/", "/DR/", "/DISTURBANCE/"),
        event_dirs=("/EVENTS/", "/FAULT/"),
        nameplate_markers=("schneider", "micom", "easergy", "sepam", "areva", "alstom"),
    ),
    VendorProfile(
        id="SEL",
        label="Schweitzer (SEL)",
        families="SEL-4xx (411L/421/487), SEL-7xx (751/787/751A), SEL-2440, RTAC",
        dr_dirs=("/COMTRADE/", "COMTRADE/", "/EVENTS/"),
        event_dirs=("/EVENTS/", "/REPORTS/"),
        settings_dirs=("/SETTINGS/",),
        nameplate_markers=("sel", "schweitzer"),
        notes="SEL exposes COMTRADE, EVENTS and SETTINGS (SET_*.TXT) over MMS file services.",
    ),
    VendorProfile(
        id="NR",
        label="NR Electric",
        families="PCS-9xx series (PCS-931/902/978/915)",
        dr_dirs=("/COMTRADE/", "COMTRADE/", "/RECORD/", "/WAVE/"),
        event_dirs=("/EVENT/",),
        nameplate_markers=("nr electric", "nari", "pcs-"),
    ),
    VendorProfile(
        id="TOSHIBA",
        label="Toshiba",
        families="GR series (GRL100/GRZ100/GRT100/GRD200)",
        dr_dirs=_COMMON_DR,
        nameplate_markers=("toshiba",),
    ),
    VendorProfile(
        id="ZIV",
        label="ZIV / Hitachi Energy Spain",
        families="ZLV / DLX / IDV series",
        dr_dirs=_COMMON_DR + ("/OSCILO/",),
        nameplate_markers=("ziv",),
    ),
    VendorProfile(
        id="OTHER",
        label="Other vendor (generic)",
        families="Ingeteam, Arteche, Efacec, Sifang, XJ, Woodward, Beckwith, Eaton, Hyosung …",
        dr_dirs=_COMMON_DR + ("/DR/", "/RECORDS/"),
        event_dirs=("/EVENTS/", "/LOG/"),
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


def search_dirs(profile: VendorProfile) -> list[str]:
    """Directory search order: vendor-specific first, then the whole store."""
    seen: list[str] = []
    for d in (
        *profile.dr_dirs,
        *profile.event_dirs,
        *profile.settings_dirs,
        *_COMMON_DR,
        "/",
    ):
        if d not in seen:
            seen.append(d)
    return seen
