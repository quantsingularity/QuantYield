"""
QuantYield -- Auth API tests

Covers:
    POST /api/v1/auth/register/
    POST /api/v1/auth/token/
    POST /api/v1/auth/token/refresh/
    GET  /api/v1/auth/me/
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

REGISTER_URL = "/api/v1/auth/register/"
TOKEN_URL = "/api/v1/auth/token/"
TOKEN_REFRESH_URL = "/api/v1/auth/token/refresh/"
ME_URL = "/api/v1/auth/me/"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def registered_user(db):
    """A user registered via the API (username == email)."""
    u = User.objects.create_user(
        username="alice@example.com",
        email="alice@example.com",
        password="securepass99",
        first_name="Alice",
        last_name="Smith",
    )
    return u


# ── Register ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestRegister:
    def test_register_success(self, client):
        res = client.post(
            REGISTER_URL,
            {
                "email": "bob@example.com",
                "password": "securepass99",
                "first_name": "Bob",
                "last_name": "Jones",
            },
            format="json",
        )
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == "bob@example.com"
        assert data["first_name"] == "Bob"
        assert "password" not in data
        assert User.objects.filter(email="bob@example.com").exists()

    def test_register_duplicate_email_rejected(self, client, registered_user):
        res = client.post(
            REGISTER_URL,
            {
                "email": "alice@example.com",
                "password": "anotherpass99",
            },
            format="json",
        )
        assert res.status_code == 400
        assert "email" in res.json()

    def test_register_short_password_rejected(self, client):
        res = client.post(
            REGISTER_URL,
            {
                "email": "charlie@example.com",
                "password": "short",
            },
            format="json",
        )
        assert res.status_code == 400
        assert "password" in res.json()

    def test_register_missing_email_rejected(self, client):
        res = client.post(REGISTER_URL, {"password": "securepass99"}, format="json")
        assert res.status_code == 400
        assert "email" in res.json()

    def test_register_missing_password_rejected(self, client):
        res = client.post(REGISTER_URL, {"email": "dave@example.com"}, format="json")
        assert res.status_code == 400
        assert "password" in res.json()


# ── Token obtain ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTokenObtain:
    def test_obtain_token_success(self, client, registered_user):
        res = client.post(
            TOKEN_URL,
            {
                "email": "alice@example.com",
                "password": "securepass99",
            },
            format="json",
        )
        assert res.status_code == 200
        data = res.json()
        assert "access" in data
        assert "refresh" in data

    def test_wrong_password_rejected(self, client, registered_user):
        res = client.post(
            TOKEN_URL,
            {
                "email": "alice@example.com",
                "password": "wrongpassword",
            },
            format="json",
        )
        assert res.status_code == 401

    def test_unknown_email_rejected(self, client):
        res = client.post(
            TOKEN_URL,
            {
                "email": "nobody@example.com",
                "password": "securepass99",
            },
            format="json",
        )
        assert res.status_code == 401

    def test_missing_fields_rejected(self, client):
        res = client.post(TOKEN_URL, {}, format="json")
        assert res.status_code == 400

    def test_inactive_user_rejected(self, client, registered_user):
        registered_user.is_active = False
        registered_user.save()
        res = client.post(
            TOKEN_URL,
            {
                "email": "alice@example.com",
                "password": "securepass99",
            },
            format="json",
        )
        assert res.status_code == 401


# ── Token refresh ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestTokenRefresh:
    def _get_refresh(self, client, registered_user):
        res = client.post(
            TOKEN_URL,
            {
                "email": "alice@example.com",
                "password": "securepass99",
            },
            format="json",
        )
        return res.json()["refresh"]

    def test_refresh_returns_new_access(self, client, registered_user):
        refresh = self._get_refresh(client, registered_user)
        res = client.post(TOKEN_REFRESH_URL, {"refresh": refresh}, format="json")
        assert res.status_code == 200
        assert "access" in res.json()

    def test_invalid_refresh_rejected(self, client):
        res = client.post(
            TOKEN_REFRESH_URL, {"refresh": "notavalidtoken"}, format="json"
        )
        assert res.status_code == 401


# ── Me ────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMe:
    def _auth_client(self, client, registered_user):
        res = client.post(
            TOKEN_URL,
            {
                "email": "alice@example.com",
                "password": "securepass99",
            },
            format="json",
        )
        token = res.json()["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return client

    def test_me_returns_profile(self, client, registered_user):
        authed = self._auth_client(client, registered_user)
        res = authed.get(ME_URL)
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "alice@example.com"
        assert data["first_name"] == "Alice"
        assert "profile" in data
        assert data["profile"]["role"] in ("Analyst", "Portfolio Manager")

    def test_me_unauthenticated_rejected(self, client):
        res = client.get(ME_URL)
        assert res.status_code == 401

    def test_me_invalid_token_rejected(self, client):
        client.credentials(HTTP_AUTHORIZATION="Bearer notavalidtoken")
        res = client.get(ME_URL)
        assert res.status_code == 401
