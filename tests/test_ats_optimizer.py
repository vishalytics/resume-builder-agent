import unittest

from ats_checker import build_ats_report, cv_display_text
from ats_optimizer import (
    MAX_OPTIMIZATION_ITERATIONS,
    OPTIMIZER_CONFIG,
    TARGET_ATS_SCORE,
    optimize_cv,
)


def resume_with_evidence(bullets):
    return {
        "experience": [{
            "company": "Example Co",
            "role": "Operations Analyst",
            "skills": ["Power BI"],
            "achievements": [{"evidence": bullet, "achievement": bullet} for bullet in bullets],
        }],
    }


def cv_with_bullets(bullets):
    return {
        "name": "Candidate", "targeted_headline": "Operations Analyst",
        "targeted_summary": "Operations professional.", "core_expertise": ["Operations"],
        "tools_and_technologies": [],
        "experience": [{"company": "Example Co", "role": "Operations Analyst", "dates": "2020-2024", "bullets": list(bullets)}],
        "education": {}, "achievements": [], "certifications": [], "leadership": [],
    }


def report_for(score, missing=None, matched=0):
    return {
        "ats_compatibility_score": score,
        "keyword_coverage": {"matched_count": matched, "total_count": 1},
        "structure_score_percent": 100,
        "missing_keywords": list(missing or []),
    }


class AtsOptimizerTests(unittest.TestCase):
    def setUp(self):
        self.jd = {
            "job_title": "Operations Analyst", "required_skills": ["Building business dashboards"],
            "preferred_skills": [], "tools_and_technologies": [], "domain_keywords": [],
            "ats_keywords": [], "important_action_verbs": [],
        }
        self.match = {"strong_matches": [], "partial_matches": [], "no_evidence": [], "keyword_matches": []}
        self.missing = [{
            "keyword": "Building business dashboards",
            "category": "Required skills",
            "evidence_status": "supported_in_resume_not_presented_in_cv",
        }]

    def test_target_and_iteration_limit_are_configured_in_one_module(self):
        self.assertEqual(TARGET_ATS_SCORE, 90)
        self.assertEqual(MAX_OPTIMIZATION_ITERATIONS, 3)
        self.assertEqual(OPTIMIZER_CONFIG["target_score"], TARGET_ATS_SCORE)
        self.assertEqual(OPTIMIZER_CONFIG["max_iterations"], MAX_OPTIMIZATION_ITERATIONS)

    def test_low_score_improves_with_verified_source_bullet(self):
        evidence = resume_with_evidence(["Built Power BI dashboards for 20 vendors."])
        initial = cv_with_bullets(["Coordinated daily operations."])

        def evaluate(candidate):
            text = cv_display_text(candidate)
            report = build_ats_report(self.jd, self.match, candidate, evidence, document_text=text)
            return report, text

        best, report, result = optimize_cv(initial, self.jd, self.match, evidence, evaluate)
        self.assertGreater(report["ats_compatibility_score"], evaluate(initial)[0]["ats_compatibility_score"])
        self.assertIn("Built Power BI dashboards for 20 vendors.", best["experience"][0]["bullets"])
        self.assertEqual(result["iterations_completed"], 1)
        self.assertEqual(result["history"][1]["selected"], True)
        self.assertFalse(result["target_reached"])

    def test_genuinely_absent_requirement_is_never_added(self):
        evidence = resume_with_evidence(["Improved operating costs by 20%."])
        initial = cv_with_bullets(["Improved operating costs by 20%."])
        jd = {**self.jd, "required_skills": ["Financial modeling"]}
        missing = [{
            "keyword": "Financial modeling", "category": "Required skills",
            "evidence_status": "not_verified_in_resume_evidence",
        }]

        def evaluate(candidate):
            return report_for(40, missing), cv_display_text(candidate)

        best, _report, result = optimize_cv(initial, jd, self.match, evidence, evaluate)
        self.assertEqual(best, initial)
        self.assertEqual(result["iterations_completed"], 0)
        self.assertEqual(result["stop_reason"], "evidence_insufficient")
        self.assertFalse(any("Financial modeling" in bullet for role in best["experience"] for bullet in role["bullets"]))

    def test_master_resume_gate_rejects_unverified_metrics_in_evidence_json(self):
        evidence = resume_with_evidence([
            "Built Power BI dashboards for 20 vendors.",
            "Built Power BI dashboards for 300 customers.",
        ])
        initial = cv_with_bullets(["Coordinated daily operations."])
        master_text = "Built Power BI dashboards for 20 vendors."

        def evaluate(candidate):
            score = 60 if any("20 vendors" in bullet for role in candidate["experience"] for bullet in role["bullets"]) else 40
            return report_for(score, self.missing), cv_display_text(candidate)

        best, _report, result = optimize_cv(
            initial, self.jd, self.match, evidence, evaluate, master_text=master_text,
        )
        bullets = best["experience"][0]["bullets"]
        self.assertIn("Built Power BI dashboards for 20 vendors.", bullets)
        self.assertNotIn("Built Power BI dashboards for 300 customers.", bullets)
        self.assertEqual(len(result["history"][-1]["improvements"]), 1)

    def test_target_score_stops_before_any_iteration(self):
        evidence = resume_with_evidence([])
        initial = cv_with_bullets(["A strong, verified bullet."])
        calls = []

        def evaluate(candidate):
            calls.append(candidate)
            return report_for(92), cv_display_text(candidate)

        _best, _report, result = optimize_cv(initial, self.jd, self.match, evidence, evaluate)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["iterations_completed"], 0)
        self.assertTrue(result["target_reached"])
        self.assertEqual(result["stop_reason"], "target_reached")

    def test_two_non_improving_iterations_stop_early(self):
        evidence = resume_with_evidence([
            "Built Power BI dashboards for 20 vendors.",
            "Built Power BI dashboards for 30 suppliers.",
            "Built Power BI dashboards for 40 distributors.",
        ])
        initial = cv_with_bullets(["Coordinated daily operations."])

        def evaluate(candidate):
            return report_for(40, self.missing), cv_display_text(candidate)

        _best, _report, result = optimize_cv(
            initial, self.jd, self.match, evidence, evaluate,
            config={"max_evidence_bullets_per_iteration": 1},
        )
        self.assertEqual(result["iterations_completed"], 2)
        self.assertEqual(result["stop_reason"], "two_consecutive_non_improving_iterations")

    def test_best_candidate_retained_when_later_iteration_scores_worse(self):
        evidence = resume_with_evidence([
            "Built Power BI dashboards for 20 vendors.",
            "Built Power BI dashboards for 30 suppliers.",
        ])
        initial = cv_with_bullets(["Coordinated daily operations."])

        def evaluate(candidate):
            count = len(candidate["experience"][0]["bullets"]) - 1
            score = 40 if count == 0 else 55 if count == 1 else 45
            return report_for(score, self.missing, matched=count), cv_display_text(candidate)

        best, report, result = optimize_cv(
            initial, self.jd, self.match, evidence, evaluate,
            config={"max_evidence_bullets_per_iteration": 1},
        )
        self.assertEqual(report["ats_compatibility_score"], 55)
        self.assertEqual(len(best["experience"][0]["bullets"]), 2)
        self.assertTrue(result["history"][1]["selected"])
        self.assertFalse(result["history"][2]["selected"])


if __name__ == "__main__":
    unittest.main()