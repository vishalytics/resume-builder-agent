import json
from pathlib import Path
from gemini_client import generate_with_fallback
from docx import Document


# ============================================================
# CONFIG
# ============================================================

# Gemini models are configured in gemini_client.py

RESUME_FILE = "data/resume_evidence.json"
JD_FILE = "data/jd_analysis.json"
MATCH_FILE = "data/resume_jd_match.json"

TEMPLATE_FILE = "templates/CV_TEMPLATE.docx"

OUTPUT_DIR = Path("output")
GENERATED_JSON_FILE = "data/generated_cv.json"

# Gemini retry handling is configured in gemini_client.py
# Gemini timeout/retry handling is configured in gemini_client.py


# ============================================================
# GEMINI CLIENT`r`n# Gemini client is imported from gemini_client.py`r`n


# ============================================================
# LOAD JSON
# ============================================================

def load_json(path):

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# COMPACT DATA
# ============================================================

def compact_resume_data(data):

    """
    Keep only information that is useful for CV generation.
    This prevents sending the entire master resume JSON
    unnecessarily to the local model.
    """

    result = {}

    # Keep common personal fields if available
    for key in [
        "name",
        "email",
        "phone",
        "linkedin",
        "location",
        "contact",
        "personal_information"
    ]:

        if key in data:
            result[key] = data[key]

    # Keep experience
    for key in [
        "experience",
        "work_experience",
        "professional_experience",
        "employment"
    ]:

        if key in data:
            result[key] = data[key]

    # Keep education
    if "education" in data:
        result["education"] = data["education"]

    # Keep skills
    for key in [
        "skills",
        "technical_skills",
        "tools_and_technologies"
    ]:

        if key in data:
            result[key] = data[key]

    # Keep achievements
    for key in [
        "achievements",
        "certifications",
        "projects",
        "leadership"
    ]:

        if key in data:
            result[key] = data[key]

    return result


# ============================================================
# COMPACT JD
# ============================================================

def compact_jd_data(data):

    result = {}

    for key in [
        "job_title",
        "company",
        "domain_keywords",
        "ats_keywords",
        "behavioral_requirements",
        "experience_requirements",
        "education_requirements",
        "important_action_verbs",
        "key_business_outcomes"
    ]:

        if key in data:
            result[key] = data[key]

    return result


# ============================================================
# COMPACT MATCH
# ============================================================

def compact_match_data(data):

    result = {}

    for key in [
        "matches",
        "experience_summary",
        "education_summary",
        "tools_and_technologies",
        "key_strengths",
        "recommendations"
    ]:

        if key in data:
            result[key] = data[key]

    return result


# ============================================================
# VALIDATE GENERATED CV
# ============================================================

def validate_cv(data):

    if not isinstance(data, dict):
        return False, "Response is not a JSON object."

    if not data:
        return False, "Qwen returned {}."

    required = [
        "name",
        "targeted_summary",
        "core_expertise",
        "experience",
        "education"
    ]

    for field in required:

        if field not in data:
            return False, f"Missing field: {field}"

    if not data["name"]:
        return False, "Name is empty."

    if not data["targeted_summary"]:
        return False, "Summary is empty."

    if not isinstance(
        data["experience"],
        list
    ):
        return False, "Experience is not a list."

    return True, "Valid CV."


# ============================================================
# GENERATE CV
# ============================================================

def generate_cv(
    resume_data,
    jd_data,
    match_data
):

    resume = compact_resume_data(
        resume_data
    )

    jd = compact_jd_data(
        jd_data
    )

    match = compact_match_data(
        match_data
    )

    prompt = f"""
You are an expert ATS resume writer.

Create a targeted one-page CV for the candidate.

TARGET ROLE:
{jd.get("job_title", "Target Role")}

IMPORTANT RULES:

- Use ONLY facts from the supplied candidate evidence.
- Never invent companies.
- Never invent roles.
- Never invent dates.
- Never invent metrics.
- Never invent tools.
- Never invent certifications.
- Never invent achievements.
- Rewrite existing achievements to match the JD.
- Use JD keywords naturally when supported by candidate evidence.
- Prioritize quantified achievements.
- Prioritize the strongest JD matches.
- Keep the CV concise.
- Return ONLY valid JSON.
- Do NOT return markdown.
- Do NOT return explanations.
- Do NOT return an empty object.

JOB REQUIREMENTS:

{json.dumps(jd, ensure_ascii=False)}

RESUME-JD MATCH:

{json.dumps(match, ensure_ascii=False)}

CANDIDATE EVIDENCE:

{json.dumps(resume, ensure_ascii=False)}

Return exactly this structure:

{{
  "name": "",
  "email": "",
  "phone": "",
  "linkedin": "",
  "location": "",

  "targeted_summary": "",

  "core_expertise": [],

  "tools_and_technologies": [],

  "experience": [
    {{
      "company": "",
      "role": "",
      "dates": "",
      "bullets": []
    }}
  ],

  "projects": [
    {{
      "name": "",
      "tools": "",
      "description": ""
    }}
  ],

  "achievements": [],

  "certifications": [],

  "education": {{
    "mba_degree": "",
    "mba_institution": "",
    "mba_duration": "",
    "mba_score": "",
    "btech_degree": "",
    "btech_institution": "",
    "btech_duration": "",
    "btech_score": ""
  }}
}}

Experience bullets should be concise, achievement-oriented and
tailored to the target JD.

Use the candidate's actual numbers whenever available.

Return ONLY the JSON.
"""

    print("\nSending request to Gemini...")
    result = generate_with_fallback(prompt)
    print("\nGemini response received.")
    print("Response length:", len(result))

    try:
        data = json.loads(result)

    except json.JSONDecodeError:

        print("\nGemini returned invalid JSON:")
        print(result)

        raise ValueError(
            "Invalid JSON returned by Gemini."
        )

    valid, message = validate_cv(data)

    if not valid:

        print("\nCV validation failed:")
        print(message)

        print("\nGemini returned:")
        print(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            )
        )

        raise ValueError(message)

    return data


# ============================================================
# PLACEHOLDER REPLACEMENT
# ============================================================

def replace_in_paragraph(
    paragraph,
    replacements
):

    text = paragraph.text

    new_text = text

    for placeholder, value in replacements.items():

        new_text = new_text.replace(
            placeholder,
            str(value)
        )

    if new_text != text:

        paragraph.text = new_text


def replace_in_document(
    doc,
    replacements
):

    for paragraph in doc.paragraphs:

        replace_in_paragraph(
            paragraph,
            replacements
        )

    for table in doc.tables:

        for row in table.rows:

            for cell in row.cells:

                for paragraph in cell.paragraphs:

                    replace_in_paragraph(
                        paragraph,
                        replacements
                    )


# ============================================================
# BUILD PLACEHOLDERS
# ============================================================

def build_replacements(cv):

    replacements = {}

    # Basic information
    replacements["{{NAME}}"] = cv.get(
        "name", ""
    )

    replacements["{{EMAIL}}"] = cv.get(
        "email", ""
    )

    replacements["{{PHONE}}"] = cv.get(
        "phone", ""
    )

    replacements["{{LINKEDIN}}"] = cv.get(
        "linkedin", ""
    )

    replacements["{{LOCATION}}"] = cv.get(
        "location", ""
    )

    # Summary
    replacements["{{TARGETED_SUMMARY}}"] = cv.get(
        "targeted_summary", ""
    )

    # Skills
    replacements["{{CORE_EXPERTISE}}"] = " | ".join(
        cv.get(
            "core_expertise",
            []
        )
    )

    replacements["{{TOOLS_AND_TECHNOLOGIES}}"] = " | ".join(
        cv.get(
            "tools_and_technologies",
            []
        )
    )

    # Experience
    experiences = cv.get(
        "experience",
        []
    )

    for i in range(1, 5):

        prefix = f"{{{{EXPERIENCE_{i}"

        if i <= len(experiences):

            exp = experiences[i - 1]

            replacements[
                prefix + "_COMPANY}}"
            ] = exp.get(
                "company",
                ""
            )

            replacements[
                prefix + "_ROLE}}"
            ] = exp.get(
                "role",
                ""
            )

            replacements[
                prefix + "_DATES}}"
            ] = exp.get(
                "dates",
                ""
            )

            bullets = exp.get(
                "bullets",
                []
            )

            for b in range(1, 8):

                placeholder = (
                    prefix
                    + f"_BULLET_{b}}}"
                )

                if b <= len(bullets):

                    replacements[
                        placeholder
                    ] = bullets[b - 1]

                else:

                    replacements[
                        placeholder
                    ] = ""

        else:

            replacements[
                prefix + "_COMPANY}}"
            ] = ""

            replacements[
                prefix + "_ROLE}}"
            ] = ""

            replacements[
                prefix + "_DATES}}"
            ] = ""

            for b in range(1, 8):

                replacements[
                    prefix
                    + f"_BULLET_{b}}}"
                ] = ""

    # Projects
    projects = cv.get(
        "projects",
        []
    )

    for i in range(1, 4):

        if i <= len(projects):

            project = projects[i - 1]

            replacements[
                f"{{{{PROJECT_{i}_NAME}}}}"
            ] = project.get(
                "name",
                ""
            )

            replacements[
                f"{{{{PROJECT_{i}_TOOLS}}}}"
            ] = project.get(
                "tools",
                ""
            )

            replacements[
                f"{{{{PROJECT_{i}_DESCRIPTION}}}}"
            ] = project.get(
                "description",
                ""
            )

        else:

            replacements[
                f"{{{{PROJECT_{i}_NAME}}}}"
            ] = ""

            replacements[
                f"{{{{PROJECT_{i}_TOOLS}}}}"
            ] = ""

            replacements[
                f"{{{{PROJECT_{i}_DESCRIPTION}}}}"
            ] = ""

    # Achievements
    achievements = cv.get(
        "achievements",
        []
    )

    for i in range(1, 5):

        replacements[
            f"{{{{ACHIEVEMENT_{i}}}}}"
        ] = (
            achievements[i - 1]
            if i <= len(achievements)
            else ""
        )

    # Certifications
    certifications = cv.get(
        "certifications",
        []
    )

    for i in range(1, 5):

        replacements[
            f"{{{{CERTIFICATION_{i}}}}}"
        ] = (
            certifications[i - 1]
            if i <= len(certifications)
            else ""
        )

    # Education
    education = cv.get(
        "education",
        {}
    )

    replacements[
        "{{MBA_DEGREE}}"
    ] = education.get(
        "mba_degree",
        ""
    )

    replacements[
        "{{MBA_INSTITUTION}}"
    ] = education.get(
        "mba_institution",
        ""
    )

    replacements[
        "{{MBA_DURATION}}"
    ] = education.get(
        "mba_duration",
        ""
    )

    replacements[
        "{{MBA_SCORE}}"
    ] = education.get(
        "mba_score",
        ""
    )

    replacements[
        "{{BTECH_DEGREE}}"
    ] = education.get(
        "btech_degree",
        ""
    )

    replacements[
        "{{BTECH_INSTITUTION}}"
    ] = education.get(
        "btech_institution",
        ""
    )

    replacements[
        "{{BTECH_DURATION}}"
    ] = education.get(
        "btech_duration",
        ""
    )

    replacements[
        "{{BTECH_SCORE}}"
    ] = education.get(
        "btech_score",
        ""
    )

    return replacements


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 65)
    print("TAILORED CV GENERATOR")
    print("=" * 65)

    print("\nLoading resume evidence...")

    resume_data = load_json(
        RESUME_FILE
    )

    print("Loading JD analysis...")

    jd_data = load_json(
        JD_FILE
    )

    print("Loading resume-JD matching...")

    match_data = load_json(
        MATCH_FILE
    )

    print("\nGenerating tailored CV...")
    print(
        "Using compact prompt for local Qwen3:8b."
    )

    try:

        cv_data = generate_cv(
            resume_data,
            jd_data,
            match_data
        )

    except Exception as e:

        print("\nERROR:")
        print(str(e))

        print(
            "\nThe CV was NOT created."
        )

        exit(1)

    # Save JSON
    with open(
        GENERATED_JSON_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            cv_data,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        "\nSaved generated CV data to:"
    )

    print(
        GENERATED_JSON_FILE
    )

    # Load template
    print(
        "\nLoading Word template..."
    )

    doc = Document(
        TEMPLATE_FILE
    )

    # Replace placeholders
    replacements = build_replacements(
        cv_data
    )

    print(
        "Replacing template placeholders..."
    )

    replace_in_document(
        doc,
        replacements
    )

    # Create output directory
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # Filename
    job_title = jd_data.get(
        "job_title",
        "Tailored_CV"
    )

    safe_title = (
        str(job_title)
        .replace("/", "-")
        .replace("\\", "-")
        .replace(" ", "_")
    )

    output_path = (
        OUTPUT_DIR
        / f"Vishal_Kumar_{safe_title}_CV.docx"
    )

    # Save
    doc.save(
        output_path
    )

    print("\n" + "=" * 65)
    print("SUCCESS")
    print("=" * 65)

    print(
        "\nCV saved to:"
    )

    print(
        output_path
    )

    print(
        "\nGenerated JSON:"
    )

    print(
        GENERATED_JSON_FILE
    )

    print("=" * 65)


