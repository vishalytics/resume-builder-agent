import json
import unittest
from pathlib import Path

import pipeline


class MasterResumeIntegrityTests(unittest.TestCase):
    def test_evidence_identity_roles_education_and_certifications_align(self):
        resume = json.loads((pipeline.DATA_DIR / "resume_evidence.json").read_text(encoding="utf-8"))
        master_text = pipeline._read_master_resume_text()
        self.assertEqual(pipeline._resume_evidence_alignment_errors(resume, master_text), [])

    def test_achievements_and_leadership_come_from_master_without_editor_notes(self):
        master_text = pipeline._read_master_resume_text()
        achievements, leadership = pipeline._master_resume_highlights(master_text)
        self.assertEqual(len(achievements), 4)
        self.assertEqual(len(leadership), 3)
        self.assertTrue(any("PPO offered" in item for item in achievements))
        self.assertTrue(any("Badminton Singles" in item for item in achievements))
        self.assertFalse(any(
            marker in item.casefold()
            for item in achievements + leadership
            for marker in ("shg accelerator", "add your exact", "confirm", "validate")
        ))


if __name__ == "__main__":
    unittest.main()