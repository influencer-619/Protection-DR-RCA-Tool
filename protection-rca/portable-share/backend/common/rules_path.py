"""Resolve rules/ and templates/ relative to repo root or /app."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def _candidate_roots() -> list[Path]:
    here = Path(__file__).resolve()
    # backend/common/rules_path.py -> parents[2] = repo root (protection-rca)
    repo_root = here.parents[2]
    return [
        Path("/app"),
        repo_root,
        here.parents[1],  # backend/
        Path.cwd(),
    ]


@lru_cache(maxsize=1)
def resolve_rules_root() -> Path:
    """Return the rules directory. Prefer /app/rules, else <repo>/rules."""
    for root in _candidate_roots():
        candidate = root / "rules"
        if candidate.is_dir():
            return candidate
    # Fall back to repo-relative path even if not yet created
    return Path(__file__).resolve().parents[2] / "rules"


@lru_cache(maxsize=1)
def resolve_templates_root() -> Path:
    """Return the templates directory. Prefer /app/templates, else <repo>/templates."""
    for root in _candidate_roots():
        candidate = root / "templates"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parents[2] / "templates"


def load_yaml(path: Path) -> dict | list:
    import yaml

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if data is not None else {}
