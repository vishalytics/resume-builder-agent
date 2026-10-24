
import json
import re
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
DATA = BASE / "data"
OUTPUT = BASE / "output"

JD_FILE = DATA / "jd_analysis.json"
MATCH_FILE = DATA / "resume_jd_match.json"
CV_FILE = DATA / "generated_cv.json"

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def clean(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(clean(x) for x in value)
    if isinstance(value, dict):
        return " ".join(clean(x) for x in value.values())
    return str(value or "")

def normalize(text):
    text = str(text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"power\s*bi", "power bi", text)
    text = re.sub(r"\bms\s*excel\b", "excel", text)
    text = re.sub(r"\bteamwork\b", "team collaboration", text)
    text = re.sub(r"\bcross functional\b", "cross-functional", text)
    return re.sub(r"[^a-z0-9+#.]+", " ", text).strip()

def flatten(value):
    if isinstance(value, dict):
        return " ".join(flatten(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(flatten(v) for v in value)
    return str(value or "")

def cv_display_text(cv):
    fields = (
        "name", "targeted_headline", "targeted_summary", "core_expertise",
        "skills", "tools_and_technologies", "experience", "education",
        "achievements", "leadership", "certifications",
    )
    return normalize(" ".join(flatten(cv.get(field, "")) for field in fields))


ALIASES = {
    "ability to translate data into business insights": [
        "data-driven decisions", "data-informed decisions", "actionable insights",
        "business insights",
    ],
    "advanced excel skills": ["advanced excel", "excel reporting"],
    "building business dashboards": [
        "power bi dashboards", "procurement analytics dashboards",
        "performance dashboards",
    ],
    "managing cross-functional projects and multiple priorities": [
        "cross-functional program management", "cross-functional rollout",
        "cross-functional programs",
    ],
    "stakeholder management": ["stakeholder coordination", "stakeholder engagement"],
    "competitor benchmarking": ["competitor analysis", "competitive benchmarking"],
    "pricing analysis": ["pricing intelligence", "pricing trends"],
    "go to market gtm strategy": ["gtm strategy", "go to market strategy"],
    "standard operating procedures sops": ["sops"],
    "key performance indicators kpis": ["kpis", "kpi"],
    "operational metrics": ["operational reporting", "business metrics", "key business metrics"],
    "automation solutions": ["automation", "automated workflows", "workflow automation"],
    "cross functional leadership": [
        "cross-functional program management", "cross-functional rollout",
        "cross-functional implementation",
    ],
    "working knowledge of power bi sql or other business intelligence tools": [
        "power bi", "sql",
    ],
    "analyze": ["analyse", "analyzed", "analysed", "analysis"],
    "analyse": ["analyze", "analyzed", "analysed", "analysis"],
    "build": ["built", "building", "developed", "created"],
    "manage": ["managed", "managing", "management"],
    "coordinate": ["coordinated", "coordination"],
    "identify": ["identified", "identifying"],
    "execute": ["executed", "executing", "execution"],
    "implement": ["implemented", "implementing", "implementation"],
    "develop": ["developed", "developing", "development"],
    "monitor": ["monitored", "monitoring"],
    "communicate": ["communicated", "communicating", "communication"],
    "conduct": ["conducted", "conducting"],
    "prepare": ["prepared", "preparing", "preparation"],
    "work": ["worked", "working"],
}


def matches_keyword(term, cv_text):
    normalized_term = normalize(term)
    candidates = [normalized_term] + ALIASES.get(normalized_term, [])
    if any(
        candidate and re.search(
            r"(?<![a-z0-9+#])" + re.escape(normalize(candidate)) + r"(?![a-z0-9+#])",
            cv_text,
        )
        for candidate in candidates
    ):
        return True

    analytical_requirement = normalized_term in {
        "analytical and problem solving skills",
        "analytical and problem solving abilities",
        "strong analytical and problem solving abilities",
    }
    if analytical_requirement:
        evidence_groups = (
            ("analytical", "data analysis", "analytics"),
            ("problem solving", "process improvement", "operational efficiency"),
            ("data driven decisions", "decision making", "business insights"),
        )
        supported = sum(
            any(normalize(phrase) in cv_text for phrase in group)
            for group in evidence_groups
        )
        return supported >= 2
    return False


def _requirement_tokens(value):
    tokens = set(normalize(value).split())
    tokens.discard("skills")
    tokens.discard("skill")
    return {"model" if token in {"models", "modeling", "modelling"} else token for token in tokens}


def _responsibility_alignment(jd, match):
    responsibilities = jd.get("responsibilities", [])
    if isinstance(responsibilities, str):
        responsibilities = [responsibilities]
    if not isinstance(responsibilities, list) or not responsibilities:
        return {"coverage_percent": 0.0, "matched_count": 0, "total_count": 0, "items": []}
    strong = match.get("strong_matches", [])
    partial = match.get("partial_matches", [])
    no_evidence = match.get("no_evidence", [])
    match_groups = (
        ("strong", strong if isinstance(strong, list) else []),
        ("partial", partial if isinstance(partial, list) else []),
        ("unsupported", no_evidence if isinstance(no_evidence, list) else []),
    )
    items = []
    weighted_coverage = 0.0
    matched_count = 0
    for responsibility in responsibilities:
        requirement_tokens = _requirement_tokens(responsibility)
        status = "not_assessed"
        for match_status, entries in match_groups:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                matched_tokens = _requirement_tokens(entry.get("requirement", ""))
                overlap = len(requirement_tokens & matched_tokens) / max(1, len(requirement_tokens))
                if overlap >= 0.75 and len(requirement_tokens & matched_tokens) >= min(3, len(requirement_tokens)):
                    status = match_status
                    break
            if status != "not_assessed":
                break
        if status == "strong":
            weighted_coverage += 1.0
            matched_count += 1
        elif status == "partial":
            weighted_coverage += 0.5
            matched_count += 1
        items.append({"responsibility": responsibility, "evidence_status": status})
    return {
        "coverage_percent": round(weighted_coverage / len(responsibilities) * 100, 1),
        "matched_count": matched_count,
        "total_count": len(responsibilities),
        "items": items,
    }


def get_terms(jd):
    groups = [
        ("Required skills", jd.get("required_skills", [])),
        ("Preferred skills", jd.get("preferred_skills", [])),
        ("Tools and technologies", jd.get("tools_and_technologies", [])),
        ("Domain keywords", jd.get("domain_keywords", [])),
        ("ATS keywords", jd.get("ats_keywords", [])),
        ("Important action verbs", jd.get("important_action_verbs", [])),
    ]

    result = {}
    seen_terms = set()
    for group, values in groups:
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue

        for value in values:
            term = clean(value)
            normalized_term = normalize(term)
            if term and len(normalized_term) > 1 and normalized_term not in seen_terms:
                result[term] = group
                seen_terms.add(normalized_term)

    return result

def build_ats_report(jd, match, cv, resume_evidence=None, *, document_text=None, document_integrity=None):
    cv_text = normalize(document_text) if isinstance(document_text, str) and document_text.strip() else cv_display_text(cv)
    source_text = normalize(flatten(resume_evidence or {}))

    terms = get_terms(jd)
    matched = []
    missing = []

    for term, group in terms.items():
        if matches_keyword(term, cv_text):
            matched.append({"keyword": term, "category": group})
        else:
            missing.append({"keyword": term, "category": group})

    source_match_terms = {
        normalize(term): term
        for term in match.get("keyword_matches", [])
        if isinstance(term, str)
    }
    missing_status = []
    for item in missing:
        term = item["keyword"]
        normalized_term = normalize(term)
        if source_text and matches_keyword(term, source_text):
            status = "supported_in_resume_not_presented_in_cv"
        elif normalized_term in source_match_terms:
            status = "matcher_reports_source_support_but_cv_omits_term"
        elif any(
            _requirement_tokens(term)
            <= _requirement_tokens(partial.get("requirement", ""))
            for partial in match.get("partial_matches", [])
            if isinstance(partial, dict)
        ):
            status = "partial_evidence_only"
        else:
            status = "not_verified_in_resume_evidence"
        missing_status.append({**item, "evidence_status": status})


    required = [x for x in terms if terms[x] == "Required skills"]
    preferred = [x for x in terms if terms[x] == "Preferred skills"]

    def coverage(items):
        if not items:
            return 0.0
        count = sum(
            1 for item in items
            if any(m["keyword"] == item for m in matched)
        )
        return round(count / len(items) * 100, 1)

    required_score = coverage(required)
    preferred_score = coverage(preferred)
    overall_keyword_score = coverage(list(terms.keys()))

    # Transparent heuristic score, not a proprietary ATS prediction.
    score = round(
        0.50 * required_score
        + 0.15 * preferred_score
        + 0.35 * overall_keyword_score
    )

    # Structural checks against the generated CV fields.
    checks = {
        "Candidate name": bool(cv.get("name")),
        "Professional headline": bool(cv.get("targeted_headline")),
        "Professional summary": bool(cv.get("targeted_summary")),
        "Core expertise": bool(cv.get("core_expertise") or cv.get("skills")),
        "Work experience": bool(cv.get("experience")),
        "Education": bool(cv.get("education")),
        "Certifications": bool(cv.get("certifications")),
    }

    structure_score = round(
        sum(checks.values()) / len(checks) * 100
    )
    strong_count = len(match.get("strong_matches", []))
    partial_count = len(match.get("partial_matches", []))
    unsupported_count = len(match.get("no_evidence", []))
    evidence_requirement_count = strong_count + partial_count + unsupported_count
    experience_alignment = round(
        (strong_count + 0.5 * partial_count) / evidence_requirement_count * 100
    ) if evidence_requirement_count else 0.0
    responsibility_alignment = _responsibility_alignment(jd, match)

    recommendations = []
    for item in missing_status:
        if item["category"] == "Important action verbs":
            continue
        term = item["keyword"]
        if item["evidence_status"] == "supported_in_resume_not_presented_in_cv":
            recommendations.append(
                f"Consider presenting the verified resume evidence for '{term}' in the CV where it fits naturally."
            )
        elif item["evidence_status"] == "partial_evidence_only":
            recommendations.append(
                f"Describe the documented adjacent evidence for '{term}' and state its limits; do not claim full direct experience."
            )
        elif item["evidence_status"] == "not_verified_in_resume_evidence":
            recommendations.append(
                f"Keep '{term}' unclaimed unless the candidate can verify supporting experience or qualification."
            )

    # Keep the keyword score primary; report structure separately.
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "job_title": jd.get("job_title", "Target role"),
        "company": jd.get("company", ""),
        "ats_compatibility_score": score,
        "score_note": (
            "Heuristic estimate = 50% required-skill coverage + 15% preferred-skill "
            "coverage + 35% coverage of all listed JD terms. Empty groups score 0%. "
            "This is not an actual score from an employer's ATS."
        ),
        "keyword_coverage": {
            "required_skills_percent": required_score,
            "preferred_skills_percent": preferred_score,
            "all_jd_terms_percent": overall_keyword_score,
            "matched_count": len(matched),
            "total_count": len(terms),
        },
        "structure_score_percent": structure_score,
        "experience_alignment_percent": experience_alignment,
        "responsibility_alignment": responsibility_alignment,
        "experience_evidence_counts": {
            "strong": strong_count,
            "partial": partial_count,
            "unsupported_or_unverified": unsupported_count,
            "total": evidence_requirement_count,
        },
        "document_integrity": document_integrity if document_integrity is not None else {
            "checked": False,
            "note": "No rendered DOCX was supplied to the ATS evaluator.",
        },
        "section_checks": checks,
        "matched_keywords": matched,
        "missing_keywords": missing_status,
        "relevant_experience_evidence": {
            "strong_matches": match.get("strong_matches", []),
            "partial_matches": match.get("partial_matches", []),
        },
        "unsupported_or_unverified_requirements": match.get("no_evidence", []),
        "matching_recommendations": recommendations,
        "priority_actions": [],
    }

    actions = []

    if required_score < 100:
        actions.append(
            "Review missing required skills. Add them only where "
            "supported by genuine experience or qualifications."
        )

    if preferred_score < 100:
        actions.append(
            "Review preferred skills and include relevant evidence "
            "where accurate."
        )

    if not checks["Certifications"]:
        actions.append(
            "Check the certifications section in the generated CV."
        )

    if not checks["Work experience"]:
        actions.append(
            "Check whether professional experience was populated."
        )

    if score < 90:
        actions.append(
            "Review the highest-priority missing keywords and "
            "revise the CV without inventing experience."
        )

    report["priority_actions"] = actions
    return report


def main():
    print("=" * 60)
    print("ATS COMPATIBILITY CHECKER")
    print("=" * 60)
    evidence_path = DATA / "resume_evidence.json"
    evidence = load_json(evidence_path) if evidence_path.is_file() else {}
    report = build_ats_report(
        load_json(JD_FILE), load_json(MATCH_FILE), load_json(CV_FILE), evidence
    )
    score = report["ats_compatibility_score"]
    required_score = report["keyword_coverage"]["required_skills_percent"]
    preferred_score = report["keyword_coverage"]["preferred_skills_percent"]
    overall_keyword_score = report["keyword_coverage"]["all_jd_terms_percent"]
    structure_score = report["structure_score_percent"]
    matched = report["matched_keywords"]
    missing = report["missing_keywords"]
    actions = report["priority_actions"]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT / "ats_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nTarget role: {report['job_title']}")
    print(f"ATS compatibility estimate: {score}/100")
    print(f"Required skills coverage: {required_score}%")
    print(f"Preferred skills coverage: {preferred_score}%")
    print(f"Overall keyword coverage: {overall_keyword_score}%")
    print(f"Section completeness: {structure_score}%")
    print(f"Matched keywords: {len(matched)}/{report['keyword_coverage']['total_count']}")

    print("\nMISSING KEYWORDS")
    for item in missing:
        print(f"- {item['keyword']} ({item['category']})")

    print("\nPRIORITY ACTIONS")
    for action in actions:
        print(f"- {action}")

    print(f"\nReport saved to: {report_path}")

if __name__ == "__main__":
    main()
