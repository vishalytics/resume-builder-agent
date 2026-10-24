
from pathlib import Path
import re
import py_compile

p = Path("ats_checker.py")
s = p.read_text(encoding="utf-8")

backup = Path("ats_checker_before_matching_fix.py")
if not backup.exists():
    backup.write_text(s, encoding="utf-8")

old = '''        is_match = any(
            candidate and re.search(
                r"(?<![a-z0-9+#])" + re.escape(normalize(candidate)) +
                r"(?![a-z0-9+#])",
                cv_text
            )
            for candidate in candidates
        )'''

new = '''        is_match = any(
            candidate and re.search(
                r"(?<![a-z0-9+#])" + re.escape(normalize(candidate)) +
                r"(?![a-z0-9+#])",
                cv_text
            )
            for candidate in candidates
        )

        # Recognize combined evidence for analytical/problem-solving skills.
        if normalized_term == "strong analytical and problem-solving abilities":
            evidence_terms = [
                "data analysis",
                "decision-making",
                "process improvement",
            ]
            is_match = is_match or all(
                re.search(
                    r"(?<![a-z0-9+#])" + re.escape(normalize(term)) +
                    r"(?![a-z0-9+#])",
                    cv_text
                )
                for term in evidence_terms
            )'''

if s.count(old) != 1:
    raise SystemExit(
        "PATCH NOT APPLIED: expected matching block not found exactly once. "
        "No changes made."
    )

updated = s.replace(old, new, 1)

# Validate syntax before overwriting the working file.
test_file = Path("_ats_checker_validation.py")
test_file.write_text(updated, encoding="utf-8")

try:
    py_compile.compile(str(test_file), doraise=True)
finally:
    test_file.unlink(missing_ok=True)

p.write_text(updated, encoding="utf-8")
print("PATCH APPLIED. Backup:", backup)
print("Syntax validation passed.")
