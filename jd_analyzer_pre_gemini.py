import json
import ollama


MODEL = "qwen3:8b"


def analyze_jd(jd_text):

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

    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        options={
            "temperature": 0
        }
    )

    return response["message"]["content"]


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

    result = analyze_jd(jd_text)

    try:

        parsed = json.loads(result)

        with open(
            "data/jd_analysis.json",
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
        print("JD ANALYSIS")
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
        print("Saved to: data/jd_analysis.json")
        print("=" * 60)

    except json.JSONDecodeError:

        print("ERROR: Qwen did not return valid JSON.")
        print("\nRaw response:")
        print(result)