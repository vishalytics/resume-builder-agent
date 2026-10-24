import json
import re
from pathlib import Path
from gemini_client import generate_with_fallback, parse_json_response

BASE_DIR = Path(__file__).resolve().parent




def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_match_response(response_text):
    try:
        result = parse_json_response(response_text)
    except ValueError:
        return False, "invalid_json"
    list_fields = (
        "strong_matches", "partial_matches", "no_evidence", "keyword_matches",
        "missing_keywords", "recommended_resume_keywords",
        "recommended_experiences", "recommended_projects", "skill_gaps",
        "priority_changes",
    )
    if any(not isinstance(result.get(field), list) for field in list_fields):
        return False, "invalid_match_field"
    if not isinstance(result.get("overall_match"), (int, float)):
        return False, "invalid_match_score"
    return True, "valid"


def _normalized_tokens(value):
    return set(re.findall(r"[a-z0-9+#.]+", str(value or "").lower()))


def verify_match_evidence(result, resume_data, jd_data):
    resume_text = json.dumps(resume_data, ensure_ascii=False).lower()
    jd_text = json.dumps(jd_data, ensure_ascii=False).lower()
    resume_tokens = _normalized_tokens(resume_text)
    jd_tokens = _normalized_tokens(jd_text)
    ignored = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "the", "to", "with"}
    rejected = []

    for field in ("strong_matches", "partial_matches"):
        verified = []
        for item in result.get(field, []):
            if not isinstance(item, dict):
                rejected.append({"match": item, "reason": "Match entry is not an object."})
                continue
            evidence_tokens = _normalized_tokens(item.get("evidence", "")) - ignored
            requirement_tokens = _normalized_tokens(item.get("requirement", "")) - ignored
            metrics = item.get("metrics", [])
            if not isinstance(metrics, list):
                metrics = []
            metric_tokens = set().union(*(_normalized_tokens(metric) for metric in metrics)) if metrics else set()
            company = str(item.get("company", item.get("relevant_company", "")) or "").strip().lower()
            role = str(item.get("role", item.get("relevant_role", "")) or "").strip().lower()
            supported = (
                bool(evidence_tokens)
                and evidence_tokens <= resume_tokens
                and (not requirement_tokens or requirement_tokens <= jd_tokens)
                and (not company or _normalized_tokens(company) - ignored <= resume_tokens)
                and (not role or _normalized_tokens(role) - ignored <= resume_tokens)
                and metric_tokens <= resume_tokens
            )
            if supported:
                verified.append(item)
            else:
                rejected.append({
                    "requirement": item.get("requirement", "Unverified requirement"),
                    "reason": "Model-suggested evidence did not pass deterministic resume/JD verification.",
                })
        result[field] = verified

    if rejected:
        result["unverified_model_matches"] = rejected
        result.setdefault("no_evidence", []).extend(rejected)
    else:
        result["unverified_model_matches"] = []
    return result


def match_resume_to_jd(resume_data, jd_data, event_sink=None):
    if not isinstance(resume_data, dict) or not isinstance(jd_data, dict):
        raise ValueError("Resume evidence and JD analysis must be JSON objects.")

    prompt = f"""
You are an expert Resume-to-JD Matching Engine.

Your task is to compare a candidate's VERIFIED career evidence
against a job description.

IMPORTANT RULES:

1. NEVER invent experience.
2. NEVER assume the candidate has a skill just because it is common
   for the role.
3. Use ONLY evidence contained in the resume evidence database.
4. Preserve metrics exactly as provided.
5. Distinguish between:
   - STRONG_MATCH
   - PARTIAL_MATCH
   - NO_EVIDENCE
6. A keyword should NOT be considered a match unless the resume contains
   actual supporting evidence.
7. Identify the strongest evidence that should be used in the tailored CV.
8. Identify genuine skill gaps.
9. Do not try to artificially increase the match score.
10. Return ONLY valid JSON.
11. Do not use markdown.

For every important JD requirement, provide:

- requirement
- category
- match_status
- evidence
- relevant_company
- relevant_role
- relevant_project
- metrics
- recommendation

Use this structure:

{{
    "overall_match": 0,

    "strong_matches": [
        {{
            "requirement": "",
            "category": "",
            "evidence": "",
            "company": "",
            "role": "",
            "project": "",
            "metrics": []
        }}
    ],

    "partial_matches": [
        {{
            "requirement": "",
            "category": "",
            "evidence": "",
            "gap": "",
            "company": "",
            "role": "",
            "metrics": []
        }}
    ],

    "no_evidence": [
        {{
            "requirement": "",
            "category": "",
            "reason": ""
        }}
    ],

    "keyword_matches": [],

    "missing_keywords": [],

    "recommended_resume_keywords": [],

    "recommended_experiences": [],

    "recommended_projects": [],

    "skill_gaps": [],

    "priority_changes": []
}}

MASTER RESUME EVIDENCE:

{json.dumps(resume_data, indent=2, ensure_ascii=False)}

JOB DESCRIPTION ANALYSIS:

{json.dumps(jd_data, indent=2, ensure_ascii=False)}
"""

    result = parse_json_response(generate_with_fallback(
        prompt,
        stage="resume_matching",
        response_validator=_validate_match_response,
        event_sink=event_sink,
    ))
    for field in (
        "strong_matches", "partial_matches", "no_evidence", "keyword_matches",
        "missing_keywords", "recommended_resume_keywords",
        "recommended_experiences", "recommended_projects", "skill_gaps",
        "priority_changes",
    ):
        if not isinstance(result.get(field), list):
            result[field] = []
    result.setdefault("overall_match", 0)
    return verify_match_evidence(result, resume_data, jd_data)


if __name__ == "__main__":

    print("=" * 60)
    print("RESUME ↔ JD MATCHING ENGINE")
    print("=" * 60)

    print("\nLoading master resume evidence...")

    resume_data = load_json(BASE_DIR / "data" / "resume_evidence.json")

    print("Loading JD analysis...")

    jd_data = load_json(BASE_DIR / "data" / "jd_analysis.json")

    print("\nMatching resume evidence against JD...")
    print("This may take a little while...\n")

    parsed = match_resume_to_jd(
        resume_data,
        jd_data
    )
    output_path = BASE_DIR / "data" / "resume_jd_match.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("MATCHING RESULTS")
    print("=" * 60)
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    print("\n" + "=" * 60)
    print("SUCCESS")
    print("Saved to: data/resume_jd_match.json")
    print("=" * 60)