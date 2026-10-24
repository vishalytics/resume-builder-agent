
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
        "data-driven decisions", "actionable insights", "business insights",
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
    "working knowledge of power bi sql or other business intelligence tools": [
        "power bi", "sql",
    ],
    "analyze": ["analyse", "analyzed", "analysed", "analysis"],
    "analyse": ["analyze", "analyzed", "analysed", "analysis"],
    "build": ["built", "building", "developed", "created"],
    "manage": ["managed", "managing", "management"],
    "coordinate": ["coordinated", "coordination"],
    "identify": ["identified", "identifying"],
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

def build_ats_report(jd, match, cv):
    cv_text = cv_display_text(cv)
    print("=" * 60)
    print("ATS COMPATIBILITY CHECKER")
    print("=" * 60)

    terms = get_terms(jd)
    matched = []
    missing = []

    for term, group in terms.items():
        if matches_keyword(term, cv_text):
            matched.append({"keyword": term, "category": group})
        else:
            missing.append({"keyword": term, "category": group})


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
        "matching_recommendations": match.get(
            "recommendations", match.get("priority_changes", [])
        ),
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
    report = build_ats_report(
        load_json(JD_FILE), load_json(MATCH_FILE), load_json(CV_FILE)
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
