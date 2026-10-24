
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
ROOT = Path(__file__).resolve().parent
MASTER_RESUME = ROOT / "master_resume" / "master_resume.docx"
UPLOAD_DIR = ROOT / "master_resume"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

JD_ANALYZER = ROOT / "jd_analyzer.py"
MATCHER = ROOT / "resume_matcher.py"
GENERATOR = ROOT / "cv_generator.py"
ATS_CHECKER = ROOT / "ats_checker.py"

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
def run_script(script_path):
    """Run an existing project script and show useful errors."""
    if not script_path.exists():
        raise FileNotFoundError(
            f"Required script not found: {script_path.name}"
        )

    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(script_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )

    if result.returncode != 0:
        details = result.stderr or result.stdout
        raise RuntimeError(
            f"{script_path.name} failed.\n\n{details[-6000:]}"
        )

    return result.stdout


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

        st.warning(
            "URL retrieval must be supported by the existing JD analyzer. "
            "If it cannot fetch the page, paste the JD text instead."
        )

        # Do not silently pretend that a URL has been fetched.
        st.error(
            "Automatic URL extraction is not yet connected in this frontend. "
            "Switch to 'Paste job description text' for this first version."
        )
        st.stop()

    if not jd_text.strip():
        st.error("Paste the job description text first.")
        st.stop()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Store the JD where the analyzer can read it only if its expected
    # input contract is known. Avoid overwriting unknown project files.
    st.error(
        "Before running the pipeline, we need to connect the pasted JD "
        "to the exact input expected by jd_analyzer.py. This safety check "
        "prevents the app from using an old JD or producing a misleading CV."
    )
    st.info(
        "The interface is ready for the next integration step. "
        "Your existing scripts have not been modified."
    )


# --------------------------------------------------
# EXISTING OUTPUTS
# --------------------------------------------------
st.divider()
st.subheader("4. Existing outputs")

cv_path = find_latest_cv()
ats_path = OUTPUT_DIR / "ats_report.json"
questions_path = OUTPUT_DIR / "interview_questions.docx"

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
