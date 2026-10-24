import json
import re
from pathlib import Path

from ats_checker import build_ats_report
from cv_generator import generate_cv, render_cv_document
from interview_prep import generate_interview_document
from jd_analyzer import analyze_jd
from resume_matcher import match_resume_to_jd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"


def _load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(value, file, indent=2, ensure_ascii=False)
    temporary_path.replace(path)


def _slug(value, fallback):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_") or fallback


def run_pipeline(jd_text):
    if not isinstance(jd_text, str) or not jd_text.strip():
        raise ValueError("Enter a job description before generating an application pack.")

    resume_data = _load_json(DATA_DIR / "resume_evidence.json")
    jd_data = analyze_jd(jd_text)
    match_data = match_resume_to_jd(resume_data, jd_data)
    cv_data = generate_cv(resume_data, jd_data, match_data)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cv_path = render_cv_document(cv_data, jd_data, OUTPUT_DIR)
    report = build_ats_report(jd_data, match_data, cv_data)

    candidate = _slug(cv_data.get("name"), "Candidate")
    role = _slug(jd_data.get("job_title"), "Target_Role")
    interview_path = OUTPUT_DIR / f"{candidate}_{role}_Interview_Preparation.docx"
    generate_interview_document(resume_data, jd_data, match_data, interview_path)
    report_path = OUTPUT_DIR / "ats_report.json"

    _write_json(DATA_DIR / "jd_analysis.json", jd_data)
    _write_json(DATA_DIR / "resume_jd_match.json", match_data)
    _write_json(DATA_DIR / "generated_cv.json", cv_data)
    _write_json(report_path, report)

    return {
        "jd_analysis": jd_data,
        "resume_match": match_data,
        "generated_cv": cv_data,
        "ats_report": report,
        "files": {
            "cv": cv_path,
            "interview": interview_path,
            "ats_report": report_path,
        },
    }