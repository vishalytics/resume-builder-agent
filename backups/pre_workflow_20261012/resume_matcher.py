import json
from gemini_client import generate_with_fallback




def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def match_resume_to_jd(resume_data, jd_data):

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

    return generate_with_fallback(prompt)


if __name__ == "__main__":

    print("=" * 60)
    print("RESUME ↔ JD MATCHING ENGINE")
    print("=" * 60)

    print("\nLoading master resume evidence...")

    resume_data = load_json(
        "data/resume_evidence.json"
    )

    print("Loading JD analysis...")

    jd_data = load_json(
        "data/jd_analysis.json"
    )

    print("\nMatching resume evidence against JD...")
    print("This may take a little while...\n")

    result = match_resume_to_jd(
        resume_data,
        jd_data
    )

    try:

        parsed = json.loads(result)

        with open(
            "data/resume_jd_match.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                parsed,
                f,
                indent=2,
                ensure_ascii=False
            )

        print("=" * 60)
        print("MATCHING RESULTS")
        print("=" * 60)

        print(
            json.dumps(
                parsed,
                indent=2,
                ensure_ascii=False
            )
        )

        print("\n" + "=" * 60)
        print("SUCCESS")
        print("Saved to: data/resume_jd_match.json")
        print("=" * 60)

    except json.JSONDecodeError:

        print("ERROR: Qwen did not return valid JSON.")

        print("\nRaw response:")
        print(result)