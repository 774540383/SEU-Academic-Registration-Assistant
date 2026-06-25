@echo off
python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload
