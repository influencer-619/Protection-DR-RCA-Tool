"""Setting version helpers."""

from __future__ import annotations

from typing import Optional


def compare_versions(a: str, b: str) -> Optional[int]:
    """
    Compare simple dotted or opaque versions.
    Returns -1, 0, 1 or None if not comparable.
    """
    if not a or not b:
        return None
    try:
        pa = [int(x) for x in a.replace("v", "").split(".")]
        pb = [int(x) for x in b.replace("v", "").split(".")]
    except ValueError:
        if a == b:
            return 0
        return None
    # Pad
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0
