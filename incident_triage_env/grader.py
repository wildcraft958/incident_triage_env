"""Deterministic scoring for agent diagnoses."""


def grade_diagnosis(
    service: str | None,
    fault_type: str | None,
    remediation: str | None,
    ground_truth: dict,
    causal_chain: list[str],
) -> dict:
    """Grade a submitted diagnosis against the ground truth.

    Returns a dict with 'score' in [0.0, 1.0], 'breakdown', and 'message'.
    Fault type and remediation points are only awarded when service was
    identified (exact match or partial via causal chain).
    """
    gt_service = ground_truth["service"]
    gt_fault = ground_truth["fault_type"]
    gt_remediation = ground_truth["remediation"]

    service_correct = 0.40 if service == gt_service else 0.0
    service_partial = 0.15 if (service_correct == 0.0 and service in causal_chain) else 0.0

    service_identified = service_correct > 0.0 or service_partial > 0.0

    fault_correct = 0.35 if (fault_type == gt_fault and service_identified) else 0.0
    remediation_correct = 0.25 if (remediation == gt_remediation and service_identified) else 0.0

    score = min(1.0, max(0.0, service_correct + service_partial + fault_correct + remediation_correct))

    breakdown = {
        "service_correct": service_correct,
        "service_partial": service_partial,
        "fault_correct": fault_correct,
        "remediation_correct": remediation_correct,
    }

    if score == 1.0:
        message = "Perfect diagnosis."
    elif score == 0.0:
        message = "Incorrect diagnosis."
    else:
        parts = []
        if service_correct:
            parts.append("service correct")
        elif service_partial:
            parts.append("service in causal chain")
        if fault_correct:
            parts.append("fault type correct")
        if remediation_correct:
            parts.append("remediation correct")
        message = "Partial credit: " + ", ".join(parts) + "."

    return {"score": score, "breakdown": breakdown, "message": message}
