from __future__ import annotations

from baby_cry_detection.monitor.backends.base import DetectionResult
from baby_cry_detection.monitor.config import MonitorConfig


def passes_verifier(config: MonitorConfig, result: DetectionResult) -> bool:
    return passes_verifier_with_thresholds(
        result=result,
        baby_threshold=config.baby_threshold,
        cat_weight=config.cat_weight,
        margin_threshold=config.margin_threshold,
        cat_suppress_threshold=config.cat_suppress_threshold,
    )


def passes_verifier_with_thresholds(
    result: DetectionResult,
    baby_threshold: float,
    cat_weight: float,
    margin_threshold: float,
    cat_suppress_threshold: float,
) -> bool:
    if result.baby_score < baby_threshold:
        return False

    margin = result.baby_score - cat_weight * result.cat_score
    if margin < margin_threshold:
        return False

    cat_dominates = result.cat_score >= cat_suppress_threshold and result.baby_score <= result.cat_score
    return not cat_dominates
