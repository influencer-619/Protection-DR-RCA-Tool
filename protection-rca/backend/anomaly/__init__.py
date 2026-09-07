"""Classical ML anomaly detection with mandatory model governance."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import numpy as np


@dataclass
class ModelGovernance:
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    feature_version: Optional[str] = None
    training_dataset_version: Optional[str] = None
    training_date: Optional[str] = None
    validation_metrics: Optional[dict[str, Any]] = None
    approval_status: Optional[str] = None
    deployment_date: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnomalyResult:
    status: str  # OK | NOT_AVAILABLE
    message: str
    scores: list[float] = field(default_factory=list)
    is_anomaly: Optional[bool] = None
    governance: ModelGovernance = field(default_factory=ModelGovernance)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "scores": self.scores,
            "is_anomaly": self.is_anomaly,
            "governance": self.governance.to_dict(),
            "limitations": self.limitations,
        }


class AnomalyDetector:
    """
    Optional IsolationForest anomaly detection.

    If no trained/approved model is provided, returns ML RESULT: NOT AVAILABLE.
    Never fabricates predictions.
    """

    def __init__(
        self,
        *,
        model: Any = None,
        governance: Optional[ModelGovernance] = None,
    ) -> None:
        self.model = model
        self.governance = governance or ModelGovernance()

    def analyze(self, feature_matrix: Optional[np.ndarray] = None) -> AnomalyResult:
        gov = self.governance
        approved = (gov.approval_status or "").upper() == "APPROVED"
        if self.model is None or not approved:
            return AnomalyResult(
                status="NOT_AVAILABLE",
                message="ML RESULT: NOT AVAILABLE",
                governance=gov,
                limitations=[
                    "No validated/approved anomaly model loaded",
                    "Classical ML must not fabricate predictions",
                ],
            )

        if feature_matrix is None or len(feature_matrix) == 0:
            return AnomalyResult(
                status="NOT_AVAILABLE",
                message="ML RESULT: NOT AVAILABLE",
                governance=gov,
                limitations=["Feature matrix empty"],
            )

        try:
            # IsolationForest: decision_function / predict
            if hasattr(self.model, "decision_function"):
                scores = [float(x) for x in self.model.decision_function(feature_matrix)]
            else:
                scores = []
            preds = None
            if hasattr(self.model, "predict"):
                preds = self.model.predict(feature_matrix)
            is_anom = None
            if preds is not None and len(preds):
                # sklearn IF: -1 = anomaly
                is_anom = bool(np.any(np.asarray(preds) == -1))
            return AnomalyResult(
                status="OK",
                message="Anomaly scores computed from approved model",
                scores=scores,
                is_anomaly=is_anom,
                governance=gov,
            )
        except Exception as exc:  # noqa: BLE001 — surface as NOT AVAILABLE
            return AnomalyResult(
                status="NOT_AVAILABLE",
                message="ML RESULT: NOT AVAILABLE",
                governance=gov,
                limitations=[f"Model inference failed: {exc}"],
            )
