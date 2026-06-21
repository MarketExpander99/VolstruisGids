# app/press_releases.py
"""
Press & Media data for VolstruisGids.
Simple structure for easy non-developer updates.

Add new releases at the TOP of the list (most recent first).
Only edit this file to publish new press releases.

Fields:
- id: stable unique identifier (e.g. vol-YYYY-XXX)
- date: ISO for sorting / future use
- display_date: Human readable for display
- title: Official headline
- summary: Short teaser (1-2 sentences)
- slug: URL-friendly (future use for /press/slug)
- pdf_url: Path to hosted PDF (create file in static/press/)
- author: Who issued it
- full_text_html: Full body as safe HTML fragments (paragraphs, lists etc.)
"""

PRESS_RELEASES = [
    {
        "id": "vol-2026-001",
        "date": "2026-06-21",
        "display_date": "21 June 2026",
        "title": "Connecting Klein Karoo Micro-Economies: VolstruisGids Turns Local Economic Growth into a Real Possibility",
        "summary": "VolstruisGids, a locally built marketplace for the Klein Karoo, launches to give permanent visibility to local classifieds, services and businesses — replacing fleeting WhatsApp group posts with searchable, trustworthy local commerce that helps micro-economies thrive.",
        "slug": "connecting-klein-karoo-micro-economies",
        "pdf_url": "/static/press/vol-2026-001.pdf",
        "author": "Eben",
        "full_text_html": """
<p><strong>Oudtshoorn, South Africa — 21 June 2026</strong></p>

<p>VolstruisGids, the Klein Karoo's new dedicated local marketplace platform, today announced its public launch with a mission to connect and strengthen the region's micro-economies.</p>

<p>Residents and businesses across Oudtshoorn, Ladismith, Calitzdorp, De Rust and the surrounding farms have traditionally relied on fast-moving WhatsApp groups to buy, sell, offer services and find local opportunities. While these groups are vibrant, posts vanish quickly, there is no meaningful search, and reach is limited to whoever is in the group at that exact moment.</p>

<p>VolstruisGids solves this by offering a clean, permanent, mobile-first marketplace built specifically for the Klein Karoo. Key features include:</p>

<ul>
    <li><strong>Free personal classifieds</strong> — one active listing at a time for everyone, no cost to start</li>
    <li><strong>Professional business storefronts</strong> — local businesses can present a branded presence with all their listings in one place</li>
    <li><strong>Searchable across the region</strong> — buyers in any town can discover relevant offers without being in the right WhatsApp group</li>
    <li><strong>Share-to-earn credits</strong> — community members earn credits by sharing listings, which can be used for promotions and visibility boosts</li>
    <li><strong>Private messaging</strong> — safe, in-app contact that protects personal details until the seller chooses to share them</li>
</ul>

<p>"VolstruisGids is not another generic classifieds site," said founder Eben. "It is practical infrastructure for keeping economic activity visible and local. When a farmer in Zoar can reliably find a buyer in Oudtshoorn, or a tradesperson in Ladismith gets discovered by someone in Calitzdorp, real local growth happens."</p>

<p>The platform is live today at VolstruisGids and optimised for both mobile use and search visibility. Every listing benefits from clean structure that helps Google surface local results over time.</p>

<p>Journalists, community organisations and potential partners are invited to explore the platform and reach out for interviews, asset packs or collaboration discussions.</p>

<p class="mb-0"><strong>For media enquiries:</strong><br>
WhatsApp: +27 81 076 3237<br>
Or use the in-app messaging after registering.</p>
"""
    }
]
