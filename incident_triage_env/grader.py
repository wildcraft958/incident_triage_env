"""Deterministic scoring for agent diagnoses and investigation quality."""


EVIDENCE_KEYWORDS: dict[str, list[str]] = {
    "oom": ["outofmemoryerror", "heap", "gc overhead", "memory_pct"],
    "cpu_saturated": ["cpu", "100%", "thread pool", "saturated"],
    "connection_leak": ["pool exhausted", "connection pool", "idle connections", "connections in use"],
    "disk_full": ["no space left", "disk full", "read-only", "disk_usage"],
    "config_error": ["config push", "config change", "rollback", "config_error"],
    "network_partition": ["network", "partition", "unreachable"],
    "dependency_timeout": ["timeout", "timed out", "dependency"],
    "certificate_expired": ["certificate", "tls", "handshake", "expired", "cert"],
    "memory_leak": ["memory", "heap", "leak", "climbing"],
    "thread_deadlock": ["deadlock", "thread", "hung", "zero throughput"],
    "dns_failure": ["dns", "servfail", "resolution", "unreachable"],
}


def grade_diagnosis(
    service: str | None,
    fault_type: str | None,
    remediation: str | None,
    ground_truth: dict,
    causal_chain: list[str],
    hypothesis_evidence: str | None = None,
    scenario: dict | None = None,
    service_criticality: dict | None = None,
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

    base_score = service_correct + service_partial + fault_correct + remediation_correct

    criticality_adj = _criticality_adjustment(
        service_correct > 0, service_identified, gt_service, service_criticality
    )

    evidence_bonus = _score_evidence(hypothesis_evidence, gt_service, gt_fault, scenario)

    score = min(1.0, max(0.0, base_score + criticality_adj + evidence_bonus))

    breakdown = {
        "service_correct": service_correct,
        "service_partial": service_partial,
        "fault_correct": fault_correct,
        "remediation_correct": remediation_correct,
        "criticality_adjustment": criticality_adj,
        "evidence_bonus": evidence_bonus,
    }

    if score >= 1.0:
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
        if evidence_bonus > 0:
            parts.append(f"evidence bonus +{evidence_bonus:.2f}")
        message = "Partial credit: " + ", ".join(parts) + "."

    return {"score": score, "breakdown": breakdown, "message": message}


def _criticality_adjustment(
    service_exact: bool,
    service_identified: bool,
    root_service: str,
    service_criticality: dict | None,
) -> float:
    """Small scoring adjustment based on root cause service criticality.

    Tier 1 (critical) correct diagnosis: +0.02 bonus
    Tier 1 wrong diagnosis: -0.03 penalty
    Tier 2: no adjustment
    Tier 3: no adjustment
    """
    if not service_criticality:
        return 0.0
    tier = service_criticality.get(root_service, 2)
    if tier == 1:
        if service_exact:
            return 0.02
        if not service_identified:
            return -0.03
    return 0.0


def _score_evidence(
    hypothesis_evidence: str | None,
    root_service: str,
    fault_type: str,
    scenario: dict | None,
) -> float:
    """Score hypothesis evidence for up to +0.10 bonus."""
    if not hypothesis_evidence:
        return 0.0

    bonus = 0.0
    evidence_lower = hypothesis_evidence.lower()

    # +0.05 if evidence references the root cause service
    if root_service.lower() in evidence_lower:
        bonus += 0.05

    # +0.02 per matching signal keyword (max +0.05)
    keywords = EVIDENCE_KEYWORDS.get(fault_type, [])
    matches = sum(1 for kw in keywords if kw.lower() in evidence_lower)
    if matches > 0:
        bonus += min(0.05, matches * 0.02)

    return round(bonus, 2)


def grade_investigation_quality(
    history: list[dict],
    causal_chain: list[str],
    all_services: list[str],
    topology: dict,
) -> dict:
    """Score the quality of the investigation process.

    Rewards agents that follow good SRE methodology:
    1. Understand the system (check topology early)
    2. Investigate causal chain services
    3. Cross-reference logs and metrics for the same service
    4. Stay focused on relevant services
    5. Follow dependency links in investigation order

    Returns dict with 'score' in [0.0, 0.30] and 'breakdown'.
    """
    if not history:
        return {"score": 0.0, "breakdown": {}}

    score = 0.0
    breakdown = {}

    # 1. Did agent check topology early? (0.0-0.05)
    topo_positions = [
        i for i, h in enumerate(history)
        if h["action_type"] == "check_topology"
    ]
    if topo_positions:
        earliest = topo_positions[0]
        topo_score = max(0.0, 0.05 - (earliest * 0.01))
        score += topo_score
        breakdown["topology_timing"] = round(topo_score, 3)

    # 2. Causal chain coverage (0.0-0.10)
    investigated = set()
    for h in history:
        if h.get("target_service") and h["action_type"] in (
            "query_logs", "query_metrics", "trace_request"
        ):
            investigated.add(h["target_service"])

    chain_set = set(causal_chain)
    if chain_set:
        coverage = len(investigated & chain_set) / len(chain_set)
        coverage_score = round(coverage * 0.10, 3)
        score += coverage_score
        breakdown["causal_chain_coverage"] = coverage_score

    # 3. Cross-referencing: logs AND metrics for same causal service (0.0-0.05)
    log_services = {
        h["target_service"] for h in history
        if h["action_type"] == "query_logs" and h.get("target_service")
    }
    metric_services = {
        h["target_service"] for h in history
        if h["action_type"] == "query_metrics" and h.get("target_service")
    }
    cross_referenced = log_services & metric_services & chain_set
    if chain_set:
        depth = len(cross_referenced) / len(chain_set)
        depth_score = round(depth * 0.05, 3)
        score += depth_score
        breakdown["cross_reference_depth"] = depth_score

    # 4. Focus ratio: relevant vs total investigated (0.0-0.05)
    total_investigated = len(investigated)
    relevant_investigated = len(investigated & chain_set)
    if total_investigated > 0:
        focus = relevant_investigated / total_investigated
        focus_score = round(focus * 0.05, 3)
        score += focus_score
        breakdown["investigation_focus"] = focus_score

    # 5. Logical flow: did agent follow dependency edges? (0.0-0.05)
    investigated_order = [
        h["target_service"] for h in history
        if h.get("target_service") and h["action_type"] in (
            "query_logs", "query_metrics"
        )
    ]
    follows_deps = 0
    for i in range(1, len(investigated_order)):
        prev_svc = investigated_order[i - 1]
        curr_svc = investigated_order[i]
        prev_deps = topology.get(prev_svc, [])
        curr_deps = topology.get(curr_svc, [])
        if curr_svc in prev_deps or prev_svc in curr_deps:
            follows_deps += 1

    if len(investigated_order) > 1:
        flow = follows_deps / (len(investigated_order) - 1)
        flow_score = round(flow * 0.05, 3)
        score += flow_score
        breakdown["logical_flow"] = flow_score

    return {"score": round(min(score, 0.30), 3), "breakdown": breakdown}
