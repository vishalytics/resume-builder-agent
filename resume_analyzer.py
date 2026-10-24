import json
import ollama
from resume_parser import extract_resume_text


MODEL = "qwen3:8b"


def analyze_resume(resume_text):
    prompt = f"""
You are a professional resume data extraction engine.

Your task is to convert the candidate's master resume into a structured
career evidence database.

IMPORTANT RULES:

1. Use ONLY information explicitly present in the resume.
2. NEVER invent companies, responsibilities, skills, metrics, tools,
   achievements, education, certifications or projects.
3. Preserve numbers and metrics exactly as stated.
4. Separate responsibilities from measurable achievements.
5. Capture the evidence behind every important achievement.
6. If information is not present, do not create it.
7. Return ONLY valid JSON.
8. Do not use markdown.
9. Do not add explanations outside the JSON.

Use this structure:

{{
  "candidate": {{
    "name": "",
    "location": "",
    "email": "",
    "phone": "",
    "linkedin": ""
  }},

  "summary": "",

  "education": [],

  "experience": [
    {{
      "company": "",
      "role": "",
      "duration": "",
      "responsibilities": [],
      "achievements": [
        {{
          "achievement": "",
          "metrics": [],
          "evidence": ""
        }}
      ],
      "skills": [],
      "tools": [],
      "projects": []
    }}
  ],

  "projects": [
    {{
      "name": "",
      "description": "",
      "skills": [],
      "tools": [],
      "metrics": [],
      "evidence": ""
    }}
  ],

  "skills": [],

  "tools": [],

  "certifications": [],

  "leadership": [],

  "achievements": []
}}

MASTER RESUME:

{resume_text}
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

    print("Reading master resume...")

    resume_text = extract_resume_text()

    print(f"Resume characters: {len(resume_text)}")

    print("\nAnalyzing resume with Qwen...")
    print("This may take a little while...\n")

    result = analyze_resume(resume_text)

    print("\n" + "=" * 60)
    print("RESUME ANALYSIS")
    print("=" * 60)

    print(result)

    # Try to save the response
    try:
        parsed = json.loads(result)
        # Preserve contact details directly from the master resume.
        import re

        candidate = parsed.setdefault("candidate", {})

        email_match = re.search(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            resume_text
        )

        phone_match = re.search(
            r"(?:\+91[\s-]?)?[6-9]\d{9}",
            resume_text
        )

        linkedin_match = re.search(
            r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+",
            resume_text,
            re.IGNORECASE
        )

        if email_match:
            candidate["email"] = email_match.group(0)

        if phone_match:
            candidate["phone"] = phone_match.group(0)

        if linkedin_match:
            candidate["LinkedIn"] = linkedin_match.group(0)

        candidate["name"] = "VISHAL KUMAR"
        candidate["location"] = "Delhi NCR"

        with open(
            "data/resume_evidence.json",
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                parsed,
                f,
                indent=2,
                ensure_ascii=False
            )

        print("\n" + "=" * 60)
        print("SUCCESS")
        print("Saved to: data/resume_evidence.json")
        print("=" * 60)

    except json.JSONDecodeError:
        print("\nWARNING:")
        print("Qwen did not return valid JSON.")
        print("We will fix this if it happens.")