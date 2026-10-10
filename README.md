# Bill Decoder ⚡

A bold, local Streamlit app that turns Pakistani electricity bills into structured
details and evidence-grounded answers. Built for Women Tech Quest 2026.

Supports KE, LESCO and IESCO bill images. Review payment dates, usage, charges,
taxes, printed history and late-payment tiers. Download extracted JSON or ask
questions in plain language. The shared pipeline validates model output with
Pydantic and performs supported arithmetic with Python Decimal.

## Run on Windows

Python 3.12 recommended (minimum 3.11). In the project folder:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r source/requirements.txt
Copy-Item source/.env.example .env
```

Edit `.env` and set your own Google Gemini API key. Never commit it.

```powershell
.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Open http://127.0.0.1:8501. Upload a clear PNG or JPG (up to 20 MB), click
**Decode my bill**, review the breakdown, and ask a question below.

## Privacy and limitations

Decoding sends the uploaded image to the configured Google Gemini API. The app
removes its temporary upload after processing. Extracted evidence and answers
are cached locally in `cache/`; the upload preview and conversation live in the
browser session. Model responses may contain mistakes; check important amounts
against the original bill. API quota, latency and availability depend on your account.
The server binds to localhost by default; this project is intended for personal use.

Credentials, caches, generated outputs, private bill datasets, recordings and
submission ZIPs are excluded by `.gitignore`. Supply your own bill images.

## Project layout

- `streamlit_app.py`: browser entry point
- `source/web_app.py` and `source/web_style.css`: interface
- `source/`: extraction, validation, question answering, CLI and tests
- `.streamlit/config.toml`: theme and local server settings
- `DESIGN.md`: UI decisions and assumptions

The optional Tkinter frontend remains available with
`.venv\Scripts\python.exe source/app.py`.
See [pipeline documentation](source/README.md) for CLI and competition CSV workflows.

## Check the project

```powershell
.venv\Scripts\python.exe -m unittest discover -s source -p test_pipeline.py -v
.venv\Scripts\python.exe -m unittest discover -s source -p test_web_app.py -v
```
