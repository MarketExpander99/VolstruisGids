# VolstruisGids

**The Klein Karoo’s Digital Notice Board** — Local classifieds done right.

A clean, searchable, always-available marketplace replacing noisy WhatsApp groups for Oudtshoorn, Ladismith, Calitzdorp and surrounding areas.

### Mission
People in the Klein Karoo are already buying, selling, and sharing daily on WhatsApp.  
Volstruis Gids gives them a **better home**:  
- Listings that don’t disappear when you stop scrolling  
- Private messaging (no more public phone numbers)  
- Powerful search and filters  
- Free personal ads + paid business visibility  

### Key Features
- **Free Personal Listings** — Post for free (active 3–7 days)
- **Business / Promoted Ads** — Longer visibility, top placement, badges
- **Smart Search** — By keyword, area, price, category, new/used
- **Private DM System** — Message sellers safely
- **Mobile-first** — Works great on phones (the main device in the Karoo)
- **Community feel** — Warm, trustworthy, local-first design

### Tech Stack
- Python + Flask (Blueprints)
- SQLAlchemy + Flask-Migrate
- Flask-Login + Flask-WTF
- Bootstrap 5
- SQLite (development) → PostgreSQL (production)
- Deployed on PythonAnywhere

### Quick Start (Development)

```bash
# 1. Clone + enter folder
git clone https://github.com/MarketExpander99/VolstruisGids.git
cd VolstruisGids
```

#### Easiest way on Windows (recommended)

Just run one of these helper scripts — they automatically use the correct Python from the virtual environment and install dependencies for you. No activation headaches.

**PowerShell:**
```powershell
.\start-dev.ps1
```

**Command Prompt / double-click:**
```cmd
start-dev.bat
```

These scripts will:
- Create `.venv` if missing
- Install `requirements.txt` (including `requests`)
- Run `python run.py` using the venv Python

#### Manual steps (all platforms)

```bash
# 2. Create virtual environment (only once)
python -m venv .venv
```

**Activate (only if not using the helper scripts above):**

- **PowerShell (Windows):**  
  `(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; & ".\.venv\Scripts\Activate.ps1"`

- **cmd.exe (Windows):**  
  `.venv\Scripts\activate.bat`

- **macOS / Linux:**  
  `source .venv/bin/activate`

```bash
# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and edit environment file (add your real keys)
cp .env.example .env

# 5. Apply database migrations
python -m flask db upgrade

# 6. Run the dev server
python run.py
```

**Tip:** After `git pull` or editing requirements, re-run `pip install -r requirements.txt` (or just use `start-dev.ps1` / `start-dev.bat`).

`python run.py` will now **automatically switch** to the correct `.venv` Python on Windows if you forget to activate. You should rarely see the old ModuleNotFoundError anymore.

**Still getting "No module named 'requests'"?**

You are using the wrong Python. Run this diagnostic in your terminal:

```powershell
cd C:\Users\ebenc\Documents\XAIFV\Projects\VolstruisGids
python --version
python -c "import sys; print('Python executable:', sys.executable)"
python -c "import requests" 2>&1 || echo "requests is MISSING in this python"
```

Then use the helper script instead of plain `python run.py`.

**Nuclear option (recreate venv cleanly):**
```powershell
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.\start-dev.ps1
```