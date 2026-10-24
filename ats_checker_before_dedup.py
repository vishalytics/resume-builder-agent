
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
    for group, values in groups:
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            continue

        for value in values:
            term = clean(value)
            if term and len(term) > 1:
                result.setdefault(term, group)

    return result

def main():
    print("=" * 60)
    print("ATS COMPATIBILITY CHECKER")
    print("=" * 60)

    jd = load_json(JD_FILE)
    match = load_json(MATCH_FILE)
    cv = load_json(CV_FILE)

    # Evaluate the generated CV, not the original master resume.
    cv_text = normalize(flatten(cv))
    jd_text = normalize(flatten(jd))

    terms = get_terms(jd)
    matched = []
    missing = []

    
    aliases = {
        "strong stakeholder management skills": ["stakeholder management", "stakeholder coordination", "stakeholder engagement"],
        "excellent excel and power bi skills": ["excel", "power bi"],
        "strong analytical and problem-solving abilities": [
            "analytical",
            "problem solving",
            "problem-solving",
            "data analysis",
            "analysis",
            "analytics",
            "process improvement",
            "performance dashboards",
            "data-driven decision-making",
            "data-driven",
            "decision-making",
            "data analysis and decision-making",
        ],
        "excellent communication skills": ["communication", "communicated", "presentations"],
        "cross-functional teams": ["cross-functional", "cross functional", "cross-functional collaboration"],
        "data analysis": ["data analysis", "data analytics", "analyzed", "analysed"],
        "manage": ["manage", "managed", "managing", "management"],
        "coordinate": ["coordinate", "coordinated", "coordination"],
        "build": ["build", "built", "building", "developed", "created"],
        "analyze": ["analyze", "analyzed", "analyse", "analysed", "analysis"],
        "identify": ["identify", "identified", "identifying"],
    }

    for term, group in terms.items():
        normalized_term = normalize(term)
        candidates = [normalized_term] + aliases.get(normalized_term, [])
        is_match = any(
            candidate and re.search(
                r"(?<![a-z0-9+#])" + re.escape(normalize(candidate)) +
                r"(?![a-z0-9+#])",
                cv_text
            )
            for candidate in candidates
        )

        # Recognize combined evidence for analytical/problem-solving skills.
        if normalized_term == "strong analytical and problem-solving abilities":
            evidence_terms = [
                "data analysis",
                "decision-making",
                "process improvement",
            ]
            is_match = is_match or all(
                re.search(
                    r"(?<![a-z0-9+#])" + re.escape(normalize(term)) +
                    r"(?![a-z0-9+#])",
                    cv_text
                )
                for term in evidence_terms
            )

        # Recognize combined evidence for analytical/problem-solving skills.
        if normalized_term == "strong analytical and problem-solving abilities":
            evidence_terms = [
                "data analysis",
                "decision-making",
                "process improvement",
            ]
            is_match = is_match or all(
                re.search(
                    r"(?<![a-z0-9+#])" + re.escape(normalize(term)) +
                    r"(?![a-z0-9+#])",
                    cv_text
                )
                for term in evidence_terms
            )

        if is_match:
            matched.append({"keyword": term, "category": group})
        else:
            missing.append({"keyword": term, "category": group})


    required = [x for x in terms if terms[x] == "Required skills"]
    preferred = [x for x in terms if terms[x] == "Preferred skills"]

    def coverage(items):
        if not items:
            return 100.0
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
        "Core expertise": bool(cv.get("core_expertise")),
        "Work experience": bool(cv.get("experience")),
        "Education": bool(cv.get("education")),
        "Certifications": bool(cv.get("certifications")),
    }

    structure_score = round(
        sum(checks.values()) / len(checks) * 100
    )

    # Keep the keyword score primary; report structure separately.
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "job_title": jd.get("job_title", jd.get("job_title", "Target role")),
        "company": jd.get("company", ""),
        "ats_compatibility_score": score,
        "score_note": (
            "Heuristic estimate based on keyword coverage. "
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
        "section_checks": checks,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "matching_recommendations": match.get("recommendations", []),
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

    OUTPUT.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT / "ats_report.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nTarget role: {report['job_title']}")
    print(f"ATS compatibility estimate: {score}/100")
    print(f"Required skills coverage: {required_score}%")
    print(f"Preferred skills coverage: {preferred_score}%")
    print(f"Overall keyword coverage: {overall_keyword_score}%")
    print(f"Section completeness: {structure_score}%")
    print(f"Matched keywords: {len(matched)}/{len(terms)}")

    print("\nMISSING KEYWORDS")
    for item in missing:
        print(f"- {item['keyword']} ({item['category']})")

    print("\nPRIORITY ACTIONS")
    for action in actions:
        print(f"- {action}")

    print(f"\nReport saved to: {report_path}")

if __name__ == "__main__":
    main()
