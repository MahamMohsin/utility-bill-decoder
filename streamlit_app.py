"""Browser entry point; run with python -m streamlit run streamlit_app.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'source'))
from web_app import main

main()
