"""Evidence model and evidence graph builder."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.core.enums import EvidenceSourceType


@dataclass
class Evidence:
    evidence_id: str
    source_type: str
    source_id: str
    parameter: str
    timestamp: Optional[float]
    value: Any
    unit: str
    expected: Any
    observed: Any
    interpretation: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceNode:
    node_id: str
    node_type: str  # RCA | Hypothesis | Finding | Calculation | RawData | SourceFile
    label: str
    evidence_id: Optional[str] = None
    children: list["EvidenceNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "evidence_id": self.evidence_id,
            "children": [c.to_dict() for c in self.children],
        }


def make_evidence(
    *,
    source_type: str,
    source_id: str,
    parameter: str,
    value: Any,
    unit: str = "",
    expected: Any = None,
    observed: Any = None,
    interpretation: str = "",
    confidence: str = "MEDIUM",
    timestamp: Optional[float] = None,
) -> Evidence:
    return Evidence(
        evidence_id=f"e-{uuid.uuid4().hex[:12]}",
        source_type=source_type,
        source_id=source_id,
        parameter=parameter,
        timestamp=timestamp,
        value=value,
        unit=unit,
        expected=expected,
        observed=observed if observed is not None else value,
        interpretation=interpretation,
        confidence=confidence,
    )


class EvidenceGraphBuilder:
    """Build RCA → Hypothesis → Finding → Calculation → Raw → SourceFile graph."""

    def build(
        self,
        *,
        rca_primary_id: str,
        hypotheses: list[dict[str, Any]],
        findings: list[dict[str, Any]],
        calculations: list[Evidence],
        source_files: list[str],
    ) -> EvidenceNode:
        root = EvidenceNode(
            node_id="rca-root",
            node_type="RCA",
            label=f"RCA:{rca_primary_id}",
        )
        finding_nodes = [
            EvidenceNode(
                node_id=f.get("finding_id", f"f-{i}"),
                node_type="Finding",
                label=f"{f.get('check_type')}:{f.get('element')}",
                evidence_id=f.get("finding_id"),
            )
            for i, f in enumerate(findings)
        ]
        calc_nodes = [
            EvidenceNode(
                node_id=c.evidence_id,
                node_type="Calculation",
                label=c.parameter,
                evidence_id=c.evidence_id,
                children=[
                    EvidenceNode(
                        node_id=f"raw-{c.evidence_id}",
                        node_type="RawData",
                        label=f"raw:{c.source_id}",
                        children=[
                            EvidenceNode(
                                node_id=f"file-{j}",
                                node_type="SourceFile",
                                label=sf,
                            )
                            for j, sf in enumerate(source_files[:3])
                        ],
                    )
                ],
            )
            for c in calculations
        ]
        for h in hypotheses:
            h_node = EvidenceNode(
                node_id=f"hyp-{h.get('hypothesis_id')}",
                node_type="Hypothesis",
                label=str(h.get("hypothesis_id")),
                children=list(finding_nodes) + list(calc_nodes),
            )
            root.children.append(h_node)
        if not hypotheses:
            root.children.extend(finding_nodes)
            root.children.extend(calc_nodes)
        return root
