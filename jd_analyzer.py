import json
from pathlib import Path
from gemini_client import generate_with_fallback, parse_json_response

BASE_DIR = Path(__file__).resolve().parent
JD_FIELDS = (
    "responsibilities", "required_skills", "preferred_skills",
    "tools_and_technologies", "domain_keywords", "ats_keywords",
    "behavioral_requirements", "experience_requirements",
    "education_requirements", "important_action_verbs",
    "key_business_outcomes",
)




def _validate_jd_response(response_text):
    try:
        result = parse_json_response(response_text)
    except ValueError:
        return False, "invalid_json"
    if not isinstance(result.get("job_title"), str) or not result["job_title"].strip():
        return False, "missing_job_title"
    if not isinstance(result.get("company", ""), str):
        return False, "invalid_company"
    if any(not isinstance(result.get(field), list) for field in JD_FIELDS):
        return False, "invalid_jd_field"
    return True, "valid"


def analyze_jd(jd_text, event_sink=None):
    if not isinstance(jd_text, str) or not jd_text.strip():
        raise ValueError("Job description text cannot be empty.")

    prompt = f"""
You are an expert Job Description Analysis Engine.

Analyze the following job description for a candidate applying to this role.

Return ONLY valid JSON.

Do NOT invent requirements that are not present in the JD.

Extract:

1. job_title
2. company
3. seniority
4. responsibilities
5. required_skills
6. preferred_skills
7. tools_and_technologies
8. domain_keywords
9. ats_keywords
10. behavioral_requirements
11. experience_requirements
12. education_requirements
13. important_action_verbs
14. key_business_outcomes

For skills and keywords, preserve the terminology used in the JD where possible.

Return this exact structure:

{{
    "job_title": "",
    "company": "",
    "seniority": "",

    "responsibilities": [],

    "required_skills": [],

    "preferred_skills": [],

    "tools_and_technologies": [],

    "domain_keywords": [],

    "ats_keywords": [],

    "behavioral_requirements": [],

    "experience_requirements": [],

    "education_requirements": [],

    "important_action_verbs": [],

    "key_business_outcomes": []
}}

JOB DESCRIPTION:

{jd_text}
"""

    result = parse_json_response(generate_with_fallback(
        prompt,
        stage="jd_analysis",
        response_validator=_validate_jd_response,
        event_sink=event_sink,
    ))
    result.setdefault("job_title", "")
    result.setdefault("company", "")
    result.setdefault("seniority", "")
    for field in JD_FIELDS:
        if not isinstance(result.get(field), list):
            result[field] = []
    return result


if __name__ == "__main__":

    print("=" * 60)
    print("JD ANALYZER")
    print("=" * 60)

    print("\nPaste the complete Job Description.")
    print("When finished, type END on a new line.\n")

    lines = []

    while True:

        line = input()

        if line.strip() == "END":
            break

        lines.append(line)

    jd_text = "\n".join(lines)

    if not jd_text.strip():
        print("No JD provided.")
        exit()

    print("\nAnalyzing JD...")
    print("Please wait...\n")

    parsed = analyze_jd(jd_text)
    output_path = BASE_DIR / "data" / "jd_analysis.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    print("=" * 60)
    print("JD ANALYSIS")
    print("=" * 60)
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    print("\n" + "=" * 60)
    print("SUCCESS")
    print("Saved to: data/jd_analysis.json")
    print("=" * 60)