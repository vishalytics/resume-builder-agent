import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from pipeline import PipelineError
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


class ResumeAgentAppTests(unittest.TestCase):
    def test_hides_old_outputs_until_current_run_is_available(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("download_button")), 0)
        self.assertTrue(any("No application pack" in element.value for element in app.info))

    def test_current_run_renders_all_three_downloads(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = {
                "cv": root / "current_CV.docx",
                "interview": root / "current_Interview.docx",
                "ats_report": root / "current_ats.json",
            }
            for path in paths.values():
                path.write_bytes(b"current-run fixture")
            app.session_state["current_run"] = {
                "run_id": "active-test-run",
                "status": "completed",
                "failed_stage": None,
                "stage_statuses": {
                    "cv_document": "fresh", "interview_document": "fresh", "ats_report": "fresh",
                },
                "outputs": {key: str(value) for key, value in paths.items()},
            }
            app.run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get("download_button")), 3)

    def test_text_submission_runs_pipeline_and_exposes_successful_outputs(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        app.radio[0].set_value("Paste job description text").run(timeout=30)
        app.text_area[0].set_value("Operations analyst role responsible for dashboards and process improvement.").run(timeout=30)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = {
                "cv": root / "test_CV.docx",
                "interview": root / "test_Interview.docx",
                "ats_report": root / "test_ats.json",
            }
            for path in paths.values():
                path.write_bytes(b"fresh mocked output")
            result = {
                "run_id": "mocked-success-run",
                "status": "completed",
                "stages": {"cv_document": "fresh", "interview_document": "fresh", "ats_report": "fresh"},
                "files": paths,
                "manifest": root / "manifest.json",
                "ats_report": {"ats_compatibility_score": 42},
                "optimization": {
                    "initial_score": 35,
                    "final_score": 42,
                    "target_score": 90,
                    "target_reached": False,
                    "iterations_completed": 1,
                    "maximum_iterations": 3,
                    "stop_reason": "evidence_insufficient",
                    "history": [{"iteration": 1, "improvements": []}],
                    "remaining_missing_requirements": [{
                        "keyword": "Financial modeling",
                        "category": "Required skills",
                        "evidence_status": "partial_evidence_only",
                    }],
                },
            }
            with patch("pipeline.create_run_id", return_value="mocked-success-run"), patch(
                "pipeline.run_pipeline", return_value=result
            ) as runner:
                app.button[0].click().run(timeout=30)
            runner.assert_called_once()
            self.assertEqual(runner.call_args.args[0], "Operations analyst role responsible for dashboards and process improvement.")
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get("download_button")), 3)
            self.assertEqual(app.session_state["current_run"]["run_id"], "mocked-success-run")
            self.assertEqual(app.session_state["current_run"]["status"], "completed")
            self.assertEqual(app.session_state["current_run"]["optimization"]["initial_score"], 35)
            self.assertTrue(any("ATS optimization" in element.value for element in app.markdown))
            self.assertTrue(any("Remaining gaps" in element.value for element in app.markdown))

    def test_failed_pipeline_does_not_show_previous_run_outputs(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        app.radio[0].set_value("Paste job description text").run(timeout=30)
        app.text_area[0].set_value("A realistic test job description for an operations analyst.").run(timeout=30)

        def fail(*args, **kwargs):
            raise PipelineError(kwargs["run_id"], "cv_generation", "daily quota exhausted")

        with patch("pipeline.run_pipeline", side_effect=fail):
            app.button[0].click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("download_button")), 0)
        self.assertTrue(any("failed during cv_generation" in element.value for element in app.error))
        self.assertTrue(any(button.key == "retry_failed_run" for button in app.button))

    def test_inaccessible_job_url_is_reported_without_stale_downloads(self):
        app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        app.text_input[0].set_value("https://example.invalid/job").run(timeout=30)
        with patch("urllib.request.urlopen", side_effect=URLError("blocked")):
            app.button[0].click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("download_button")), 0)
        self.assertTrue(any("failed while retrieving the JD" in element.value for element in app.error))
        self.assertEqual(app.session_state["current_run"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()