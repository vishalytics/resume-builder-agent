import unittest

from ats_checker import build_ats_report, get_terms, matches_keyword, normalize


class AtsCheckerTests(unittest.TestCase):
    def test_legitimate_equivalents_match_but_advanced_excel_does_not_infer_from_excel(self):
        self.assertTrue(matches_keyword("Standard operating procedures (SOPs)", normalize("Converted 20 SOPs into training videos")))
        self.assertTrue(matches_keyword("Go-to-market (GTM) strategy", normalize("Supported GTM strategy")))
        self.assertTrue(matches_keyword("Cross-functional Leadership", normalize("Led cross-functional rollout")))
        self.assertFalse(matches_keyword("Advanced Excel skills", normalize("Microsoft Excel")))

    def test_financial_modeling_is_partial_and_unverified_skills_stay_missing(self):
        jd = {
            "job_title": "Analyst", "required_skills": ["Financial modeling", "Advanced Excel skills"],
            "preferred_skills": [], "tools_and_technologies": [], "domain_keywords": [],
            "ats_keywords": [], "important_action_verbs": [],
        }
        match = {
            "strong_matches": [],
            "partial_matches": [{
                "requirement": "Develop business cases, financial models, and data-driven recommendations",
                "gap": "BOM cost modeling and TCO are evidenced, not formal financial models.",
            }],
            "no_evidence": [{"requirement": "Advanced Excel skills", "reason": "Advanced level is not documented."}],
            "keyword_matches": [],
            "priority_changes": [],
        }
        cv = {
            "name": "Candidate", "targeted_headline": "Analyst", "targeted_summary": "Operations",
            "core_expertise": ["Cost analysis"], "tools_and_technologies": ["Excel"],
            "experience": [], "education": {}, "certifications": [],
        }
        resume = {"experience": [{"achievements": [{"evidence": "Built a Product Master Cost Sheet and evaluated TCO."}]}]}
        report = build_ats_report(jd, match, cv, resume)
        statuses = {item["keyword"]: item["evidence_status"] for item in report["missing_keywords"]}
        self.assertEqual(statuses["Financial modeling"], "partial_evidence_only")
        self.assertEqual(statuses["Advanced Excel skills"], "not_verified_in_resume_evidence")
        self.assertEqual(report["keyword_coverage"]["required_skills_percent"], 0)
        self.assertEqual(report["ats_compatibility_score"], 0)
        self.assertEqual(report["unsupported_or_unverified_requirements"][0]["requirement"], "Advanced Excel skills")

    def test_empty_jd_scores_zero_and_legacy_skills_schema_is_recognized(self):
        report = build_ats_report({}, {}, {"skills": ["Operations"]})
        self.assertEqual(report["ats_compatibility_score"], 0)
        self.assertTrue(report["section_checks"]["Core expertise"])
        self.assertIn("50% required-skill coverage", report["score_note"])

    def test_case_and_punctuation_variants_are_counted_once(self):
        terms = get_terms({
            "required_skills": ["Market research"],
            "ats_keywords": ["Market Research", "Business Operations"],
            "domain_keywords": ["Business-Operations"],
        })
        self.assertEqual(len(terms), 2)
        self.assertEqual(list(terms.values()), ["Required skills", "Domain keywords"])


if __name__ == "__main__":
    unittest.main()