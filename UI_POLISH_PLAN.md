# VolstruisGids — UI Polish Plan

**Date**: 2026-06-16  
**Prepared for review**  
**Author**: Grok (based on current codebase inspection)  
**Status**: Planning document only — not yet approved for implementation

---

## Current State Summary (as of June 2026)

The project has a strong visual foundation from the recent **v2.0 Design System** work (documented in PROJECT_STATUS.md, June 15 entries):

- Warm Klein Karoo identity using earthy terracotta (#8B4513), sage green, refined gold accents on a creamy warm background (#FAF6F0).
- Excellent CSS design tokens for radius, elevation shadows, spacing, and transitions.
- High-quality, mobile-first components: pill buttons with generous 48px+ touch targets, elevated cards with hover lift, strong left-border + badge post-type indicator system.
- Boosted/promoted sparkle effects and business-listing treatments.
- Phase 2 delivered consistent application of post-type classes and improved cards in `_listing_cards.html`, `my_listings.html`, and the dynamic JS feed in `index.html`.
- Homepage hero, filters (internally labeled "Level 10 polished"), popular categories, and some loading/empty states already carry local flavor.

Core flows (HTMX-powered feed, Grok text improvement on create forms, "Ask Grok" on cards, Yoco credit purchases, private messaging) are functional.

**Remaining polish opportunities observed** (via read-only inspection of templates and `custom.css`):

- Many inline `style=""` attributes still present across templates (hero overlays, images, filter cards, credit balance sections, chat areas, profile cards, etc.). These bypass the v2.0 design system.
- Post-type badges in listing cards still mix custom CSS with legacy Bootstrap color utilities (`bg-success`, `bg-warning`, `bg-info`).
- Payments/credits pages (`payments/buy_credits.html` and the duplicate in `profile/`) and several forms have not yet received the full v2.0 treatment.
- Two similar detail templates exist (`listings/detail.html` and `main/listing_detail.html`).
- Messages (inbox + conversation) are structurally complete but visually basic (chat bubbles, empty states, mobile experience).
- Forms (create/quick_create, auth, profile editing, message compose) are mostly plain Bootstrap.
- Empty, loading, and error states exist in the feed but are inconsistent elsewhere (rules explicitly require handling these well).
- Some micro-interactions, focus states, and success feedback can be tightened to match the v2.0 tokens.
- Minor desktop assumptions and photo gallery treatments remain.

The app is already in significantly better shape than most Flask classifieds projects, but Phase 9 ("Admin + Polish") in the project spec has clear remaining work.

---

## Core Principles (any future UI polish work must obey)

- Strictly mobile-first Bootstrap 5 + HTMX (per `project_spec.json` and rules).
- Work exclusively inside the existing v2.0 design system in `app/static/css/custom.css` (reuse CSS custom properties, `.btn-*` variants, `.card`, post-type classes, etc.). No new colors or major new components without going through backlog + spec.
- **Smallest possible edits only**.
- Explicitly handle loading, empty, and error states.
- No new dependencies.
- 100% backward compatibility — existing classes like `business-listing` and `boosted` must continue to layer correctly.
- Every batch of work must follow the mandatory workflow:
  1. Analyse → explicitly list every file touched
  2. Plan → short numbered plan (maximum 5 steps)
  3. Act → smallest possible edits
  4. Verify → run `pip install -r requirements.txt` then clean app creation (or `python run.py`) and paste full output
  5. Summary with “Task COMPLETE — here is what you should test: …”
- Append a dated entry to `PROJECT_STATUS.md` after every change.
- Anything not explicitly covered in `project_spec.json` must first be added to `rules/backlog.md`.

---

## Prioritized Polish Opportunities

### High Impact / High Visibility
1. **Eliminate inline styles** — Systematically move hero, image treatments, filter card, credit balance card, message chat container, and similar into reusable classes or component styles in `custom.css`.
2. **Fully align listing cards & badges** — Update badge rendering in `_listing_cards.html` (and mirrored locations) to leverage the custom post-type badge classes (`.sale-badge`, `.wanted-badge`, etc.) defined in v2.0 CSS.
3. **Buy Credits / Payments surfaces** — Bring package cards, balance display, and forms in `payments/buy_credits.html` (and `profile/buy_credits.html`) up to current v2.0 standards.
4. **Listing Detail pages** — Reduce duplication between `listings/detail.html` and `main/listing_detail.html`. Polish photo gallery, seller card, inline messaging, price, and status indicators.
5. **Messages experience** — Improve chat bubbles with palette colors, better empty states ("No messages yet..."), read indicators, and mobile-friendly conversation view.

### Medium Impact / Consistency Wins
- Auth (login/register), profile editing, and profile view.
- Create and Quick Create forms (especially around the existing "Grok Ad Polish" feature UI).
- Homepage feed (empty/"no results" states, active filter feedback, category pills, HTMX loading transitions).
- Top and bottom navigation (active states, badge treatment, scroll behavior).
- Global reusable patterns for empty/loading/error states (critical for HTMX partial responses).
- Accessibility quick wins on top of the existing good foundation (focus visibility, label associations, contrast on badges).

### Lower Priority / Nice-to-Have
- Subtle micro-animations and optimistic UI updates on HTMX actions (Grok buttons, load-more, delete confirmations).
- My Listings alignment with main feed cards.
- Footer, guidelines, terms, and privacy pages.
- Image loading states and multi-photo gallery polish on detail.
- Any remaining responsive edge cases.

---

## Suggested Phased Approach

Each phase should be treated as a separate, self-contained task that follows the full 5-step workflow and ends with verification + status update.

**Phase A — Foundation (lowest risk, highest leverage)**
- Audit and remove as many inline `style` attributes as practical.
- Extract a small number of reusable component classes (`.listing-image`, `.filter-card`, `.balance-card`, etc.).
- Align all card badges across the system with the v2.0 post-type CSS.

**Phase B — Commerce Surfaces**
- Full v2.0 polish pass on the credits/payments pages.

**Phase C — High-Traffic User Flows**
- Detail page unification + polish.
- Messages visual and state improvements.

**Phase D — Forms, Auth, Profile & Global States**
- Create forms, auth pages, profile.
- Introduce consistent empty/loading/error components or patterns.
- Refine the Grok "Improve Ad" and "Ask Grok" UI elements.

**Phase E — Final Sweep**
- Navigation, hero, feed micro-polish.
- Full mobile + accessibility pass.
- Light internal UI guidelines (comments in CSS or a small section in this plan).

**Batch size guidance**: Touch 1–3 files per mini-task. Always start with an explicit file list.

---

## Process Recommendations

1. Before starting any implementation, re-read:
   - Latest `PROJECT_STATUS.md`
   - `rules/01-project-rules.md`, `.clinerules`, `04-workflow.md`
   - `rules/project_spec.json` (single source of truth)
   - This `UI_POLISH_PLAN.md`

2. Use shell scans + available search tools to inspect files before editing.

3. Log any out-of-scope ideas first in `rules/backlog.md`.

4. After changes: always execute the activation command, `pip install -r requirements.txt`, then a clean app creation check, and paste the output.

5. Finish every task by appending a dated, professional entry to `PROJECT_STATUS.md`.

---

## Definition of "UI Polish Complete" (for this phase)

- Minimal remaining (or zero) `style=""` attributes in templates.
- Every major surface (feed, detail, create, credits, messages, profile, auth) feels visually cohesive with the v2.0 warm Karoo system.
- Post-type, business, and promoted signals are obvious at a glance everywhere.
- Loading, empty, and error states are on-brand and consistent.
- Mobile experience is delightful (touch targets, spacing, no layout breakage).
- Future UI work can mostly happen by editing `custom.css` and applying small class combinations rather than fighting inline styles or one-off overrides.

---

**Next Steps (for reviewer)**

- Review this document.
- Decide which phases/items (if any) to move forward.
- For any approved work, create a task that starts with "Analyse → list every file..." following the project rules.

This plan exists purely for review. No implementation has occurred.
