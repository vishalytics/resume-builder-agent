import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from docx import Document

import interview_prep


class InterviewPreparationTests(unittest.TestCase):
    def setUp(self):
        self.resume = {
            "summary": "Built a vendor booking workflow that reduced manual coordination by 90%.",
            "experience": [{
                "company": "Example Co", "role": "Operations Analyst",
                "achievements": [{"evidence": "Built a vendor booking workflow, reducing manual coordination by 90%."}],
            }],
        }
        self.jd = {
            "job_title": "Operations Analyst", "company": "Example Employer",
            "responsibilities": ["Build operational dashboards", "Improve workflows"],
            "required_skills": ["Analytics"], "preferred_skills": [],
            "key_business_outcomes": ["Reduce manual work"],
        }
        self.match = {
            "no_evidence": [{"requirement": "Financial modeling", "reason": "Formal modeling is not documented."}],
        }
        self.plan = {
            "questions": [
                {
                    "question": f"Question {index}",
                    "category": "analytical_case" if index == 1 else "role_specific" if index == 2 else "behavioral",
                    "evidence_indices": [0] if index != 1 else [],
                    "follow_up_questions": ["What was the result?", "What would you do differently?"],
                }
                for index in range(1, 5)
            ],
            "experience_gap_indices": [0],
        }

    def test_plan_uses_validated_source_indices_and_reports_gaps(self):
        def fake_generate(prompt, **kwargs):
            self.assertEqual(kwargs["stage"], "interview_preparation")
            self.assertIn("Build operational dashboards", prompt)
            self.assertIn("90%", prompt)
            self.assertTrue(kwargs["response_validator"](json.dumps(self.plan))[0])
            invalid = json.loads(json.dumps(self.plan))
            invalid["questions"][1]["evidence_indices"] = [999]
            self.assertFalse(kwargs["response_validator"](json.dumps(invalid))[0])
            return json.dumps(self.plan)

        with patch.object(interview_prep, "generate_with_fallback", side_effect=fake_generate):
            content = interview_prep.build_interview_questions(self.resume, self.jd, self.match)
        self.assertIn("90%", "\n".join(content["questions"][1]["answer_points"]))
        self.assertEqual(content["experience_gaps"], self.match["no_evidence"])
        self.assertIn("proposed analytical approach", "\n".join(content["questions"][0]["answer_points"]))

    def test_document_contains_followups_case_guidance_and_gap_section(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "interview.docx"
            interview_prep.generate_with_fallback = lambda *args, **kwargs: json.dumps(self.plan)
            with patch.object(interview_prep, "generate_with_fallback", side_effect=lambda *args, **kwargs: json.dumps(self.plan)):
                content, path = interview_prep.generate_interview_document(
                    self.resume, self.jd, self.match, path
                )
            text = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
            self.assertIn("Likely follow-up questions", text)
            self.assertIn("Genuine experience gaps", text)
            self.assertIn("Financial modeling", text)
            self.assertIn("proposed analytical approach", text)
            self.assertEqual(len(content["questions"]), 4)


if __name__ == "__main__":
    unittest.main()