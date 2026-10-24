import json
import unittest
from unittest.mock import patch

import resume_matcher


class ResumeMatcherEvidenceTests(unittest.TestCase):
    def test_matcher_removes_unsupported_evidence_before_returning_results(self):
        resume = {
            "experience": [{
                "company": "Example Co",
                "role": "Operations Analyst",
                "achievements": [{
                    "evidence": "Built Power BI dashboards, reducing manual coordination by 90%.",
                    "metrics": ["Reduced manual coordination by 90%"],
                }],
            }],
        }
        jd = {
            "responsibilities": ["Build Power BI dashboards and reduce manual coordination."],
            "required_skills": [], "preferred_skills": [], "tools_and_technologies": [],
            "domain_keywords": [], "ats_keywords": [], "behavioral_requirements": [],
            "experience_requirements": [], "education_requirements": [],
            "important_action_verbs": [], "key_business_outcomes": [],
        }
        response = {
            "overall_match": 80,
            "strong_matches": [{
                "requirement": "Build Power BI dashboards",
                "evidence": "Built Power BI dashboards, reducing manual coordination by 90%.",
                "company": "Example Co", "role": "Operations Analyst",
                "metrics": ["Reduced manual coordination by 90%"],
            }],
            "partial_matches": [{
                "requirement": "Build Power BI dashboards",
                "evidence": "Owned a $5M marketing budget and increased ROI by 300%.",
                "gap": "No evidence", "company": "Invented Inc", "role": "CFO",
                "metrics": ["$5M", "300%"],
            }],
            "no_evidence": [], "keyword_matches": [], "missing_keywords": [],
            "recommended_resume_keywords": [], "recommended_experiences": [],
            "recommended_projects": [], "skill_gaps": [], "priority_changes": [],
        }

        def fake_generate(prompt, **kwargs):
            self.assertEqual(kwargs["stage"], "resume_matching")
            self.assertTrue(kwargs["response_validator"](json.dumps(response))[0])
            return json.dumps(response)

        with patch.object(resume_matcher, "generate_with_fallback", side_effect=fake_generate):
            result = resume_matcher.match_resume_to_jd(resume, jd)
        self.assertEqual(len(result["strong_matches"]), 1)
        self.assertEqual(result["strong_matches"][0]["company"], "Example Co")
        self.assertEqual(result["partial_matches"], [])
        self.assertEqual(len(result["unverified_model_matches"]), 1)
        self.assertTrue(any("did not pass" in item["reason"] for item in result["no_evidence"]))


if __name__ == "__main__":
    unittest.main()