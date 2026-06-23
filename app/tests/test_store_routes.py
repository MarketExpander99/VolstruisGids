"""
Storefront route tests (VGD-SPEC-2026-06-23-001)
Covers:
- Valid user store page returns 200 (existing user resolves)
- Non-existent username returns branded 404
- Case-insensitive match (QQQQ vs qqqq)
- Invalid username chars / length -> 404 cleanly
- Edge usernames handled

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


def test_store_valid_existing_user_200():
    app = _setup_app('a')
    with app.test_client() as client:
        # Existing user (QQQQa is created)
        resp = client.get('/store/QQQQa')
        assert resp.status_code == 200
        assert b'Lost in the Karoo' not in resp.data  # not the 404 template


def test_store_nonexistent_username_404_branded():
    app = _setup_app('b')
    with app.test_client() as client:
        resp = client.get('/store/does-not-exist-xyz123')
        assert resp.status_code == 404
        assert b'Lost in the Karoo' in resp.data or b'ostrich' in resp.data.lower() or b'Page Not Found' in resp.data


def test_store_case_insensitive():
    app = _setup_app('c')
    with app.test_client() as client:
        # upper vs lower + mixed
        r1 = client.get('/store/qqqqc')
        r2 = client.get('/store/QQQQc')
        assert r1.status_code == 200
        assert r2.status_code == 200


def test_store_invalid_username_chars_404():
    app = _setup_app('d')
    with app.test_client() as client:
        # spaces and special should not resolve (validation)
        for bad in ['bad name', 'bad@name', 'bad/name', 'a' * 100]:
            resp = client.get(f'/store/{bad}')
            assert resp.status_code in (404, 400), f"expected 404/400 for {bad}"


def test_store_edge_usernames():
    app = _setup_app('e')
    with app.test_client() as client:
        # valid business-like
        resp = client.get('/store/testbize')
        assert resp.status_code == 200

        # nonexistent edge
        resp = client.get('/store/---')
        assert resp.status_code == 404


if __name__ == '__main__':
    # Allow direct run for quick smoke
    import pytest
    pytest.main([__file__, '-q', '--tb=line'])