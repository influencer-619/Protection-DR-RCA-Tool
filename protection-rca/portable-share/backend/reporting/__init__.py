"""Deterministic Jinja2 HTML report generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from common.rules_path import resolve_templates_root


STATEMENT_KINDS = ("OBSERVED", "CALCULATED", "INFERRED", "HYPOTHESIS")


def _as_pct_filter(value: Any) -> str:
    """Jinja filter: show 0–1 scores as percentage (e.g. 0.7975 → 79.8%)."""
    if value is None:
        return "—"
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return "—"
        if s.endswith("%"):
            return s
        try:
            value = float(s)
        except ValueError:
            return s
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if 0.0 <= f <= 1.0:
        f *= 100.0
    if abs(f - round(f)) < 1e-9:
        return f"{int(round(f))}%"
    return f"{f:.1f}%"


@dataclass
class ReportStatement:
    kind: str  # OBSERVED | CALCULATED | INFERRED | HYPOTHESIS
    text: str
    section: str


@dataclass
class ReportBundle:
    html: str
    statements: list[ReportStatement] = field(default_factory=list)
    template_version: str = "1.0.0"
    limitations: list[str] = field(default_factory=list)


class SentenceLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (resolve_templates_root() / "sentences")
        self._cache: dict[str, dict[str, str]] = {}

    def get(self, category: str, key: str, **kwargs: Any) -> str:
        if category not in self._cache:
            path = self.root / f"{category}.yaml"
            if not path.is_file():
                self._cache[category] = {}
            else:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                self._cache[category] = dict(data.get("sentences") or {})
        tmpl = self._cache[category].get(key)
        if not tmpl:
            return f"[{category}.{key} NOT AVAILABLE]"
        try:
            return tmpl.format(**kwargs)
        except KeyError:
            return tmpl


class ReportGenerator:
    def __init__(self, templates_root: Path | None = None) -> None:
        self.templates_root = templates_root or resolve_templates_root()
        self.sentences = SentenceLibrary(self.templates_root / "sentences")
        report_dir = self.templates_root / "reports"
        self.env = Environment(
            loader=FileSystemLoader(str(report_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            auto_reload=True,
        )
        self.env.filters["as_pct"] = _as_pct_filter

    def build_statements(self, analysis: dict[str, Any]) -> list[ReportStatement]:
        stmts: list[ReportStatement] = []
        fault = analysis.get("fault_classification") or {}
        ft = fault.get("fault_type")
        st = fault.get("status")
        if st == "CLASSIFIED" and ft and ft != "UNKNOWN":
            stmts.append(
                ReportStatement(
                    "OBSERVED",
                    self.sentences.get("fault", "classified", fault_type=ft),
                    "Fault Classification",
                )
            )
        elif st == "PROBABLE" and ft:
            stmts.append(
                ReportStatement(
                    "INFERRED",
                    self.sentences.get("fault", "probable", fault_type=ft),
                    "Fault Classification",
                )
            )
        else:
            stmts.append(
                ReportStatement(
                    "INFERRED",
                    self.sentences.get("fault", "inconclusive"),
                    "Fault Classification",
                )
            )

        dist_obj = fault.get("distance")
        dist = dist_obj.get("status") if isinstance(dist_obj, dict) else None
        display = fault.get("distance_display")
        # Only mention missing km when location was attempted / in scope — not for OC/diff/BF-only cases.
        attempted = bool(
            (isinstance(dist_obj, dict) and dist_obj.get("status") not in (None, "NOT_APPLICABLE", "N/A", "NA"))
            and (
                dist_obj.get("reason")
                or dist_obj.get("method")
                or dist_obj.get("algorithms")
                or dist == "NOT_CALCULABLE"
            )
            or (isinstance(display, str) and display.strip() and "NOT_APPLICABLE" not in display.upper())
        )
        if attempted and (
            dist == "NOT_CALCULABLE"
            or (
                isinstance(display, str)
                and "NOT CALCULABLE" in display.upper()
            )
        ):
            stmts.append(
                ReportStatement(
                    "CALCULATED",
                    self.sentences.get("fault", "distance_not_calculable"),
                    "Fault Classification",
                )
            )

        for a in analysis.get("protection_assessment") or []:
            el = a.get("element")
            if a.get("consistency") == "CONSISTENT" and a.get("actual_operation") == "OPERATED":
                stmts.append(
                    ReportStatement(
                        "OBSERVED",
                        self.sentences.get("protection", "operated_consistent", element=el),
                        "Protection Operation",
                    )
                )
            elif a.get("consistency") == "INCONSISTENT":
                stmts.append(
                    ReportStatement(
                        "OBSERVED",
                        self.sentences.get("protection", "operated_inconsistent", element=el),
                        "Protection Consistency Check",
                    )
                )

        if any(
            f.get("status") == "INCONSISTENT"
            for f in (analysis.get("consistency_findings") or [])
        ):
            stmts.append(
                ReportStatement(
                    "INFERRED",
                    self.sentences.get("consistency", "inconsistent_disabled"),
                    "Protection Consistency Check",
                )
            )

        rca = analysis.get("rca_hypotheses") or {}
        primary = rca.get("primary") or {}
        if primary:
            hid = primary.get("hypothesis_id", "UNKNOWN")
            status = (primary.get("status") or "INCONCLUSIVE").lower()
            key = {
                "confirmed": "confirmed",
                "probable": "probable",
                "possible": "possible",
                "unlikely": "unlikely",
                "inconclusive": "inconclusive",
            }.get(status, "inconclusive")
            stmts.append(
                ReportStatement(
                    "HYPOTHESIS",
                    self.sentences.get("rca", key, hypothesis=hid),
                    "RCA Assessment",
                )
            )
        return stmts

    def render(self, analysis: dict[str, Any]) -> ReportBundle:
        statements = self.build_statements(analysis)
        template_path = self.templates_root / "reports" / "event_report.html.j2"
        limitations = list(analysis.get("limitations") or [])
        if not template_path.is_file():
            return ReportBundle(
                html="<html><body>Report template NOT AVAILABLE</body></html>",
                statements=statements,
                limitations=limitations + ["Report template NOT AVAILABLE"],
            )
        tmpl = self.env.get_template("event_report.html.j2")
        html = tmpl.render(
            analysis=analysis,
            statements=[{"kind": s.kind, "text": s.text, "section": s.section} for s in statements],
            kinds=STATEMENT_KINDS,
        )
        return ReportBundle(html=html, statements=statements, limitations=limitations)
