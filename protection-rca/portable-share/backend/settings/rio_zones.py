"""Parse RIO / XRIO distance trip zones into R–X geometry (deterministic).

Supports:
  - Classic RIO text: DISTANCE / ZONE / MHOSHAPE / SHAPE+LINE
  - XRIO XML: Parameter / Block style zone reaches
  - Fallback from Protection RCA relay_settings["21"] scalars

Never invents zones when no reach / shape evidence exists.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional


def _f(val: Any) -> Optional[float]:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _line_intersection(
    p1: tuple[float, float],
    ang1_deg: float,
    p2: tuple[float, float],
    ang2_deg: float,
) -> Optional[tuple[float, float]]:
    """Intersection of two infinite lines (point + angle)."""
    a1 = math.radians(ang1_deg)
    a2 = math.radians(ang2_deg)
    d1x, d1y = math.cos(a1), math.sin(a1)
    d2x, d2y = math.cos(a2), math.sin(a2)
    den = d1x * d2y - d1y * d2x
    if abs(den) < 1e-12:
        return None
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    t = (dx * d2y - dy * d2x) / den
    return (p1[0] + t * d1x, p1[1] + t * d1y)


def _polygon_from_lines(lines: list[tuple[float, float, float]]) -> list[dict[str, float]]:
    """Convert RIO LINE borders (R, X, angle) to polygon vertices via consecutive intersections."""
    if len(lines) < 3:
        return []
    verts: list[dict[str, float]] = []
    n = len(lines)
    for i in range(n):
        r1, x1, a1 = lines[i]
        r2, x2, a2 = lines[(i + 1) % n]
        hit = _line_intersection((r1, x1), a1, (r2, x2), a2)
        if hit is None:
            continue
        verts.append({"r": float(hit[0]), "x": float(hit[1])})
    return verts if len(verts) >= 3 else []


def _mho_zone(
    *,
    label: str,
    reach_ohm: float,
    angle_deg: float = 75.0,
    index: Optional[int] = None,
    source: str = "settings",
) -> dict[str, Any]:
    ang = math.radians(angle_deg)
    z_set = reach_ohm * complex(math.cos(ang), math.sin(ang))
    center = z_set / 2.0
    return {
        "label": label,
        "index": index,
        "shape": "mho",
        "reach_ohm": float(reach_ohm),
        "angle_deg": float(angle_deg),
        "center_r": float(center.real),
        "center_x": float(center.imag),
        "radius_ohm": float(abs(center)),
        "polygon": None,
        "source": source,
    }


def parse_rio_text(text: str) -> list[dict[str, Any]]:
    """Parse classic RIO distance zones from text."""
    if not text or "BEGIN DISTANCE" not in text.upper():
        return []
    line_angle = 75.0
    m_la = re.search(r"LINEANGLE\s+([-+0-9.eE]+)", text, re.I)
    if m_la:
        line_angle = _f(m_la.group(1)) or 75.0

    zones: list[dict[str, Any]] = []
    # Split ZONE blocks
    for zm in re.finditer(
        r"BEGIN\s+ZONE\b(.*?)END\s+ZONE",
        text,
        flags=re.I | re.S,
    ):
        body = zm.group(1)
        label_m = re.search(r'LABEL\s+"([^"]+)"', body, re.I)
        label = label_m.group(1) if label_m else "ZONE"
        idx_m = re.search(r"INDEX\s+(\d+)", body, re.I)
        index = int(idx_m.group(1)) if idx_m else None
        active_m = re.search(r"ACTIVE\s+(\w+)", body, re.I)
        if active_m and active_m.group(1).upper() in ("FALSE", "0", "NO"):
            continue

        # MHOSHAPE
        mho = re.search(r"BEGIN\s+MHOSHAPE\b(.*?)END\s+MHOSHAPE", body, re.I | re.S)
        if mho:
            mb = mho.group(1)
            reach = _f(
                (re.search(r"REACH\s+([-+0-9.eE]+)", mb, re.I) or [None, None])[1]
            )
            ang = _f(
                (re.search(r"(?:ANGLE|LINEANGLE)\s+([-+0-9.eE]+)", mb, re.I) or [None, None])[1]
            )
            if reach and reach > 0:
                zones.append(
                    _mho_zone(
                        label=label,
                        reach_ohm=reach,
                        angle_deg=ang if ang is not None else line_angle,
                        index=index,
                        source="rio_mho",
                    )
                )
            continue

        # General SHAPE with LINE borders
        shape = re.search(r"BEGIN\s+SHAPE\b(.*?)END\s+SHAPE", body, re.I | re.S)
        if shape:
            lines: list[tuple[float, float, float]] = []
            for lm in re.finditer(
                r"LINE\s+([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)",
                shape.group(1),
                re.I,
            ):
                r, x, a = _f(lm.group(1)), _f(lm.group(2)), _f(lm.group(3))
                if r is None or x is None or a is None:
                    continue
                lines.append((r, x, a))
            poly = _polygon_from_lines(lines)
            if poly:
                zones.append(
                    {
                        "label": label,
                        "index": index,
                        "shape": "polygon",
                        "reach_ohm": None,
                        "angle_deg": line_angle,
                        "center_r": None,
                        "center_x": None,
                        "radius_ohm": None,
                        "polygon": poly,
                        "source": "rio_shape",
                    }
                )
    return zones


def parse_xrio_xml(text: str) -> list[dict[str, Any]]:
    """Extract zone reaches / polygons from XRIO-like XML when present."""
    if not text or "<" not in text[:200]:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    # Collect flat params for fallback mho construction
    flat: dict[str, Any] = {}

    def walk(node: ET.Element, path: str = "") -> None:
        tag = (node.tag or "").split("}")[-1]
        attrs = {k.lower(): v for k, v in node.attrib.items()}
        name = attrs.get("name") or attrs.get("id") or attrs.get("pathname")
        val = attrs.get("value")
        if name and val is not None:
            flat[str(name)] = val
            flat[str(name).lower().replace(" ", "_")] = val
        for ch in node:
            ctag = (ch.tag or "").split("}")[-1].lower()
            if ctag in ("name", "id") and (ch.text or "").strip():
                # sibling value pattern handled below
                pass
            walk(ch, f"{path}/{tag}")

    walk(root)

    # Explicit polygon points: Point R= X= under Zone
    zones: list[dict[str, Any]] = []
    for zone_el in root.iter():
        ztag = (zone_el.tag or "").split("}")[-1].lower()
        if ztag not in ("zone", "distancezone"):
            continue
        zattrs = {k.lower(): v for k, v in zone_el.attrib.items()}
        label = zattrs.get("label") or zattrs.get("name") or "ZONE"
        index = None
        try:
            if zattrs.get("index") is not None:
                index = int(zattrs["index"])
        except ValueError:
            index = None
        pts: list[dict[str, float]] = []
        reach = None
        angle = None
        for ch in zone_el.iter():
            ctag = (ch.tag or "").split("}")[-1].lower()
            ca = {k.lower(): v for k, v in ch.attrib.items()}
            if ctag in ("point", "vertex") and ("r" in ca or "x" in ca):
                r, x = _f(ca.get("r")), _f(ca.get("x"))
                if r is not None and x is not None:
                    pts.append({"r": r, "x": x})
            if ctag in ("parameter", "param", "setting"):
                n = (ca.get("name") or "").lower()
                v = _f(ca.get("value"))
                if n in ("reach", "zreach", "z", "reach_ohm") and v:
                    reach = v
                if n in ("angle", "lineangle", "phi") and v is not None:
                    angle = v
                # child Name/Value
                cn = cv = None
                for sub in ch:
                    st = (sub.tag or "").split("}")[-1].lower()
                    if st in ("name", "id") and (sub.text or "").strip():
                        cn = sub.text.strip().lower()
                    if st in ("value", "val") and sub.text is not None:
                        cv = _f(sub.text.strip())
                if cn and cv is not None:
                    if cn in ("reach", "zreach", "reach_ohm"):
                        reach = cv
                    if cn in ("angle", "lineangle"):
                        angle = cv
        if len(pts) >= 3:
            zones.append(
                {
                    "label": label,
                    "index": index,
                    "shape": "polygon",
                    "reach_ohm": None,
                    "angle_deg": angle,
                    "center_r": None,
                    "center_x": None,
                    "radius_ohm": None,
                    "polygon": pts,
                    "source": "xrio_polygon",
                }
            )
        elif reach and reach > 0:
            zones.append(
                _mho_zone(
                    label=label,
                    reach_ohm=reach,
                    angle_deg=angle if angle is not None else 75.0,
                    index=index,
                    source="xrio_mho",
                )
            )

    if zones:
        return zones

    # Flat param fallbacks from XRIO parameter dump
    return zones_from_settings_flat(flat, source="xrio_params")


def zones_from_settings_flat(
    flat: dict[str, Any],
    *,
    source: str = "settings",
) -> list[dict[str, Any]]:
    """Build mho zones from scalar zone reaches (relay_settings / ingest)."""
    # Nested protection.21
    prot = flat.get("protection") if isinstance(flat.get("protection"), dict) else {}
    el21 = prot.get("21") if isinstance(prot.get("21"), dict) else {}
    if not el21 and isinstance(flat.get("21"), dict):
        el21 = flat["21"]

    def pick(*keys: str) -> Optional[float]:
        for k in keys:
            if k in el21:
                v = _f(el21.get(k))
                if v is not None:
                    return v
            if k in flat:
                v = _f(flat.get(k))
                if v is not None:
                    return v
            kl = k.lower()
            for fk, fv in flat.items():
                if str(fk).lower().replace(" ", "_") == kl:
                    v = _f(fv)
                    if v is not None:
                        return v
        return None

    angle = pick("zone1_angle", "z1_angle", "lineangle", "z1ang") or 75.0
    zones: list[dict[str, Any]] = []
    z1 = pick("zone1_reach", "zone1_reach_ohm", "z1_reach_ohm", "z1mag", "z1p", "reach_ohm")
    z2 = pick("zone2_reach", "zone2_reach_ohm", "z2_reach_ohm", "z2mag", "z2p")
    z3 = pick("zone3_reach", "zone3_reach_ohm", "z3_reach_ohm", "z3mag", "z3p")
    for idx, (lab, reach) in enumerate(
        (("Z1", z1), ("Z2", z2), ("Z3", z3)),
        start=1,
    ):
        if reach and reach > 0:
            zones.append(
                _mho_zone(
                    label=lab,
                    reach_ohm=reach,
                    angle_deg=float(angle),
                    index=idx,
                    source=source,
                )
            )
    return zones


def extract_distance_zones(
    *,
    file_texts: Optional[list[tuple[str, str]]] = None,
    relay_settings: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """
    Prefer RIO/XRIO file shapes; else scalar settings reaches.

    file_texts: list of (filename, text)
    """
    zones: list[dict[str, Any]] = []
    for name, text in file_texts or []:
        n = (name or "").lower()
        if "begin distance" in (text or "").lower() or n.endswith(".rio"):
            zones.extend(parse_rio_text(text))
        if n.endswith((".xrio", ".xml")) or (text or "").lstrip().startswith("<"):
            zones.extend(parse_xrio_xml(text))
    if zones:
        return zones
    if relay_settings:
        return zones_from_settings_flat(relay_settings, source="relay_settings")
    return []
