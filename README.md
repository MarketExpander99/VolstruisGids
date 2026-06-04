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
# 1. Clone
git clone https://github.com/MarketExpander99/VolstruisGids.git
cd VolstruisGids

# 2. Virtual environment (recommended)
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # macOS/Linux

# 3. Install
pip install -r requirements.txt

# 4. Environment
cp .env.example .env

# 5. Database
python -m flask db upgrade

# 6. Run
python run.py