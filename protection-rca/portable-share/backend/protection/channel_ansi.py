"""Vendor-neutral digital / fault channel name → ANSI / IEEE C37.2 device number.

COMTRADE ``ch_id`` fields are free-form (IEEE C37.111 / C37.248). Vendors
encode the same protection function differently:

* **IEC 61850 LN** (all modern IEDs): ``PIOC``, ``PTOC``, ``PDIF``, ``PDIS``, …
* **SEL** Relay Word bits: ``50P1``, ``51G1``, ``67P1``, ``21P1``, ``50Q1``, …
* **Siemens SIPROTEC**: ``I>``, ``IN>``, ``I2>``, ``I-DIFF``, ``50/51 Pickup``, …
* **ABB Relion**: LN prefixes ``PHPIOC``, ``PHLPTOC``, ``EFPIOC``, ``T2WPDIF``, …
* **GE / Multilin**: ``Phase IOC``, ``Ground TOC``, ``Neutral IOC``, …
* **Schneider / MiCOM**: ``I>1``, ``IN1>1``, ``ISEF>``, ``Thermal Trip``, …

Rules are ordered most-specific first. Generic trip/start contacts that do not
identify a function return ``None``.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Ordered rules: first match wins
# ---------------------------------------------------------------------------
_CHANNEL_ANSI_RULES: list[tuple[re.Pattern[str], str]] = [
    # --- IEC 61850 logical-node class tokens (vendor-agnostic) -------------
    (re.compile(
        r"\bRBRF\d*\b|50BF|50NBF|CBF|BKR.?FAIL|BRK.?FAIL|BREAKER.?FAIL|"
        r"\bBFAIL\d*|\bLBB\b|BF\s*TRIP",
        re.I,
    ), "50BF"),
    (re.compile(r"\bREFPDIF\d*\b|87RGF|RESTRICTED.?EARTH|\bIREF\b|I-?REF|(?<![A-Z])REF(?![A-Z])", re.I), "87RGF"),
    (re.compile(r"\bGENPDIF\d*\b|87GT|\b87G\b|GEN(?:ERATOR)?.?DIFF", re.I), "87G"),
    (re.compile(
        r"\b(?:T2W|T3W)?PDIF\d*\b|\b87T\b|XFMR.?DIFF|TRANSFORMER.?DIFF|"
        r"BIAS(?:ED)?.?DIFF|I-?DIFF|DIFF\s*>+|DIFF\s*PICK",
        re.I,
    ), "87T"),
    # Line differential (ABB REL561 "DIFF TRIP" / "B DIFF TRIP")
    (re.compile(r"\bPLDF\d*\b|\b87L\b|LINE.?DIFF|\b[RYB]\s*DIFF\s*TRIP\b|\bDIFF\s*TRIP\b", re.I), "87L"),
    (re.compile(r"\b87B\b|BUS.?DIFF|BUSBAR.?DIFF", re.I), "87B"),
    (re.compile(r"\bPDIF\d*\b|\b87\b|(?<![A-Z])DIFF(?:ERENTIAL)?(?![A-Z])", re.I), "87T"),
    (re.compile(r"\b21G\d*\b|ZONE.?EARTH|GROUND.?DIST|Z\d+\s*G", re.I), "21G"),
    (re.compile(r"\b21P\d*\b|PHASE.?DIST", re.I), "21P"),
    (re.compile(
        r"\bPDIS\d*\b|\b21\b|ZONE\s*[1-5]|Z[1-5]\b|"
        r"DIST(?:ANCE)?\s*(START|TRIP|PICK|PU)|"
        r"DST\s*ST|DSTST",  # station DFR distance start
        re.I,
    ), "21"),
    (re.compile(
        r"\bPTTR\d*\b|THERMAL|THOVERLOAD|TH\s*OVERLOAD|TH\s*TRIP|TH\s*ALARM|\b49\b",
        re.I,
    ), "49"),
    (re.compile(
        r"STALL|LOCKED?\s*ROTOR|PROLONGED\s*START|LONG\s*START|"
        r"NUMBER\s*OF\s*STARTS|INCOMPLETE.?SEQ|\b48\b",
        re.I,
    ), "48"),
    (re.compile(
        r"\b50Q\d*\b|\b51Q\d*\b|\b46\b|"
        r"I2\s*>|I2>|NPS|NEG(?:ATIVE)?.?SEQ|PHASE.?UNBAL|BROKEN.?COND|"
        r"\bNSPTOC\d*\b|\bNS2PTOC\d*\b",
        re.I,
    ), "46"),
    # Directional (before plain OC)
    (re.compile(
        r"\b67N\d*\b|\b67G\d*\b|\bPDEF\d*\b|\bPTEF\d*\b|\bPSDE\d*\b|"
        r"DIR(?:ECTIONAL)?.?EARTH|EARTH.?DIR|SENSITIVE.?DIR.?E(?:ARTH)?F|"
        r"\bIE\s*>+\s*DIR|\bIEP\s*DIR|\bIE>>",  # Siemens earth dir OC
        re.I,
    ), "67N"),
    (re.compile(r"\b67P\d*\b|\bPDOC\d*\b|DIR(?:ECTIONAL)?.?PHASE", re.I), "67P"),
    (re.compile(
        r"\b67\d*\b|DIR(?:ECTIONAL)?\s*(START|TRIP|OC|PU)|DIR\s*O/?C|DIR.?O/?C",
        re.I,
    ), "67"),
    # Earth / neutral OC — SEL 50N/51G/51N; Siemens IN>; MiCOM IN1>; ABB EF*
    (re.compile(
        r"\b51N\d*\b|\b51G\d*\b|IDMT.?EARTH|"
        r"\bIN\d*\s*>\s*[23456]|\bIN\d*>[23456]|"
        r"GROUND.?TOC|NEUTRAL.?TOC|EARTH.?TOC|"
        r"\bEFLPTOC\d*\b|\bEF4PTOC\d*\b",
        re.I,
    ), "51N"),
    (re.compile(
        r"\b50N\d*\b|\b50G\d*\b|"
        r"\bPHIZ\d*\b|"
        r"ISEF|SEF|SENSITIVE.?E(?:ARTH)?F|"
        r"\bIEN\s*>|"
        r"\bIN\d*\s*>\s*1|\bIN\d*>1|"
        r"\bI0\s*>|"
        r"\bIN\s*>|"
        r"\bEFPIOC\d*\b|"
        r"GROUND.?IOC|NEUTRAL.?IOC|EARTH.?IOC|"
        r"EARTH.?FAULT|E/F|EF\s*(START|TRIP|PICK|PU)|"
        r"GND\s*(START|TRIP|PICK|OC)",
        re.I,
    ), "50N"),
    # Explicit phase 50P / 51P (SEL 50P1 / 51P1T …)
    (re.compile(r"\b50P\d*", re.I), "50P"),
    (re.compile(r"\b51P\d*", re.I), "51P"),
    # Swing / block BEFORE generic OC — "PSB BLOCK" / "68 BLOCK" contain "OC"
    (re.compile(r"\bRPSB\d*\b|\b68\b|POWER.?SWING|PSB|OUT.?OF.?STEP.?BLOCK", re.I), "68"),
    (re.compile(r"\bPPAM\d*\b|\b78\b|OUT.?OF.?STEP|OOS\b", re.I), "78"),
    # Combined / backup OC labels before bare 50
    (re.compile(r"50\s*/\s*51|5X-?B\s*PICKUP", re.I), "51"),
    # Instantaneous / time phase OC — IEC PIOC/PTOC, SEL 50/51, Siemens I>, GE IOC/TOC
    (re.compile(
        r"\bPIOC\d*\b|\bPHPIOC\d*\b|"
        r"\bI\s*>\s*1\b|\bI>1\b|"
        r"INST(?:ANTANEOUS)?.?OC|SOTF|"
        r"PHASE.?IOC|(?<![A-Z])IOC(?![A-Z])",
        re.I,
    ), "50"),
    (re.compile(
        r"\bPTOC\d*\b|\bPHLPTOC\d*\b|\bOC4PTOC\d*\b|"
        r"\bI\s*>\s*[234]\b|\bI>[234]\b|"
        r"IDMT.?OC|VCO|VOLTAGE.?CONTROLLED.?OC|"
        r"PHASE.?TOC|(?<![A-Z])TOC(?![A-Z])",
        re.I,
    ), "51"),
    # O/?C must not match inside BLOCK / LOCKOUT / …
    (re.compile(
        r"\bI\s*>|\bI>|PHASE.?OC|(?<![A-Z])O/?C(?![A-Z])(?:\s*PH)?|OVERCURRENT|"
        r"(?<![A-Z])OC\s*(START|TRIP|PICK|PU)",
        re.I,
    ), "50"),
    # Voltage / frequency / power
    (re.compile(r"\bPTUV\d*\b|V\s*<|V<|U/?V\b|UNDER.?VOLT|\b27\b", re.I), "27"),
    (re.compile(r"\bPTOV\d*\b|V\s*>|V>|VN\s*>|V0\s*>|NVD|OVER.?VOLT|\b59\b", re.I), "59"),
    (re.compile(r"\bPTUF\d*\b|F\s*<|F<|UNDER.?FREQ|81U", re.I), "81U"),
    (re.compile(r"\bPTOF\d*\b|F\s*>|F>|OVER.?FREQ|81O", re.I), "81O"),
    (re.compile(r"\bPFRC\d*\b|DF/DT|81R|ROCOF", re.I), "81R"),
    (re.compile(r"\bPDOP\d*\b|\bPDUP\d*\b|32R|REVERSE.?POWER|P<\s*REV|UNDER.?POWER|OVER.?POWER", re.I), "32R"),
    (re.compile(r"\b32\b|POWER.?TRIP", re.I), "32R"),
    # Reclose — initiate/operate only (INHIBIT AR is not ANSI 79 pickup)
    (re.compile(
        r"\bRREC\d*\b|AUTO.?RECLOSE|RECLOSE|INITIATE_?AR|"
        r"\b79\s*(?:AR|RECLOSE|RREC)\b|\bAR\s*(?:INIT|CLOSE|ON|OFF|SUCCESS)",
        re.I,
    ), "79"),
    (re.compile(r"\b86\b|LOCKOUT|LOCK.?OUT", re.I), "86"),
    (re.compile(r"\bRSYN\d*\b|\b25\b|CHECK.?SYNC|SYNCH?(?:RONISM)?|SYNC.?CHECK", re.I), "25"),
]

# Whole-name skips (generic contacts — no inventable ANSI)
_SKIP = re.compile(
    r"^ANY\s*START$|^TRIP$|^FAULT\s*TRIP|^TRIP\s*TO\s*TC|"
    r"^TRIP\s*CMD$|^GENERAL\s*TRIP$|^GEN\s*TRIP$|^PTRC\d*$|"
    r"^RELAY\s*\d+$|^UNUSED|^BINARY|^DIGITAL|"
    r"^BIN_?\d+$|^DOUT_?\d+$|"
    r"^D\d+$|"  # opaque DFR spare slots D16…D96
    r"DIFF\s*COM\s*FAIL|COM\s*FAIL",
    re.I,
)

# Bay / station labels that look like they contain "50" but are not ANSI 50
# e.g. "50BT STn Unit Trip" (bay 50 Bus-Tie station unit trip)
_GENERAL_CONTACT = re.compile(
    r"STN\s*UNIT\s*TRI|"  # STn Unit Trip / truncated …Ti
    r"\bUNIT\s*TRIP\b|"
    r"GENERAL\s*(?:TRIP|START|PICKUP)|"
    r"ANY\s*START|"
    r"FAULT\s*TRIP\s*TO\s*TC|"
    r"TRIP\s*TO\s*TC|"
    r"\bPTRC\d*\b",
    re.I,
)

_BARE_ANSI = (
    "87RGF",
    "50BF",
    "50NBF",
    "87GT",
    "87G",
    "87T",
    "87L",
    "87B",
    "51N",
    "50N",
    "67N",
    "67P",
    "50P",
    "51P",
    "21G",
    "21P",
    "32R",
    "81U",
    "81O",
    "81R",
    "32",
    "49",
    "48",
    "46",
    "68",
    "78",
    "21",
    "50",
    "51",
    "67",
    "27",
    "59",
    # 79 / 86 / 25 only via explicit patterns above (not bare token — invents AR/lockout)
    "87",
)


def _refine_distance(name: str, code: str) -> str:
    """Prefer 21G / 21P when the channel name carries a ground/phase hint."""
    if code != "21":
        return code
    n = name.upper()
    if re.search(r"21G|GROUND|EARTH|\bGND\b|Z\d+\s*G", n) and not re.search(r"21P|PHASE", n):
        return "21G"
    if re.search(r"21P|PHASE", n) and not re.search(r"21G|GROUND|EARTH", n):
        return "21P"
    return "21"


def _bare_token_match(name: str, code: str) -> bool:
    """Match ANSI token at non-alnum boundaries (not glued bay ids like 50BT)."""
    return bool(
        re.search(rf"(?:^|[^A-Z0-9]){re.escape(code)}(?:[^A-Z0-9]|$)", name, re.I)
    )


def match_ansi_from_channel(name: str) -> Optional[str]:
    """Return ANSI device number for a protection digital/analog channel name."""
    raw = (name or "").strip()
    if not raw or _SKIP.search(raw) or _GENERAL_CONTACT.search(raw):
        return None
    n = raw.upper()
    # Pure block / inrush restraint — not overcurrent (avoid O/?C inside BLOCK)
    if re.search(r"\bBLOCK\b|\bBLK\b|INRUSH|2ND\s*H|NTH\s*H|\bCWA\b", n) and not re.search(
        r"\bI\s*>|\b50\b|\b51\b|OVERCURRENT|(?<![A-Z])O/?C(?![A-Z])",
        n,
    ):
        if re.search(r"PSB|POWER.?SWING|RPSB|\b68\b", n):
            return "68"
        return None
    for pat, code in _CHANNEL_ANSI_RULES:
        if pat.search(n):
            return _refine_distance(n, code)
    for code in _BARE_ANSI:
        if _bare_token_match(n, code):
            if code == "87":
                return "87T"
            if code == "87GT":
                return "87G"
            return code
    return None
