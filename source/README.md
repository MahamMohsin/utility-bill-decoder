# Utility Bill Decoder - Women Tech Quest 2026

The primary interface is now the Streamlit browser app. From the project root, run
`.venv\Scripts\python.exe -m streamlit run streamlit_app.py`.
See the root `README.md` for the updated UI and setup. The competition pipeline and
optional legacy desktop interface documented below remain available.

Python 3.12 (minimum 3.11). Reads KE, LESCO and IESCO bill images with Google Gemini API,
validates the exact Level 1 schema, keeps separate non-identifying usage history,
and answers Level 2 questions using bill evidence and Python Decimal calculations.

## Setup on Windows

Run from the project root (parent of `source/`):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r source/requirements.txt
Copy-Item source/.env.example .env
# Edit .env locally and replace the API_KEY placeholder; never share it.
.venv\Scripts\python.exe source/main.py verify-api
```

The `.env` file belongs at the project root. Environment variables: MODEL_PROVIDER=google,
MODEL_NAME=gemini-3.5-flash-lite, API_KEY=your-api-key-here. Existing aliases
GEMINI_MODEL and GEMINI_API_KEY are supported when their primary names are absent.
OS environment values take precedence over `.env` values. Only the officially allowed
Google IDs gemini-3.1-flash-lite and gemini-3.5-flash-lite are accepted. There is no
fallback. This project configures no paid service; use an AI Studio free-tier project.
Actual billing/quota eligibility is controlled by the user's Google account.

## Training and tests

```powershell
.venv\Scripts\python.exe source/main.py train --bills train/bills
.venv\Scripts\python.exe -m unittest discover -s source -p test_pipeline.py -v
```

Image discovery is recursive, supporting the provided `train/bills/bills` layout.
Training results are in `output/training/`; `regression.json` reports full field and
ordered charge/tax mismatches against the guide's page 9 KESC_0008 example.
An empty object means exact agreement. Reference data is used only by training tests,
never by the production extractor. `sample_answers.json` contains both guide examples.
Training is image-based inference and validation, not model fine-tuning.

Ask any question about a specific bill:

```powershell
.venv\Scripts\python.exe source/main.py ask --bill train/bills/bills/KESC_0008.png --question "How much extra will I pay after the due date?"
```

Optional desktop window (Tkinter, included in the standard Windows Python installer):

```powershell
.venv\Scripts\python.exe source/app.py
```

Select a bill, inspect its image and extracted JSON, then type a question and click
Ask question (or press Enter). API work runs in a background thread. Loading and
error messages are visible; all UI inference uses the same validated CLI pipeline.
Design: restrained utility desk, warm paper background, dark green headings,
Segoe UI text and Consolas JSON. The minimum desktop size is 640 x 450; the bill
preview resizes to available space and question controls keep their own reserved row.
Widget initialization is checked by `source/app.py --self-test`; full keyboard,
screen-reader and visual layout testing is not automated.

## Generate both competition CSV files

Place 10 official images in `test/bills/` and the untouched official templates in
`test/csv/level1.csv` and `test/csv/level2.csv`. Then run:

```powershell
.venv\Scripts\python.exe source/main.py batch --bills test/bills --templates test/csv --output output
.venv\Scripts\python.exe source/validate_submission.py
.venv\Scripts\python.exe source/validate_submission.py --package submission.zip
```

Exact headers are `bill_id,json` and `bill_id,question_id,question,answer`. The
application preserves row order and template identity/question text. It writes UTF-8
using Python csv and serializes each complete JSON object onto one line.
Do not edit outputs manually. Validation compares them with the official templates.
The ZIP command validates first, checks exact archived bytes and CRC, and refuses
ZIPs exceeding 15,000,000 bytes. It never uploads or submits. Existing ZIPs are not overwritten
unless `--replace` is explicitly passed; validated replacements are written atomically.

## Reliability and dependencies

Pillow 12.3.0 retains original image detail and corrects EXIF orientation; overlapping
crops are used on extraction validation retries. Pydantic 2.13.5 rejects extra or
missing fields, invalid dates, numeric strings, nonfinite numbers and zero line items.
python-dotenv 1.2.2 loads local credentials. HTTP uses the Python standard library.
API failures use capped exponential backoff, 4.2-second request spacing, and up to
five attempts. Invalid extraction JSON/schema triggers up to three image passes.
Blocked/truncated responses stop processing. Logs never include keys or provider bodies.

Image/model/prompt hashes cache extraction, and evidence/question/model hashes cache
answers under `cache/`. Rerunning resumes completed calls. `--refresh` forces fresh
inference. Missing/duplicate images and invalid templates fail before batch processing.
Official outputs are published after every bill succeeds. Previous outputs may remain
after a failed run; always verify against the current templates before packaging.

Gemini plans arithmetic over named printed evidence; Python Decimal evaluates a
restricted AST without eval, functions or attribute access. Gemini explains verified
results. Month threshold counts are computed directly in Python. Unsupported years
are rejected. Missing information is reported as unavailable; estimates require
explicit assumptions from printed evidence. These checks reduce errors but do not
prove every natural-language claim; inspect training answers and uncertainties.

Late-payment evidence retains every printed tier and date range separately. Answers
explain all tiers, the on-time amount and due date; a date-specific question selects
its matching tier. The highest printed amount remains the official extraction value,
and is used as the maximum or unspecified-date summary without hiding earlier tiers.
Printed payable totals and surcharge amounts are kept independently to preserve
rounding. Answers use customer language and exclude JSON, level names and code fields.

## Optional demo

No demo is generated by default. If recorded, place one real working-app recording
at `demo/demo.mp4`, `demo/demo.mov`, or `demo/demo.webm`. It must be at least 500,000
bytes, no longer than 180 seconds, readable and fit the complete 15 MB ZIP. Show
starting the app, the bill image, extracted fields, sample answers and CSV generation.
Install ffprobe for video metadata checks, watch the complete recording, then use
`--demo-reviewed` with validation/packaging. Metadata cannot prove that it records
a real working app; this flag is your explicit confirmation after watching it.

## AI usage

- Application models: Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) through Google
  Gemini API / Google AI Studio; verified and used for training. The guard also supports
  the officially allowed Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`), not used in training.
- AI coding assistants: OpenAI Codex Desktop, used to implement, debug and test this
  project. Underlying assistant model was not exposed to this session.
- Other AI coding assistants: none known in this session. Add any other assistants
  you personally used before packaging; the validator cannot discover prior use.
- Other application AI APIs/services: none. Local OCR: none. Prebuilt invoice services: none.
- Documentation tools used during development: web search of Google documentation,
  local PDF text extraction (pypdf), image inspection, and the Codex bundled Python runtime.

## Submission contents

Only explicitly permitted source files, the two result CSVs and an optional verified
demo are packaged. Virtual environments, runtime dependencies, bytecode, images,
caches, local credentials and real `.env` files are excluded. Validation scans known
local secret values and common key patterns; it cannot prove the absence of every
possible secret or semantic AI error. No automatic submission is implemented.
