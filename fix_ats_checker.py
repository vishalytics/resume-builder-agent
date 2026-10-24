
from pathlib import Path
import py_compile

path = Path("ats_checker.py")
source = path.read_text(encoding="utf-8")

old = '''            evidence_terms = [
                "data analysis",
                "decision-making",
                "process improvement",
            ]'''

new = '''            evidence_terms = [
                "data analysis",
                "decision making",
                "process improvement",
            ]'''

if source.count(old) != 1:
    raise SystemExit(
        "PATCH NOT APPLIED: expected one evidence_terms block. "
        "No changes made."
    )

backup = Path("ats_checker_before_evidence_terms_fix.py")
backup.write_text(source, encoding="utf-8")

path.write_text(source.replace(old, new, 1), encoding="utf-8")

try:
    py_compile.compile(str(path), doraise=True)
except Exception:
    path.write_text(source, encoding="utf-8")
    raise

print("PATCH APPLIED. Syntax validation passed.")
print(f"Backup created: {backup}")
