
import json
import re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st
from gemini_client import redact_sensitive_text
from pipeline import run_pipeline

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
ROOT = Path(__file__).resolve().parent
MASTER_RESUME = ROOT / "master_resume" / "master_resume.docx"
UPLOAD_DIR = ROOT / "master_resume"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

st.set_page_config(
    page_title="Resume Agent",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Resume Agent")
st.caption(
    "Paste a job description or URL to generate a tailored CV, "
    "ATS compatibility report, and interview preparation."
)


# --------------------------------------------------
# HELPERS
# --------------------------------------------------
class JobPageTextParser(HTMLParser):
    """Extract readable text while ignoring scripts and page styling."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1
        elif not self.skip_depth and tag in {"p", "br", "div", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in {"p", "div", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def fetch_job_description(url):
    request = Request(
        url,
        headers={"User-Agent": "ResumeAgent/1.0 (+job-description retrieval)"},
    )
    with urlopen(request, timeout=20) as response:
        body = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    html = body.decode(charset, errors="replace")
    parser = JobPageTextParser()
    parser.feed(html)
    text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) < 80:
        raise ValueError("The page did not contain enough readable job-description text.")
    return text


def find_master_resume():
    """Prefer the existing master resume."""
    if MASTER_RESUME.is_file() and MASTER_RESUME.stat().st_size > 0:
        return MASTER_RESUME
    return None


def save_uploaded_resume(upload):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = MASTER_RESUME
    destination.write_bytes(upload.getvalue())
    return destination


def get_jd_details():
    path = DATA_DIR / "jd_analysis.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def find_latest_cv():
    files = list(OUTPUT_DIR.glob("*_CV.docx"))
    if not files:
        files = list(OUTPUT_DIR.glob("*.docx"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def find_latest_interview_document():
    files = list(OUTPUT_DIR.glob("*_Interview_Preparation.docx"))
    if not files:
        legacy = OUTPUT_DIR / "interview_questions.docx"
        return legacy if legacy.is_file() else None
    return max(files, key=lambda p: p.stat().st_mtime)


def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def safe_download(label, path, mime):
    if path and path.exists():
        st.download_button(
            label=label,
            data=path.read_bytes(),
            file_name=path.name,
            mime=mime,
            use_container_width=True,
        )
    else:
        st.info(f"Not available yet: {label}")


# --------------------------------------------------
# MASTER RESUME
# --------------------------------------------------
st.subheader("1. Master resume")

master = find_master_resume()

if master:
    st.success(f"Master resume detected: {master.relative_to(ROOT)}")
    st.caption("The existing master resume will be used automatically.")
else:
    st.warning("The master resume is missing. Upload your .docx file.")
    uploaded = st.file_uploader(
        "Upload master resume",
        type=["docx"],
        key="master_resume_upload",
    )
    if uploaded:
        if st.button("Save master resume", type="primary"):
            try:
                save_uploaded_resume(uploaded)
                st.success("Master resume saved.")
                st.rerun()
            except OSError as exc:
                st.error(f"Could not save the resume: {exc}")


# --------------------------------------------------
# JOB DESCRIPTION INPUT
# --------------------------------------------------
st.subheader("2. Job description")

input_mode = st.radio(
    "Choose how to provide the JD",
    ["Paste job description URL", "Paste job description text"],
    horizontal=True,
)

jd_url = ""
jd_text = ""

if input_mode == "Paste job description URL":
    jd_url = st.text_input(
        "Job description URL",
        placeholder="https://company.com/careers/job",
    )
    st.caption(
        "The agent will try to retrieve the public job page. "
        "Login-protected or blocked pages may require pasted text."
    )
else:
    jd_text = st.text_area(
        "Paste the complete job description",
        height=260,
        placeholder="Paste the job description here...",
    )


# --------------------------------------------------
# PIPELINE
# --------------------------------------------------
st.subheader("3. Generate application pack")

st.caption(
    "The job title and company will be extracted automatically where "
    "the existing JD analyzer supports them."
)

if st.button("🚀 Generate Application Pack", type="primary",
             use_container_width=True):

    master = find_master_resume()

    if not master:
        st.error("Please upload and save your master resume first.")
        st.stop()

    if input_mode == "Paste job description URL":
        if not jd_url.strip():
            st.error("Paste a job description URL first.")
            st.stop()

        parsed = urlparse(jd_url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            st.error("Enter a valid URL beginning with http:// or https://.")
            st.stop()

    if input_mode == "Paste job description text" and not jd_text.strip():
        st.error("Paste the job description text first.")
        st.stop()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if input_mode == "Paste job description URL":
            jd_text = fetch_job_description(jd_url.strip())
        with st.spinner("Analyzing the job description and preparing your application pack..."):
            result = run_pipeline(jd_text)
        st.session_state["generated_outputs"] = {
            key: str(path) for key, path in result["files"].items()
        }
        st.session_state["generated_ats_report"] = result["ats_report"]
        st.success("Application pack generated successfully.")
        st.metric(
            "ATS keyword estimate",
            f"{result['ats_report']['ats_compatibility_score']}/100",
        )
    except (HTTPError, URLError, TimeoutError, ValueError, OSError, RuntimeError) as exc:
        st.error(
            "The application pack could not be generated: "
            f"{redact_sensitive_text(exc)}"
        )
    except Exception as exc:
        st.error(f"Unexpected pipeline error: {redact_sensitive_text(exc)}")


# --------------------------------------------------
# EXISTING OUTPUTS
# --------------------------------------------------
st.divider()
st.subheader("4. Existing outputs")

active_outputs = st.session_state.get("generated_outputs", {})
cv_path = Path(active_outputs["cv"]) if active_outputs.get("cv") else find_latest_cv()
ats_path = OUTPUT_DIR / "ats_report.json"
questions_path = (
    Path(active_outputs["interview"])
    if active_outputs.get("interview")
    else find_latest_interview_document()
)

left, middle, right = st.columns(3)

with left:
    st.markdown("**Tailored CV**")
    safe_download(
        "Download CV (.docx)",
        cv_path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

with middle:
    st.markdown("**ATS report**")
    safe_download(
        "Download ATS report (.json)",
        ats_path,
        "application/json",
    )

with right:
    st.markdown("**Interview preparation**")
    safe_download(
        "Download interview questions (.docx)",
        questions_path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

st.caption(
    "ATS compatibility is a heuristic estimate, not a guaranteed score "
    "from an employer's applicant tracking system."
)
