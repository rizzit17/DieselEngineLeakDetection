"""
test_api.py — Integration tests for REST API endpoints.

Covers authentication, predict, batch session analysis, and health check.
Requires Django DB (pytest-django handles test database setup).

Run:  pytest tests/test_api.py -v
"""
import io
import csv
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BACKEND_ROOT = _PROJECT_ROOT / "backend" / "diesel_engine_predictor"
for _p in (_PROJECT_ROOT, _BACKEND_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from config.constants import SENSOR_COLS
from ml_model.data_gen.engine_simulator_core import EngineSimulator

# A valid 12-channel payload built from realistic operating values
_VALID_PAYLOAD = {
    "rpm": 1600.0,
    "fuel_rate": 75.0,
    "turbo_speed": 90000.0,
    "boost_pressure": 1.4,
    "MAP": 2.3,
    "IAT": 305.0,
    "MAF": 520.0,
    "EGT": 680.0,
    "exhaust_pressure": 2.6,
    "VGT": 48.0,
    "DPF_delta": 22000.0,
    "ambient_pressure": 1.01,
}


def _make_user(username="testuser", password=None):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    pass_val = password or f"mock_secret_{username}"
    return User.objects.create_user(username=username, password=pass_val, email=f"{username}@test.com")


def _get_token(user):
    from rest_framework.authtoken.models import Token
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


def _authed_client(token_key: str):
    from rest_framework.test import APIClient
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token_key}")
    return client


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_signup_creates_user_and_returns_token() -> None:
    from rest_framework.test import APIClient
    user_pass = "mock_pass_newuser"
    resp = APIClient().post(
        "/user_auth/signup/",
        {"username": "newuser", "password": user_pass, "email": "new@test.com"},
        format="json",
    )
    assert resp.status_code == 201
    assert "token" in resp.data


@pytest.mark.django_db
def test_login_with_valid_credentials_returns_token() -> None:
    from rest_framework.test import APIClient
    user_pass = "mock_pass_loginuser"
    _make_user(username="loginuser", password=user_pass)
    resp = APIClient().post(
        "/user_auth/login/",
        {"username": "loginuser", "password": user_pass},
        format="json",
    )
    assert resp.status_code == 200
    assert "token" in resp.data


@pytest.mark.django_db
def test_login_with_wrong_password_returns_401() -> None:
    from rest_framework.test import APIClient
    correct_pass = "mock_pass_correct"
    wrong_pass = "mock_pass_wrong"
    _make_user(username="badlogin", password=correct_pass)
    resp = APIClient().post(
        "/user_auth/login/",
        {"username": "badlogin", "password": wrong_pass},
        format="json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_logout_invalidates_token() -> None:
    user = _make_user(username="logoutuser")
    token = _get_token(user)
    client = _authed_client(token)
    resp = client.post("/user_auth/logout/")
    assert resp.status_code == 200
    # Second logout with the same (now-deleted) token should fail
    resp2 = client.post("/user_auth/logout/")
    assert resp2.status_code in {401, 403}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_health_check_returns_ok() -> None:
    from rest_framework.test import APIClient
    resp = APIClient().get("/user_auth/health/")
    assert resp.status_code == 200
    assert resp.data["status"] == "ok"


# ---------------------------------------------------------------------------
# Predict endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_predict_requires_auth() -> None:
    from rest_framework.test import APIClient
    resp = APIClient().post("/api/predict", _VALID_PAYLOAD, format="json")
    assert resp.status_code in {401, 403}


@pytest.mark.django_db
def test_predict_with_missing_channels_returns_400() -> None:
    user = _make_user(username="partial")
    client = _authed_client(_get_token(user))
    resp = client.post("/api/predict", {"rpm": 1600.0}, format="json")
    assert resp.status_code == 400
    assert "missing" in str(resp.data).lower() or "error" in resp.data


@pytest.mark.django_db
def test_predict_with_valid_payload_returns_200() -> None:
    user = _make_user(username="predictuser")
    client = _authed_client(_get_token(user))
    resp = client.post("/api/predict", _VALID_PAYLOAD, format="json")
    assert resp.status_code == 200


@pytest.mark.django_db
def test_predict_response_has_five_section_structure() -> None:
    user = _make_user(username="structuser")
    client = _authed_client(_get_token(user))
    resp = client.post("/api/predict", _VALID_PAYLOAD, format="json")
    assert resp.status_code == 200
    for key in ("steady_state", "detection", "isolation", "decision", "metadata"):
        assert key in resp.data, f"Missing top-level key: {key}"
    assert resp.data["decision"]["flag"] in {"PASS", "WARNING", "FAIL"}


# ---------------------------------------------------------------------------
# Batch session endpoint
# ---------------------------------------------------------------------------

def _generate_csv(n_rows: int = 20, seed: int = 77) -> bytes:
    sim = EngineSimulator(seed=seed)
    for _ in range(60):
        sim.step()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=SENSOR_COLS)
    writer.writeheader()
    for _ in range(n_rows):
        writer.writerow(sim.step())
    return buf.getvalue().encode()


@pytest.mark.django_db
@pytest.mark.slow
def test_batch_with_valid_csv_returns_go_no_go() -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile
    user = _make_user(username="batchuser")
    client = _authed_client(_get_token(user))
    csv_file = SimpleUploadedFile("session.csv", _generate_csv(20), content_type="text/csv")
    resp = client.post("/api/session/", {"file": csv_file}, format="multipart")
    assert resp.status_code == 200
    assert "header" in resp.data
    assert resp.data["header"]["go_nogo"] in {"GO", "CAUTION", "NO-GO"}


@pytest.mark.django_db
def test_batch_with_missing_columns_returns_400() -> None:
    from django.core.files.uploadedfile import SimpleUploadedFile
    user = _make_user(username="badcsv")
    client = _authed_client(_get_token(user))
    bad_csv = b"col_a,col_b\n1.0,2.0\n3.0,4.0\n"
    csv_file = SimpleUploadedFile("bad.csv", bad_csv, content_type="text/csv")
    resp = client.post("/api/session/", {"file": csv_file}, format="multipart")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_batch_requires_auth() -> None:
    from rest_framework.test import APIClient
    from django.core.files.uploadedfile import SimpleUploadedFile
    csv_file = SimpleUploadedFile("test.csv", _generate_csv(5), content_type="text/csv")
    resp = APIClient().post("/api/session/", {"file": csv_file}, format="multipart")
    assert resp.status_code in {401, 403}
