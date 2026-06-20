# Developer Specification: Polish Username / Business Name Display on Listing Cards

**Spec ID:** VOL-UI-POLISH-2026-06-20-SELLER-ATTRIB  
**Date:** 2026-06-20  
**Status:** Ready for Implementation  
**Priority:** Polish / UX Improvement  
**Scope:** Focused, additive change to listing card presentation. No DB schema changes.  
**Author:** VolstruisGids Senior Flask Engineer (with user input)

---

## 1. Background & Problem Statement

VolstruisGids listing cards currently do not prominently surface the poster’s identity (username or business name) in a consistent, scannable way. 

On the listing **detail page** (`main/listing_detail.html`):
- Business ads (`listing.is_business_ad == True`) render a styled business info bar showing `business_name` (or fallback) + "Verified Business • Klein Karoo".
- Personal ads show a simple "Posted by @username" line.

The business name treatment has previously been associated with "storefront" navigation (i.e. clicking the name took users to a business profile / storefront experience). 

**User request for polish:**
- For **personal** listings: username must display cleanly as normal text (no storefront implication).
- For **business** listings: business name should display normally (not itself be the clickable storefront trigger).
- Add a **separate, subtle "View store" hyperlink** (preferred next to the name) that explicitly takes the user to the business’s storefront / professional presence.

This improves clarity, reduces accidental navigation, and gives business owners a clear call-to-action for discovery of their other listings / brand.

---

## 2. Goals

- Add a clean "Seller / Business attribution" element to every listing card.
- Distinguish personal vs business presentation exactly as described.
- Provide an obvious but non-intrusive "View store" action for business listings only.
- Maintain visual consistency with existing Bootstrap + custom.css design system (business-badge, card styles, etc.).
- Keep implementation minimal, testable, and reversible.
- Zero database migrations or column changes.

---

## 3. Current Code State (Repo Scan 2026-06-20)

**Key files examined:**
- `app/templates/main/_listing_cards.html` — Card partial used by homepage, category views, search results. **Currently contains no seller name / username element**.
- `app/templates/main/listing_detail.html` — Has the business vs personal seller info logic (reference implementation).
- `app/models/listing.py` — `is_business_ad`, relationship to `user` (lazy=True).
- `app/models/user.py` — `username`, `business_name`, `is_business`, `account_type`, `profile_pic`, `is_business_account` @property, `storefront_enabled` @property.
- `app/blueprints/main/routes.py` & `app/blueprints/listings/routes.py` — Query listings for cards (need to ensure `user` relationship is accessible).
- `app/static/css/custom.css` — Contains business-badge and promoted styles.

**Observation:** The card partial is the right place for this addition. The detail page already demonstrates good conditional rendering we can mirror/adapt.

---

## 4. Functional Requirements

### 4.1 Display Rules (inside each `.card` in the loop)

**For Business Listings** (`listing.is_business_ad and listing.user`):
- Display the business name prominently but cleanly (use `listing.user.business_name or listing.user.username`).
- Show a small visual cue that this is a business (reuse or lightly adapt `.business-badge` or a subtle "PRO" / store icon).
- **Next to or immediately under the name**: a small, styled hyperlink reading exactly **"View store"** (or with icon `bi bi-shop` / `bi bi-building`).
  - Clicking it navigates to the business storefront.
- Do **not** make the business name itself a large clickable link to the storefront.

**For Personal Listings** (default / `not listing.is_business_ad`):
- Display "Posted by @username" (or similar) in muted text.
- **No** "View store" link.
- Username is plain text or a subtle non-storefront link (e.g. to public profile if exists).

**Fallbacks:**
- If no `listing.user`: show "Posted by Seller" (muted).
- If business but no `business_name`: fall back to `username`.

### 4.2 Target URL for "View store"

Recommended (minimal new code):
- Create or repurpose a lightweight public route: `GET /store/<username>` or `GET /business/<username>` that renders a business storefront page (header with business details + grid of their active listings).

**Interim / low-scope option (if storefront route not ready in this iteration):**
- Link to the existing authenticated profile page for the business owner (or a future public profile view).
- Or link to `url_for('main.index', seller_username=listing.user.username)` if we add a simple filter to the homepage query (adds value quickly).

**Decision needed before implementation:** Confirm exact target endpoint. The spec below assumes a new `main.business_storefront` endpoint will be added (or aliased). If we want zero new routes, we can hardcode a sensible interim target and note it clearly.

### 4.3 Styling & Layout Guidance

- Place the attribution block **after** the location/date line and **before** the action buttons / share section (inside the `card-body`, before or inside the `mt-auto` div).
- Use `small` / `fw-semibold` / muted colors for personal; slightly stronger for business name.
- "View store" link: `text-decoration-none`, small font, brand accent color (e.g. #8B4513 or primary), with icon.
- Keep card height and spacing consistent (test on mobile).
- Responsive: flex-wrap friendly.
- Accessibility: sufficient contrast, meaningful link text.

Example visual structure (text representation):

```
[Photo]

[Sale] [BUSINESS]

Title
R 1,234

Area · 20 Jun 2026

**Business Name**  [View store →]

[View] [Ask Grok] [Share...]
```

Or tighter:

**Business Name** <small class="text-muted ms-2"><a href="...">View store</a></small>

---

## 5. Technical Implementation Steps (for the talented developer)

### Step 1: Update the Card Partial (Primary Change)

**File:** `app/templates/main/_listing_cards.html`

Insert a new seller attribution block right after the meta paragraph:

```jinja2
            <p class="card-text text-muted small">
                {{ listing.area }} · {{ listing.created_at.strftime('%d %b %Y') }}
            </p>

            <!-- NEW: Seller / Business Attribution (polish item) -->
            <div class="seller-attribution mb-2">
                {% if listing.is_business_ad and listing.user %}
                    <div class="d-flex align-items-baseline gap-2 flex-wrap">
                        <span class="fw-semibold">
                            {{ listing.user.business_name or listing.user.username }}
                        </span>
                        <span class="badge business-badge" style="font-size: 0.6rem; padding: 0.1em 0.4em; vertical-align: baseline;">BUSINESS</span>
                        <a href="{{ url_for('main.business_storefront', username=listing.user.username) }}" 
                           class="small text-decoration-none fw-medium"
                           style="color: #8B4513; white-space: nowrap;">
                            <i class="bi bi-shop-window me-1"></i>View store
                        </a>
                    </div>
                {% elif listing.user %}
                    <span class="text-muted small">
                        Posted by <strong class="text-dark">@{{ listing.user.username }}</strong>
                    </span>
                {% else %}
                    <span class="text-muted small">Posted by Seller</span>
                {% endif %}
            </div>
```

**Notes for developer:**
- The `url_for` assumes a route named `main.business_storefront` exists (see Step 3). If the route is not yet implemented, replace with a temporary target (e.g. `url_for('main.index')` + comment) or link to `url_for('profile.profile')` with a note that it requires login.
- Add a small CSS rule in `custom.css` if spacing needs tuning (see Step 4).

### Step 2: Ensure User Relationship is Loaded (Performance)

In any route that renders cards (primarily `main/routes.py` index/search/category functions):

```python
# Example pattern to add if not present
listings = (Listing.query
    .options(joinedload(Listing.user))
    .filter(Listing.is_active == True, ...)
    .order_by(...)
    .all())
```

Import: `from sqlalchemy.orm import joinedload`

Current lazy=True relationship will work but may cause N+1 queries on busy pages. Adding `joinedload` is a cheap win and recommended as part of this polish.

### Step 3: Add / Confirm Business Storefront Route (Recommended)

**Option A (Preferred for clean UX) – New lightweight endpoint**

In `app/blueprints/main/routes.py`:

```python
@main_bp.route('/store/<string:username>')
def business_storefront(username):
    user = User.query.filter_by(username=username).first_or_404()
    if not user.is_business_account:
        abort(404)  # or redirect to regular profile
    
    # Get active (non-expired) listings by this business
    active_listings = (Listing.query
        .filter_by(user_id=user.id, is_active=True)
        .filter(Listing.is_expired == False)  # or use freshness logic
        .order_by(Listing.created_at.desc())
        .limit(12)
        .all())

    return render_template('main/business_storefront.html', 
                           business_user=user, 
                           listings=active_listings)
```

You will also need a new template `app/templates/main/business_storefront.html` (simple header with business_name, bio, profile_pic + grid of `_listing_cards.html` include or duplicated cards).

**Option B (Zero new templates for this ticket):** 
Link "View store" to the existing detail page of one of their recent listings, or simply to `url_for('main.index', q=business_name)` (search). Less ideal.

**Recommendation:** Go with Option A if time allows — it delivers real value and matches the "storefront" language. Scope can be kept small (reuse card partial, simple template).

### Step 4: Optional CSS Polish

In `app/static/css/custom.css` add:

```css
.seller-attribution {
    font-size: 0.875rem;
    line-height: 1.3;
}
.seller-attribution .badge {
    vertical-align: middle;
}
```

### Step 5: Testing Checklist

1. Run locally: `flask run` or `./start-dev.ps1`
2. Create / view both personal and business listings (use test users or upgrade account in profile).
3. Verify on homepage, category, and search results pages that cards render correctly.
4. Mobile viewport: attribution wraps nicely, no layout shift.
5. Click "View store" – confirm it reaches the intended page (or placeholder).
6. No errors in console, no broken links.
7. Existing delete / share / Ask Grok buttons still work and layout is preserved.
8. Accessibility: keyboard focus on "View store" link is clear.

### Step 6: Rollout / Deployment

- Merge to main after review.
- PythonAnywhere: `git pull`, restart app.
- Monitor for any template rendering issues (user relationship None checks are already in the Jinja).

---

## 6. Out of Scope (for this change)

- Full redesign of the business_storefront page (keep minimal).
- Changes to listing creation flow or forms.
- New database fields.
- Changes to the detail page seller info (can be aligned later).
- Adding public profile pages beyond the storefront route.
- Analytics on storefront clicks.

---

## 7. Open Questions / Decisions for You

1. Exact wording/icon for the link: "View store", "Visit store", "See more from this business"? (Current spec uses "View store" per your preference.)
2. Target route for "View store": Shall we implement the `/store/<username>` route + template now, or use an interim link (e.g. to profile or homepage filter) ?
3. Should the business name itself be clickable (to the same storefront) in addition to the explicit link, or strictly separate as requested?
4. Any preference on exact placement inside the card (above or below price, alignment)?

---

## 8. Next Steps After Spec Approval

1. Confirm answers to open questions above.
2. We (or the talented dev) implement the template change + any supporting route.
3. Provide the **complete updated `_listing_cards.html`** file ready to paste.
4. Test together on dev + production.
5. Close the polish item and move to next UI improvement from the backlog.

---

**This spec is designed to be self-contained.** A mid-to-senior Flask developer should be able to execute it end-to-end with the information above, the existing codebase patterns, and one or two clarifying answers.

Let's keep VolstruisGids polished, trustworthy, and delightful for Klein Karoo users and businesses. 😊
