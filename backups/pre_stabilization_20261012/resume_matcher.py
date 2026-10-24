import json
from pathlib import Path
from gemini_client import generate_with_fallback, parse_json_response

BASE_DIR = Path(__file__).resolve().parent




def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def match_resume_to_jd(resume_data, jd_data):
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

    result = parse_json_response(generate_with_fallback(prompt))
    for field in (
        "strong_matches", "partial_matches", "no_evidence", "keyword_matches",
        "missing_keywords", "recommended_resume_keywords",
        "recommended_experiences", "recommended_projects", "skill_gaps",
        "priority_changes",
    ):
        if not isinstance(result.get(field), list):
            result[field] = []
    result.setdefault("overall_match", 0)
    return result


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