# Resume Agent

Resume Agent creates a role-specific application pack from the verified evidence in `data/resume_evidence.json` and the Word layout in `templates/CV_TEMPLATE.docx`. It does not alter the master resume or template.

## Setup and Run

Use the existing Windows virtual environment and configure a Gemini API key in the process environment. The key is read by the Google GenAI SDK and is never written into project files.

```powershell
.\venv\Scripts\Activate.ps1
$env:GEMINI_API_KEY = "your-key"
python -m streamlit run app.py
```

`GOOGLE_API_KEY` is also recognized by the Google GenAI SDK. Do not put either key in source files, prompts, reports, or committed settings.

Paste JD text or provide a public HTTP(S) job URL. Each application receives its own run ID, intermediate artifacts, manifest, and output folder:

- `data/runs/<run-id>/`
- `output/runs/<run-id>/`

The app only offers downloads for the active run in that browser session. A failed run records the failed stage and safe model-attempt classifications in `run_manifest.json`; retrying that run reuses only validated artifacts whose fingerprints still match. Starting a new application creates a new run and does not reuse previous-run outputs.

## Gemini Fallback

Models are attempted sequentially in the order configured in `gemini_client.py`. A valid response ends that stage immediately. Temporary server/network failures receive at most two attempts per model with a short backoff; confirmed daily quota exhaustion skips further attempts for that model. Short rate limits are retried only when the provider gives a wait of 15 seconds or less. Authentication and invalid-request failures stop the stage. The task ceiling is explicit and bounded. Model switching does not add quota; availability of the configured fallback models depends on the same project and is not guaranteed.

## ATS Optimization

`ats_optimizer.py` is the single configuration point for the optimization target and limits:

- `TARGET_ATS_SCORE = 90`
- `MAX_OPTIMIZATION_ITERATIONS = 3` after the initial CV
- `MIN_SCORE_IMPROVEMENT = 1`
- `MAX_ADDITIONS_PER_ITERATION = 2` source-evidence bullets

Optimization is deterministic and local: it considers only exact achievement evidence present in the verified resume database and only when that evidence and role support a currently missing ATS requirement. It makes no additional Gemini calls and does not add partially supported or genuinely absent claims. Each proposal is rendered to a temporary DOCX and scored from its extracted document text. The best score/match/structure candidate is retained; iteration stops at the target, evidence exhaustion, two consecutive non-improving iterations, or the configured limit. The final report is recomputed from the selected run CV DOCX and records document integrity. The ATS report separately records required/preferred/overall terms, experience evidence, responsibility alignment, unsupported items, document checks and truthful recommendations; optimization does not modify scoring weights.

Inline bolding is deterministic and limited to a leading action verb plus selected verified percentages, counts, scale phrases, currency amounts, or known achievements (at most three spans per bullet). It splits cloned Word runs and changes only run-level bold; paragraph styles, existing font settings, section structure, and page flow are preserved. Hyperlink paragraphs are left untouched. Extra verified bullets clone the template's existing bullet paragraph style rather than changing the template, and may flow to additional pages.

## Tests

Run deterministic mocked tests without making Gemini requests:

```powershell
python -m unittest discover -s tests -v
```

The suite covers sequential model calls and retries, schema validation, run isolation/resumption, ATS evidence classification, interview content, and Streamlit download/error states.