
import json
import re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib import request as urllib_request

import streamlit as st
from gemini_client import redact_sensitive_text
from pipeline import PipelineError, create_run_id, run_pipeline

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
    request = urllib_request.Request(
        url,
        headers={"User-Agent": "ResumeAgent/1.0 (+job-description retrieval)"},
    )
    with urllib_request.urlopen(request, timeout=20) as response:
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


def execute_application_pack(jd_text, run_id=None):
    run_id = run_id or create_run_id()
    st.session_state.pop("current_stage", None)
    st.session_state.pop("current_stage_detail", None)
    state = {
        "run_id": run_id,
        "status": "running",
        "failed_stage": None,
        "stage_statuses": {},
        "outputs": {},
    }
    st.session_state["current_run"] = state

    def progress(stage, status, detail=""):
        state["stage_statuses"][stage] = status
        st.session_state["current_run"] = state
        stage_name = stage.replace("_", " ").title()
        st.session_state["current_stage"] = f"{stage_name}: {status}"
        if detail:
            st.session_state["current_stage_detail"] = redact_sensitive_text(detail)

    try:
        result = run_pipeline(jd_text, run_id=run_id, progress_callback=progress)
        state.update({
            "status": "completed",
            "stage_statuses": result["stages"],
            "outputs": {name: str(path) for name, path in result["files"].items()},
            "manifest": str(result["manifest"]),
            "ats_report": result["ats_report"],
        })
        st.session_state["current_run"] = state
        st.success(f"Application pack completed for run {run_id}.")
        st.metric("ATS keyword estimate", f"{result['ats_report']['ats_compatibility_score']}/100")
    except PipelineError as exc:
        state.update({
            "status": "failed",
            "failed_stage": exc.stage,
            "outputs": exc.output_files,
            "manifest": str(exc.manifest_path) if exc.manifest_path else "",
        })
        if exc.manifest_path and exc.manifest_path.is_file():
            manifest = load_json(exc.manifest_path)
            state["stage_statuses"] = {
                stage: details.get("status", "pending")
                for stage, details in manifest.get("stages", {}).items()
            }
        st.session_state["current_run"] = state
        st.error(redact_sensitive_text(exc))
    except Exception as exc:
        state.update({"status": "failed", "failed_stage": "application", "error": redact_sensitive_text(exc)})
        st.session_state["current_run"] = state
        st.error(f"Unexpected application error: {redact_sensitive_text(exc)}")
    return state


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
    st.session_state.pop("current_run", None)
    st.session_state.pop("current_stage", None)
    st.session_state.pop("current_stage_detail", None)
    st.session_state["retry_jd_text"] = ""
    run_id = create_run_id()

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
        st.session_state["retry_jd_text"] = jd_text
        with st.spinner("Analyzing the JD and preparing your application pack..."):
            execute_application_pack(jd_text, run_id)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        state = {
            "run_id": run_id,
            "status": "failed",
            "failed_stage": "job_description_retrieval",
            "stage_statuses": {"job_description_retrieval": "failed"},
            "outputs": {},
            "error": redact_sensitive_text(exc),
        }
        st.session_state["current_run"] = state
        st.error(f"Run {run_id} failed while retrieving the JD: {redact_sensitive_text(exc)}")

current_run = st.session_state.get("current_run", {})
if current_run.get("status") == "failed" and st.session_state.get("retry_jd_text"):
    if st.button("Retry failed run", key="retry_failed_run"):
        with st.spinner("Resuming validated stages and retrying the failed stage..."):
            execute_application_pack(
                st.session_state["retry_jd_text"], current_run.get("run_id")
            )


# --------------------------------------------------
# EXISTING OUTPUTS
# --------------------------------------------------
st.divider()
st.subheader("4. Current run outputs")
current_run = st.session_state.get("current_run", {})
if current_run:
    st.caption(f"Run ID: {current_run.get('run_id')} | Status: {current_run.get('status')}")
    if current_run.get("failed_stage"):
        st.warning(f"Failed stage: {current_run['failed_stage']}. Older run outputs are not shown here.")
    elif current_run.get("status") == "running":
        st.info(st.session_state.get("current_stage", "Run in progress"))
    if current_run.get("stage_statuses"):
        status_text = " | ".join(
            f"{stage.replace('_', ' ').title()}: {status}"
            for stage, status in current_run["stage_statuses"].items()
        )
        st.caption(status_text)
    if st.session_state.get("current_stage_detail"):
        st.caption(st.session_state["current_stage_detail"])
else:
    st.info("No application pack has been generated in this session.")

active_outputs = current_run.get("outputs", {})
stage_statuses = current_run.get("stage_statuses", {})
cv_status = stage_statuses.get("cv_document", "unavailable")
interview_status = stage_statuses.get("interview_document", "unavailable")
ats_status = stage_statuses.get("ats_report", "unavailable")
cv_path = Path(active_outputs["cv"]) if active_outputs.get("cv") else None
ats_path = Path(active_outputs["ats_report"]) if active_outputs.get("ats_report") else None
questions_path = Path(active_outputs["interview"]) if active_outputs.get("interview") else None

left, middle, right = st.columns(3)

with left:
    st.markdown(f"**Tailored CV · {cv_status}**")
    safe_download(
        "Download CV (.docx)",
        cv_path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

with middle:
    st.markdown(f"**ATS report · {ats_status}**")
    safe_download(
        "Download ATS report (.json)",
        ats_path,
        "application/json",
    )

with right:
    st.markdown(f"**Interview preparation · {interview_status}**")
    safe_download(
        "Download interview questions (.docx)",
        questions_path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

st.caption(
    "ATS compatibility is a heuristic estimate, not a guaranteed score "
    "from an employer's applicant tracking system."
)
