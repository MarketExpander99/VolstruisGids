from flask import Blueprint, make_response, url_for
from app.models.listing import Listing
from . import sitemap_bp
from datetime import datetime

@sitemap_bp.route('/sitemap.xml')
def sitemap():
    """
    Dynamic XML sitemap for Google.
    Includes homepage + all active listings.
    """
    pages = []

    # Homepage
    pages.append({
        'loc': url_for('main.index', _external=True),
        'lastmod': datetime.utcnow().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '1.0'
    })

    # Important static pages (SEO)
    for static_path, changefreq, priority in [
        ('main.how_it_works', 'monthly', '0.7'),
        ('main.press', 'weekly', '0.6'),
        ('main.terms', 'yearly', '0.3'),
        ('main.privacy', 'yearly', '0.3'),
        ('main.guidelines', 'yearly', '0.4'),
    ]:
        try:
            pages.append({
                'loc': url_for(static_path, _external=True),
                'lastmod': datetime.utcnow().strftime('%Y-%m-%d'),
                'changefreq': changefreq,
                'priority': priority
            })
        except Exception:
            pass  # in case route not registered yet

    # All currently public (non-expired + active) listings only
    listings = Listing.active_query().order_by(Listing.created_at.desc()).all()

    for listing in listings:
        pages.append({
            'loc': url_for('listings.detail', listing_id=listing.id, _external=True),
            'lastmod': listing.created_at.strftime('%Y-%m-%d') if listing.created_at else datetime.utcnow().strftime('%Y-%m-%d'),
            'changefreq': 'weekly',
            'priority': '0.8'
        })

    # Build XML
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for page in pages:
        xml += '  <url>\n'
        xml += f'    <loc>{page["loc"]}</loc>\n'
        xml += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        xml += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
        xml += '  </url>\n'

    xml += '</urlset>'

    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response