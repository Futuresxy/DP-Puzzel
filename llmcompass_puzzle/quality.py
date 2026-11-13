"""Evidence-bound full-plan quality gates, independent of hardware rankings."""

from decimal import Decimal
from pathlib import Path

from ratio_dse.common import ROOT, digest, identity, number, require


def quality_key(model_revision, config_hash, numerical_plan):
    return identity("quality", {"model_revision": model_revision, "config_sha256": config_hash,
                                "numerical_plan": numerical_plan})


def assess_quality(key, policy, records, *, allow_test_records=False):
    """All requested metric/protocol pairs must pass; absent evidence stays unknown.

    Thresholds belong to the study policy, never to an evidence record. Numerical
    plan identity includes quantizer, calibration, scope and arithmetic semantics.
    Literature with another plan/checkpoint is a prior, not an admissible score.
    """
    requirements = policy.get("requirements", [])
    if not requirements:
        return {"quality_key": key, "status": "unknown", "admitted": False,
                "reason": "quality_thresholds_not_configured", "metrics": []}
    require(len({r["id"] for r in requirements}) == len(requirements), "duplicate quality requirement")
    results = []
    for requirement in requirements:
        fields = ("metric", "unit", "dataset", "dataset_revision", "protocol", "scope")
        require(all(isinstance(requirement[f], str) and requirement[f] for f in fields), "quality requirement lacks protocol fields")
        matches = [r for r in records if r.get("quality_key") == key
                   and all(r.get(f) == requirement[f] for f in fields)]
        require(len(matches) <= 1, "ambiguous quality evidence; aggregate repetitions under one protocol first")
        row = {"requirement_id": requirement["id"], "status": "unknown"}
        if not matches:
            results.append(row | {"reason": "no_matching_evidence"})
            continue
        record = matches[0]
        kind = record.get("evidence_kind")
        if kind != "measurement" and not (allow_test_records and kind == "synthetic_test_only"):
            results.append(row | {"reason": "prior_or_prediction_is_not_a_measurement"})
            continue
        artifact = Path(record["artifact"])
        if not artifact.is_absolute():
            artifact = ROOT / artifact
        if not artifact.is_file() or digest(artifact) != record["artifact_sha256"]:
            results.append(row | {"reason": "missing_or_mismatched_evidence_artifact"})
            continue
        reference = number("reference_value", record["reference_value"])
        candidate = number("candidate_value", record["candidate_value"])
        threshold = number("max_degradation", requirement["max_degradation"])
        direction, mode = requirement["direction"], requirement["degradation_mode"]
        require(direction in ("lower", "higher") and mode in ("absolute", "relative"), "invalid quality comparison")
        delta = Decimal(str(candidate)) - Decimal(str(reference))
        if direction == "higher":
            delta = -delta
        if mode == "relative":
            require(reference > 0, "relative degradation requires positive reference")
            delta /= Decimal(str(reference))
        results.append(row | {"status": "passed" if delta <= Decimal(str(threshold)) else "failed",
                              "reference_value": reference, "candidate_value": candidate,
                              "degradation": float(delta), "artifact_sha256": record["artifact_sha256"]})
    status = ("failed" if any(r["status"] == "failed" for r in results) else
              "unknown" if any(r["status"] == "unknown" for r in results) else "passed")
    return {"quality_key": key, "status": status, "admitted": status == "passed", "metrics": results}
