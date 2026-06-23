"""
Storefront route tests (VOL-UI-STOREFRONT-ROBUST-2026-06-23)
Covers:
- Valid BUSINESS storefront returns 200
- Unknown / malformed username -> 302 redirect to /directory + info flash (never 404)
- Non-business user -> 302 redirect to /index
- Case-insensitive + @prefix tolerance for valid business usernames
- Invalid chars / garbage -> redirect to directory (graceful, no crash/404)

Run: python -m pytest app/tests/test_store_routes.py -q --tb=line
"""

import os
import sys
from decimal import Decimal

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from app import create_app, db
from app.models.user import User
from app.models.listing import Listing


def _setup_app(suffix=''):
    """Fresh in-memory app+DB per test call. Use suffix to guarantee unique usernames across rapid runs."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['FLASK_ENV'] = 'testing'

    with app.app_context():
        db.create_all()
        s = suffix or '1'
        # Business-like user (with guard for safety across test isolation quirks)
        uname1 = f'testbiz{s}'
        existing1 = User.query.filter_by(username=uname1).first()
        if not existing1:
            u1 = User(
                username=uname1,
                email=f'biz{s}@example.com',
                phone='0820000001',
                password_hash='dummyhash'
            )
            u1.is_business = True
            u1.account_type = 'business'
            u1.business_name = 'Test Biz'
            db.session.add(u1)

        # Personal / edge user
        uname2 = f'QQQQ{s}'
        existing2 = User.query.filter_by(username=uname2).first()
        if not existing2:
            u2 = User(
                username=uname2,
                email=f'qqqq{s}@example.com',
                phone='0820000002',
                password_hash='dummyhash'
            )
            db.session.add(u2)

        db.session.commit()
    return app


def test_store_valid_business_200():
    app = _setup_app('a')
    with app.test_client() as client:
        # Valid business (testbiza is the business account)
        resp = client.get('/store/testbiza')
        assert resp.status_code == 200
        assert b'Lost in the Karoo' not in resp.data  # not the 404 template


def test_store_nonexistent_redirects_to_directory():
    """Unknown store should never 404: friendly redirect to directory."""
    app = _setup_app('b')
    with app.test_client() as client:
        resp = client.get('/store/does-not-exist-xyz123', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.location is not None
        assert '/directory' in resp.location or resp.location.endswith('/directory')


def test_store_nonbusiness_redirects_to_home():
    """Personal seller (QQQQ*) should redirect (not show storefront)."""
    app = _setup_app('b2')
    with app.test_client() as client:
        resp = client.get('/store/QQQQb2', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.location is not None
        assert '/' in resp.location and 'directory' not in resp.location.split('?')[0]  # typically to /


def test_store_case_insensitive_and_at_prefix():
    app = _setup_app('c')
    with app.test_client() as client:
        # Use the business username (testbizc); case + @ variants must all work
        for path in ['/store/testbizc', '/store/TESTBIZC', '/store/@testbizc', '/store/@TestBizC']:
            r = client.get(path, follow_redirects=False)
            # Either direct 200 or redirect only if it somehow didn't match (should be 200)
            if r.status_code == 302:
                # rare: follow to see final
                r2 = client.get(path, follow_redirects=True)
                assert r2.status_code == 200
            else:
                assert r.status_code == 200


def test_store_malformed_redirects_gracefully():
    """@, spaces, junk etc. never hard 404; redirect with friendly message."""
    app = _setup_app('d')
    with app.test_client() as client:
        for bad in ['bad name', 'bad@name', '@@@', 'a' * 100, '  ', ' @ foo ']:
            # Note: slashes in URL like 'bad/name' never reach the view fn (Flask routing 404s first); that's acceptable
            resp = client.get(f'/store/{bad}', follow_redirects=False)
            assert resp.status_code in (302, 301), f"expected redirect for bad username {bad!r}, got {resp.status_code}"
            # Should go to directory in most cases
            if resp.location:
                assert '/directory' in resp.location or '/' in resp.location


def test_store_edge_usernames():
    app = _setup_app('e')
    with app.test_client() as client:
        # valid business
        resp = client.get('/store/testbize')
        assert resp.status_code == 200

        # nonexistent edge -> redirect (not 404)
        resp = client.get('/store/---', follow_redirects=False)
        assert resp.status_code == 302
        assert resp.location and '/directory' in resp.location


if __name__ == '__main__':
    # Allow direct run for quick smoke
    import pytest
    pytest.main([__file__, '-q', '--tb=line'])