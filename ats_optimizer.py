from copy import deepcopy
import re

from ats_checker import matches_keyword, normalize
from cv_generator import as_list, validate_cv


TARGET_ATS_SCORE = 90
MAX_OPTIMIZATION_ITERATIONS = 3
MIN_SCORE_IMPROVEMENT = 1
MAX_ADDITIONS_PER_ITERATION = 2
OPTIMIZER_CONFIG = {
    "target_score": TARGET_ATS_SCORE,
    "max_iterations": MAX_OPTIMIZATION_ITERATIONS,
    "minimum_score_improvement": MIN_SCORE_IMPROVEMENT,
    "max_evidence_bullets_per_iteration": MAX_ADDITIONS_PER_ITERATION,
}
EDITORIAL_MARKERS = (
    "confirm exact", "validate exact", "reported notes cite", "add your exact",
    "reconcile scope", "[₹x]", "[xx]", "placeholder",
)
MASTER_EVIDENCE_STOP_WORDS = frozenset({
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into",
    "of", "on", "or", "the", "to", "with",
})


def _usable_evidence_text(value):
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text or any(marker in text.casefold() for marker in EDITORIAL_MARKERS):
        return ""
    return text


def _master_supports_evidence(value, master_text):
    if master_text is None:
        return True
    candidate_numbers = set(re.findall(r"\d[\d,]*(?:\.\d+)?(?:\+|%)?", value))
    master_numbers = set(re.findall(r"\d[\d,]*(?:\.\d+)?(?:\+|%)?", master_text))
    if not candidate_numbers <= master_numbers:
        return False
    candidate_tokens = set(normalize(value).split()) - MASTER_EVIDENCE_STOP_WORDS
    master_tokens = set(normalize(master_text).split()) - MASTER_EVIDENCE_STOP_WORDS
    if not candidate_tokens:
        return False
    return len(candidate_tokens & master_tokens) / len(candidate_tokens) >= 0.65


def _evidence_bullet_candidates(resume_data, report, current_document_text, excluded, master_text=None):
    missing = report.get("missing_keywords", [])
    requirements = [
        item for item in missing
        if item.get("category") != "Important action verbs"
        and item.get("evidence_status") in {
            "supported_in_resume_not_presented_in_cv",
            "matcher_reports_source_support_but_cv_omits_term",
        }
    ]
    if not requirements:
        return []

    current_text = normalize(current_document_text)
    candidates = []
    for role_index, source_role in enumerate(resume_data.get("experience", [])):
        if not isinstance(source_role, dict):
            continue
        role_text = normalize(source_role)
        role_achievements = source_role.get("achievements", [])
        if not isinstance(role_achievements, list):
            continue
        for achievement_index, achievement in enumerate(role_achievements):
            if isinstance(achievement, dict):
                text = _usable_evidence_text(achievement.get("evidence"))
                if not text:
                    text = _usable_evidence_text(achievement.get("achievement"))
            else:
                text = _usable_evidence_text(achievement)
            if not text:
                continue
            if not _master_supports_evidence(text, master_text):
                continue
            normalized_bullet = normalize(text)
            candidate_key = (role_index, normalized_bullet)
            if candidate_key in excluded or normalized_bullet in current_text:
                continue
            matching_requirements = []
            for requirement in requirements:
                term = requirement.get("keyword", "")
                if (
                    matches_keyword(term, normalize(text))
                    and matches_keyword(term, role_text)
                ):
                    matching_requirements.append(requirement)
            if not matching_requirements:
                continue
            weighted_gain = sum(
                3 if item.get("category") == "Required skills"
                else 2 if item.get("category") == "Preferred skills"
                else 1
                for item in matching_requirements
            )
            candidates.append({
                "role_index": role_index,
                "achievement_index": achievement_index,
                "company": str(source_role.get("company", "")),
                "text": text,
                "key": candidate_key,
                "requirements": [item["keyword"] for item in matching_requirements],
                "weighted_gain": weighted_gain,
            })
    candidates.sort(key=lambda item: (-item["weighted_gain"], item["role_index"], item["achievement_index"]))
    return candidates


def _propose_evidence_additions(cv_data, candidates, limit):
    candidate = deepcopy(cv_data)
    experiences = candidate.get("experience", [])
    if not isinstance(experiences, list):
        return candidate, []
    additions = []
    for item in candidates:
        role_index = item["role_index"]
        if role_index >= len(experiences) or not isinstance(experiences[role_index], dict):
            continue
        bullets = as_list(experiences[role_index].get("bullets", []))
        if normalize(item["text"]) in {normalize(bullet) for bullet in bullets}:
            continue
        bullets.append(item["text"])
        experiences[role_index]["bullets"] = bullets
        additions.append({
            "company": item["company"],
            "bullet": item["text"],
            "requirements_addressed": item["requirements"],
        })
        if len(additions) >= limit:
            break
    return candidate, additions


def _report_key(report):
    coverage = report.get("keyword_coverage", {})
    return (
        int(report.get("ats_compatibility_score", 0)),
        int(coverage.get("matched_count", 0)),
        int(report.get("structure_score_percent", 0)),
    )


def optimize_cv(cv_data, jd_data, match_data, resume_data, evaluate_candidate, *, config=None, master_text=None):
    """Iteratively improve actual rendered-DOCX coverage using only source-evidence bullets."""
    settings = dict(OPTIMIZER_CONFIG)
    if config:
        settings.update(config)
    target_score = int(settings["target_score"])
    maximum_iterations = int(settings["max_iterations"])
    minimum_score_improvement = int(settings["minimum_score_improvement"])
    additions_limit = int(settings["max_evidence_bullets_per_iteration"])
    if maximum_iterations < 0 or additions_limit < 1:
        raise ValueError("Optimizer iteration and evidence-addition limits are invalid.")

    best_cv = deepcopy(cv_data)
    valid, message = validate_cv(best_cv)
    if not valid:
        raise ValueError(f"Initial CV failed validation: {message}")
    best_report, best_document_text = evaluate_candidate(best_cv)
    initial_score = int(best_report["ats_compatibility_score"])
    history = [{
        "iteration": 0,
        "score": initial_score,
        "matched_count": best_report["keyword_coverage"]["matched_count"],
        "selected": True,
        "improvements": [],
    }]
    excluded = set()
    plateau = 0
    iterations_completed = 0
    stop_reason = "maximum_iterations"
    if initial_score >= target_score:
        stop_reason = "target_reached"

    for iteration in range(1, maximum_iterations + 1):
        if stop_reason == "target_reached":
            break
        candidates = _evidence_bullet_candidates(
            resume_data, best_report, best_document_text, excluded, master_text
        )
        proposal, additions = _propose_evidence_additions(best_cv, candidates, additions_limit)
        if not additions:
            stop_reason = "evidence_insufficient"
            break
        iterations_completed = iteration
        valid, validation_message = validate_cv(proposal)
        if not valid:
            stop_reason = "quality_check_failed"
            history.append({
                "iteration": iteration,
                "selected": False,
                "improvements": [],
                "quality_error": validation_message,
            })
            break

        proposal_report, proposal_text = evaluate_candidate(proposal)
        score_delta = int(proposal_report["ats_compatibility_score"]) - int(best_report["ats_compatibility_score"])
        matched_delta = (
            int(proposal_report["keyword_coverage"]["matched_count"])
            - int(best_report["keyword_coverage"]["matched_count"])
        )
        meaningful = (
            score_delta >= minimum_score_improvement
            or matched_delta > 0
        )
        selected = meaningful and _report_key(proposal_report) > _report_key(best_report)
        history.append({
            "iteration": iteration,
            "score_before": int(best_report["ats_compatibility_score"]),
            "score_candidate": int(proposal_report["ats_compatibility_score"]),
            "matched_before": int(best_report["keyword_coverage"]["matched_count"]),
            "matched_candidate": int(proposal_report["keyword_coverage"]["matched_count"]),
            "selected": selected,
            "improvements": additions if selected else [],
        })
        if selected:
            best_cv = proposal
            best_report = proposal_report
            best_document_text = proposal_text
            plateau = 0
        else:
            excluded.update(item["key"] for item in candidates[:additions_limit])
            plateau += 1
        if int(best_report["ats_compatibility_score"]) >= target_score:
            stop_reason = "target_reached"
            break
        if plateau >= 2:
            stop_reason = "two_consecutive_non_improving_iterations"
            break
    else:
        stop_reason = "maximum_iterations"

    best_report = dict(best_report)
    best_report.pop("_document_text", None)
    optimization = {
        "target_score": target_score,
        "initial_score": initial_score,
        "final_score": int(best_report["ats_compatibility_score"]),
        "target_reached": int(best_report["ats_compatibility_score"]) >= target_score,
        "iterations_completed": iterations_completed,
        "maximum_iterations": maximum_iterations,
        "stop_reason": stop_reason,
        "history": history,
        "remaining_missing_requirements": [
            {
                "keyword": item["keyword"],
                "category": item["category"],
                "evidence_status": item["evidence_status"],
            }
            for item in best_report.get("missing_keywords", [])
            if item.get("category") != "Important action verbs"
        ],
    }
    return best_cv, best_report, optimization