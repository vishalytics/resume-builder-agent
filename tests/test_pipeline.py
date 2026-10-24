import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

import pipeline
from ats_checker import build_ats_report


def resume_fixture():
    roles = [
        ("Nutrabay Retail Pvt. Ltd.", "Associate - Founder's Office", "Jul 2025 - Present", "Reduced manual coordination by 90%"),
        ("Dakshana India Educational Trust Fund", "Program Manager", "Oct 2018 - May 2023", "Reduced operating costs by 20%"),
        ("MokkoMotto Electronics Pvt. Ltd.", "Founder's Office Intern", "Sep 2024 - Apr 2025", "Secured INR 18L+ in orders"),
        ("1-Cliq", "Business Strategy Intern", "Apr 2024 - May 2024", "Onboarded 20+ vendors"),
    ]
    return {
        "candidate": {
            "name": "Test Candidate", "email": "test@example.invalid",
            "phone": "0000000000", "linkedin": "linkedin.example/test",
            "location": "Remote",
        },
        "summary": "Strategy and operations professional with verified experience.",
        "education": [
            {"degree": "MBA", "institution": "Example Institute", "cgpa": "8.00", "duration": "2023-2025"},
            {"degree": "B.Tech.", "institution": "Example University", "cgpa": "7.00", "duration": "2014-2018"},
        ],
        "experience": [
            {
                "company": company,
                "role": role,
                "duration": dates,
                "achievements": [{"evidence": achievement, "achievement": achievement, "metrics": [achievement]}],
                "skills": ["Program Management", "Analytics", "Excel"],
            }
            for company, role, dates, achievement in roles
        ],
        "achievements": [{"name": "Excellence Award", "description": "Recognized for verified work."}],
        "certifications": [{"name": "Analytics Certificate", "provider": "Example Academy"}],
        "leadership": [{"role": "Team Lead", "institution": "Example Organization", "duration": "2020-2022"}],
    }


def jd_fixture(title="Operations Analyst"):
    return {
        "job_title": title, "company": "Example Employer", "seniority": "Mid-level",
        "responsibilities": ["Build reports"], "required_skills": ["Analytics"],
        "preferred_skills": [], "tools_and_technologies": [], "domain_keywords": [],
        "ats_keywords": [], "behavioral_requirements": [], "experience_requirements": [],
        "education_requirements": [], "important_action_verbs": [], "key_business_outcomes": [],
    }


def match_fixture():
    return {
        "overall_match": 75, "strong_matches": [], "partial_matches": [],
        "no_evidence": [{"requirement": "Financial modeling", "reason": "Not documented."}],
        "keyword_matches": [], "missing_keywords": [], "recommended_resume_keywords": [],
        "recommended_experiences": [], "recommended_projects": [], "skill_gaps": [],
        "priority_changes": [],
    }


def cv_fixture():
    return {
        "name": "Test Candidate", "email": "wrong@example.invalid", "phone": "111",
        "linkedin": "wrong.example", "location": "Wrong location",
        "targeted_headline": "Operations Analyst", "targeted_summary": "Operations leader with 999% growth.",
        "core_expertise": ["Program Management", "Advanced Financial Modeling"],
        "tools_and_technologies": ["Analytics: Excel, UnsupportedDB"],
        "experience": [
            {"company": "Wrong company", "role": "Wrong role", "dates": "wrong dates", "bullets": ["Reduced manual coordination by 90%", "Delivered 999% improvement"]}
        ],
        "education": {}, "achievements": [], "certifications": [], "leadership": [],
    }


def interview_fixture():
    return {
        "questions": [
            {
                "question": f"Question {index}",
                "category": "analytical_case" if index == 1 else "behavioral",
                "answer_points": ["Evidence-backed answer point"],
                "follow_up_questions": ["What changed?"],
                "evidence_indices": [0],
            }
            for index in range(1, 5)
        ],
        "experience_gaps": [{"requirement": "Financial modeling", "reason": "Not documented."}],
    }


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.data_dir = root / "data"
        self.output_dir = root / "output"
        self.data_dir.mkdir()
        (self.data_dir / "resume_evidence.json").write_text(
            json.dumps(resume_fixture()), encoding="utf-8"
        )
        self.patches = [
            patch.object(pipeline, "DATA_DIR", self.data_dir),
            patch.object(pipeline, "OUTPUT_DIR", self.output_dir),
            patch.object(pipeline, "analyze_jd", side_effect=lambda text, **kwargs: jd_fixture()),
            patch.object(pipeline, "match_resume_to_jd", side_effect=lambda *args, **kwargs: match_fixture()),
            patch.object(pipeline, "generate_cv", side_effect=lambda *args, **kwargs: cv_fixture()),
            patch.object(pipeline, "build_interview_questions", side_effect=lambda *args, **kwargs: interview_fixture()),
            patch.object(pipeline, "_read_master_resume_text", return_value=json.dumps(resume_fixture())),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def test_complete_mocked_pipeline_writes_three_isolated_outputs(self):
        result = pipeline.run_pipeline("JD for operations analyst")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["files"]), 3)
        self.assertTrue(all(Path(path).is_file() for path in result["files"].values()))
        self.assertTrue(all(Path(path).parent == self.output_dir / "runs" / result["run_id"] for path in result["files"].values()))
        manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["stages"]["jd_analysis"]["status"], "fresh")
        self.assertEqual(result["generated_cv"]["email"], "test@example.invalid")
        self.assertEqual(result["generated_cv"]["targeted_summary"], resume_fixture()["summary"])
        self.assertEqual(result["generated_cv"]["phone"], "0000000000")
        self.assertEqual(result["generated_cv"]["linkedin"], "linkedin.example/test")
        self.assertEqual(len(result["generated_cv"]["experience"]), 4)
        self.assertEqual(result["generated_cv"]["experience"][0]["company"], "Nutrabay Retail Pvt. Ltd.")
        self.assertEqual(result["generated_cv"]["experience"][0]["dates"], "Jul 2025 - Present")
        self.assertEqual(result["generated_cv"]["experience"][0]["bullets"], ["Reduced manual coordination by 90%"])
        self.assertEqual(result["generated_cv"]["education"]["mba_institution"], "Example Institute")
        self.assertEqual(result["generated_cv"]["certifications"], ["Analytics Certificate"])
        self.assertEqual(result["generated_cv"]["achievements"], ["Excellence Award - Recognized for verified work."])
        self.assertEqual(result["generated_cv"]["core_expertise"], ["Program Management"])
        self.assertEqual(result["generated_cv"]["tools_and_technologies"], ["Analytics: Excel"])
        report = result["ats_report"]
        self.assertTrue(report["optimization"]["score_from_selected_docx"])
        self.assertEqual(report["optimization"]["selected_docx_score"], report["ats_compatibility_score"])
        self.assertTrue(report["optimization"]["target_score"] >= 90)
        self.assertIn(report["optimization"]["stop_reason"], {
            "target_reached", "evidence_insufficient", "two_consecutive_non_improving_iterations",
            "maximum_iterations", "quality_check_failed",
        })
        optimization_artifact = result["manifest"].parent / "ats_optimization.json"
        self.assertTrue(optimization_artifact.is_file())
        self.assertEqual(result["stages"]["ats_optimization"], "fresh")
        rerun_report = build_ats_report(
            result["jd_analysis"], result["resume_match"], result["generated_cv"],
            resume_fixture(),
            document_text=pipeline._read_docx_text(result["files"]["cv"]),
            document_integrity={"checked": True, "valid": True, "source": "selected_docx"},
        )
        self.assertEqual(rerun_report["ats_compatibility_score"], report["ats_compatibility_score"])

    def test_new_job_runs_get_distinct_ids_and_artifact_directories(self):
        first = pipeline.run_pipeline("JD one")
        second = pipeline.run_pipeline("JD two")
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertNotEqual(first["files"]["cv"], second["files"]["cv"])

    def test_failed_cv_stage_can_resume_without_repeating_jd_or_match(self):
        jd_calls = []
        match_calls = []
        generation_calls = []
        self.patches[2].stop()
        self.patches[3].stop()
        self.patches[4].stop()
        self.patches[2] = patch.object(
            pipeline, "analyze_jd", side_effect=lambda *args, **kwargs: jd_calls.append(1) or jd_fixture()
        )
        self.patches[3] = patch.object(
            pipeline, "match_resume_to_jd", side_effect=lambda *args, **kwargs: match_calls.append(1) or match_fixture()
        )

        def generate(*args, **kwargs):
            generation_calls.append(1)
            if len(generation_calls) == 1:
                raise RuntimeError("synthetic CV-stage failure")
            return cv_fixture()

        self.patches[4] = patch.object(pipeline, "generate_cv", side_effect=generate)
        for item in self.patches[2:5]:
            item.start()
        with self.assertRaises(pipeline.PipelineError) as caught:
            pipeline.run_pipeline("same JD across retry", run_id="retry-run")
        self.assertEqual(caught.exception.stage, "cv_generation")
        self.assertFalse(caught.exception.output_files)
        result = pipeline.run_pipeline("same JD across retry", run_id="retry-run")
        self.assertEqual(result["status"], "completed")
        self.assertEqual((len(jd_calls), len(match_calls), len(generation_calls)), (1, 1, 2))
        self.assertEqual(result["stages"]["jd_analysis"], "reused")
        self.assertEqual(result["stages"]["resume_matching"], "reused")

    def test_run_id_cannot_be_reused_for_different_inputs(self):
        pipeline.run_pipeline("first JD", run_id="fixed-run")
        with self.assertRaises(pipeline.PipelineError) as caught:
            pipeline.run_pipeline("different JD", run_id="fixed-run")
        self.assertEqual(caught.exception.stage, "input_validation")

    def test_corrupt_cached_cv_is_rerendered_without_repeating_model_stages(self):
        first = pipeline.run_pipeline("cache validation JD", run_id="docx-cache-run")
        first["files"]["cv"].write_bytes(b"corrupt DOCX")
        second = pipeline.run_pipeline("cache validation JD", run_id="docx-cache-run")
        self.assertEqual(second["stages"]["jd_analysis"], "reused")
        self.assertEqual(second["stages"]["resume_matching"], "reused")
        self.assertEqual(second["stages"]["cv_generation"], "reused")
        self.assertEqual(second["stages"]["cv_document"], "fresh")
        self.assertIn("PROFESSIONAL EXPERIENCE", "\n".join(
            paragraph.text for paragraph in Document(second["files"]["cv"]).paragraphs
        ))

    def test_interview_failure_preserves_current_run_best_cv_and_ats_report(self):
        self.patches[5].stop()
        self.patches[5] = patch.object(
            pipeline,
            "build_interview_questions",
            side_effect=RuntimeError("synthetic interview quota failure"),
        )
        self.patches[5].start()
        with self.assertRaises(pipeline.PipelineError) as caught:
            pipeline.run_pipeline("interview-failure JD", run_id="interview-failure-run")
        self.assertEqual(caught.exception.stage, "interview_preparation")
        self.assertEqual(set(caught.exception.output_files), {"cv", "ats_report"})
        manifest = json.loads(caught.exception.manifest_path.read_text(encoding="utf-8"))
        report_path = Path(caught.exception.output_files["ats_report"])
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["run_id"], "interview-failure-run")
        self.assertEqual(manifest["stages"]["cv_document"]["status"], "fresh")
        self.assertEqual(manifest["stages"]["ats_report"]["status"], "fresh")
        self.assertEqual(manifest["stages"]["interview_preparation"]["status"], "failed")

if __name__ == "__main__":
    unittest.main()