# Testing & Verification Rules

- After every code change: run `pip install -r requirements.txt` then `python run.py`
- For database changes: also run `flask db migrate` and `flask db upgrade`
- Report full terminal output.
- Think about areas, personal vs business, promotions and DMs.
- Never break existing flows.