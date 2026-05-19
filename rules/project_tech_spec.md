\# VolstruisGids – Technical Specification

\*\*Version 1.0\*\* | 18 May 2026



\*\*App purpose\*\*: Local classifieds + notices platform replacing two high-traffic WhatsApp groups (Oudtshoorn–Calitzdorp–Ladismith–Van Wyksdorp–Zoar).



\*\*Tagline\*\*: Klein Karoo se markplein – koop, verkoop, adverteer



\## 1. Tech Stack (exact)

\- Python 3.12

\- Flask 3.1+ (blueprints only)

\- Flask-SQLAlchemy 3.1+ + SQLAlchemy 2.0+

\- Flask-Migrate 4.1+

\- Flask-Login 0.6+

\- Flask-WTF 1.2+

\- Bootstrap 5.3 + HTMX 2.0 + Jinja2

\- Flask-Babel 4.0+ (English + Afrikaans ready)

\- SQLite (dev)

\- PayFast placeholders for payments



\## 2. Exact Folder Structure

volstruisgids/

├── app/

│   ├── \_\_init\_\_.py

│   ├── config.py

│   ├── models/ (user.py, category.py, listing.py, promotion.py, message.py, payment.py)

│   ├── blueprints/ (auth/, main/, listings/, promotions/, messages/, admin/)

│   ├── templates/

│   ├── static/

│   └── utils/

├── migrations/

├── instance/

├── rules/

├── .clinerules

├── project\_spec.json

├── PROJECT\_TECH\_SPEC.md

├── PROJECT\_STATUS.md

├── backlog.md

├── requirements.txt

├── run.py

├── .env.example

└── .gitignore



\## 3. Database Models (exact fields)

\*\*User\*\*  

id, username, email, phone, password\_hash, is\_business, business\_name, profile\_pic, bio, location, created\_at, last\_seen, posts\_today



\*\*Category\*\*  

id, name\_en, name\_af, slug, icon



\*\*Listing\*\*  

id, user\_id, title, description, price, is\_business\_ad, photos (JSON list max 6), category\_id, area, is\_active, created\_at, expires\_at



\*\*Promotion\*\*  

id, listing\_id, promotion\_type (top\_category\_week | top\_section\_month), start\_date, end\_date, amount\_paid, payment\_id



\*\*Message\*\*  

id, sender\_id, receiver\_id, listing\_id, text, read, timestamp



\*\*Payment\*\*  

id, user\_id, amount, payfast\_reference, status, created\_at



\## 4. Core Features (exact)

\- Auth (register/login with username + phone)

\- Feed with infinite scroll (HTMX)

\- Create Listing (personal free, business paid)

\- Promotions (Top Category 7 days + Top Section 30 days)

\- Full-text search + filters

\- Direct Messages (DM chat)

\- User Profile + own ads

\- Simple Admin panel

\- Free tier: maximum 5 posts per day for personal users

\- Business listings in separate higher-visibility section

\- Notices / Questions section: post info or ask questions → replies via DM only



\## 5. Monetisation

\- Free posts per day: 5 (personal)

\- Business ads: separate section with badge and priority

\- Paid promotions: top of category (7 days) or top of section (30 days)



\## 6. Rules (Cline must obey 100%)

\- Blueprints from day 1

\- After every change: run `pip install -r requirements.txt` then `python run.py`

\- For model changes: also run `flask db migrate` and `flask db upgrade`

\- Only implement what is in project\_spec.json

\- Any new idea → backlog.md only

\- Build must succeed with zero errors before marking task complete

\- Append dated summary to PROJECT\_STATUS.md after every task

