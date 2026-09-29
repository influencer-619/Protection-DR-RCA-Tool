"""Map IEC 61850-7-4 logical-node settings to Protection RCA setting blocks.

Vendors use the standard LN classes (PTOC, PDIS, PDIF …) with their own
prefixes (ABB ``PHLPTOC1``, Siemens ``I_PTOC1`` …), so mapping is done on the
LN class plus prefix hints. Every value read from the IED is also kept
verbatim under ``iec61850_raw``; nothing is invented.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.services.iec61850.client import split_ln_name

# IEC 61850-7-3 CurveCharKind (setCharact of CURVE / TmACrv)
CURVE_KIND = {
    1: "ANSI Extremely Inverse",
    2: "ANSI Very Inverse",
    3: "ANSI Normal Inverse",
    4: "ANSI Moderately Inverse",
    5: "ANSI Definite Time",
    6: "ANSI Long-Time Extremely Inverse",
    7: "ANSI Long-Time Very Inverse",
    8: "ANSI Long-Time Inverse",
    9: "IEC Normal Inverse",
    10: "IEC Very Inverse",
    11: "IEC Inverse",
    12: "IEC Extremely Inverse",
    13: "IEC Short-Time Inverse",
    14: "IEC Long-Time Inverse",
    15: "IEC Definite Time",
}

# DO name → canonical parameter
_PARAMS = {
    "StrVal": "pickup",
    "TmMult": "time_dial",
    "TmACrv": "curve",
    "OpDlTmms": "delay_ms",
    "RsDlTmms": "reset_delay_ms",
    "DirMod": "direction",
    "PoRch": "reach_ohm",
    "X1": "reach_x_ohm",
    "R1": "reach_r_ohm",
    "LinAng": "line_angle_deg",
    "RisPhRch": "resistive_reach_ph_ohm",
    "RisGndRch": "resistive_reach_gnd_ohm",
    "K0Fact": "k0",
    "K0FactAng": "k0_angle_deg",
    "PhDlTmms": "phase_delay_ms",
    "GndDlTmms": "ground_delay_ms",
    "LoSet": "pickup",
    "HiSet": "high_set",
    "MinOpTmms": "min_operate_ms",
    "FailTmms": "bf_timer_ms",
    "DetValA": "pickup",
    "Rec1Tmms": "dead_time_1_ms",
    "Rec2Tmms": "dead_time_2_ms",
    "Rec3Tmms": "dead_time_3_ms",
    "RclTmms": "reclaim_ms",
    "MaxCyc": "shots",
    "ARtg": "rated_primary",
    "ARtgSec": "rated_secondary",
    "VRtg": "rated_primary",
    "VRtgSec": "rated_secondary",
    "Rat": "ratio",
}

_CLASS_ELEMENT = {
    "PDIS": "21",
    "PDIF": "87",
    "PLDF": "87L",
    "PTOV": "59",
    "PTUV": "27",
    "PTOF": "81O",
    "PTUF": "81U",
    "PFRC": "81R",
    "RBRF": "50BF",
    "RREC": "79",
    "RSYN": "25",
    "RPSB": "68",
    "PPAM": "78",
    "PTTR": "49",
    "PDUP": "32",
    "PDOP": "32",
    "PVPH": "24",
    "PHIZ": "50N",
    "PTEF": "67N",
    "PDEF": "67N",
    "PDOC": "67",
}


def element_for(ln: str, dos: set[str]) -> Optional[str]:
    prefix, cls, _inst = split_ln_name(ln)
    p = prefix.upper()
    earth = bool(re.search(r"EF|GF|NEU|GND|^N|^E|N$", p))
    neg_seq = bool(re.search(r"NS|NPS|NEG", p))
    if cls == "PTOC":
        if neg_seq:
            return "46"
        base = "51" if ({"TmACrv", "TmMult"} & dos) else "50"
        if "DirMod" in dos or p.startswith("D"):
            base = "67"
        return base + ("N" if earth else "")
    if cls in ("PDOC", "PDEF"):
        return "67N" if earth or cls == "PDEF" else "67"
    return _CLASS_ELEMENT.get(cls)


def _do_value(values: dict[str, Any], do: str) -> Any:
    """Pick the meaningful attribute of a setting DO (ASG / ING / ENG / CURVE)."""
    for suffix in (".setMag.f", ".setMag.i", ".setVal", ".setCharact", ".setMag"):
        if f"{do}{suffix}" in values:
            return values[f"{do}{suffix}"]
    for k, v in values.items():
        if k.split(".")[0] == do:
            return v
    return None


def build_settings_document(
    *,
    ied_label: str,
    host: str,
    port: int,
    nameplate: dict[str, Optional[str]],
    ln_settings: dict[str, dict[str, Any]],
    behaviour: dict[str, Any],
    active_group: Optional[int],
    read_errors: list[str],
) -> dict[str, Any]:
    """``ln_settings`` is ``{"LD/LN": {"StrVal.setMag.f": 1.2, …}}`` (SP + SG merged)."""
    protection: dict[str, dict[str, Any]] = {}
    ct_vt: dict[str, Any] = {}
    raw: dict[str, Any] = {}

    for ref, values in sorted(ln_settings.items()):
        for k, v in values.items():
            raw[f"{ref}.{k}"] = v
        ln = ref.split("/", 1)[-1]
        _prefix, cls, inst = split_ln_name(ln)
        dos = {k.split(".")[0] for k in values}

        if cls in ("TCTR", "TVTR"):
            prim = _do_value(values, "ARtg" if cls == "TCTR" else "VRtg")
            sec = _do_value(values, "ARtgSec" if cls == "TCTR" else "VRtgSec")
            key = "ct_ratio" if cls == "TCTR" else "vt_ratio"
            if prim and sec and key not in ct_vt:
                ct_vt[key] = f"{prim:g}/{sec:g}" if isinstance(prim, (int, float)) and isinstance(sec, (int, float)) else f"{prim}/{sec}"
            continue

        element = element_for(ln, dos)
        if not element:
            continue

        params: dict[str, Any] = {"ln": ref}
        for do in dos:
            canon = _PARAMS.get(do)
            if not canon:
                continue
            val = _do_value(values, do)
            if val is None:
                continue
            if canon == "curve" and isinstance(val, int):
                val = CURVE_KIND.get(val, f"Curve kind {val}")
            if canon == "pickup" and element in ("50", "51", "50N", "51N", "67", "67N", "46", "50BF"):
                canon = "pickup_current"
            params[canon] = val
        beh = behaviour.get(ref)
        if isinstance(beh, int):
            params["enabled"] = beh in (1, 2, 3)

        if element == "21":
            block = protection.setdefault("21", {"zones": {}})
            zone = f"zone{inst or len(block['zones']) + 1}"
            block["zones"][zone] = params
            for k in ("reach_ohm", "delay_ms", "reach_x_ohm"):
                if k in params:
                    block.setdefault(f"{zone}_{k.replace('_ohm', '')}", params[k])
            if zone == "zone1" and "reach_ohm" in params:
                block["zone1_reach"] = params["reach_ohm"]
            if "enabled" in params:
                block["enabled"] = block.get("enabled", False) or params["enabled"]
            continue

        if element == "50BF" and "bf_timer_ms" in params:
            params["bf_timer_s"] = round(float(params["bf_timer_ms"]) / 1000.0, 4)
        if element == "79" and "dead_time_1_ms" in params:
            params["dead_time_s"] = round(float(params["dead_time_1_ms"]) / 1000.0, 4)

        key = element if element not in protection else f"{element}_{ln}"
        protection[key] = params

    return {
        "source": "IEC61850",
        "acquired_via": f"MMS GetDataValues from {host}:{port}",
        "ied": ied_label,
        "relay_model": " ".join(x for x in (nameplate.get("vendor"), nameplate.get("model")) if x) or None,
        "nameplate": nameplate,
        "active_setting_group": active_group,
        "protection": protection,
        "ct_vt": ct_vt,
        "iec61850_raw": raw,
        "read_errors": read_errors[:50],
    }
