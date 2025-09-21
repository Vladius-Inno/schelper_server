import os
import asyncio
import pathlib

from fastapi.testclient import TestClient


def get_client():
    # Use a temporary sqlite file DB for tests
    db_path = pathlib.Path("./test.db")
    if db_path.exists():
        db_path.unlink()
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
    from app.main import app  # import after env is set
    return TestClient(app)


def register(client: TestClient, name: str, email: str, password: str, role: str):
    resp = client.post(
        "/auth/register",
        json={"name": name, "email": email, "password": password, "role": role},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def login(client: TestClient, email: str, password: str):
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_register_login_me():
    with get_client() as client:
        reg = register(client, "Ivan", "ivan@example.com", "password123", "child")
        assert reg["role"] == "child"
        tokens = login(client, "ivan@example.com", "password123")
        assert "token" in tokens and "refresh_token" in tokens

        headers = {"Authorization": f"Bearer {tokens['token']}"}
        me = client.get("/users/me", headers=headers)
        assert me.status_code == 200
        data = me.json()
        assert data["email"] == "ivan@example.com"
        assert data["role"] == "child"


def test_admin_access_and_link():
    with get_client() as client:
        # Create admin, parent, child
        reg_admin = register(client, "Admin", "admin@example.com", "adminpass", "admin")
        reg_parent = register(client, "Parent", "parent@example.com", "parentpass", "parent")
        reg_child = register(client, "Child", "child@example.com", "childpass", "child")

        admin_tokens = login(client, "admin@example.com", "adminpass")

        # Admin can list users
        headers_admin = {"Authorization": f"Bearer {admin_tokens['token']}"}
        resp = client.get("/users/", headers=headers_admin)
        assert resp.status_code == 200
        assert len(resp.json()) >= 3

        # Non-admin cannot list users
        parent_tokens = login(client, "parent@example.com", "parentpass")
        headers_parent = {"Authorization": f"Bearer {parent_tokens['token']}"}
        resp = client.get("/users/")
        assert resp.status_code == 401  # missing auth
        resp = client.get("/users/", headers=headers_parent)
        assert resp.status_code == 403

        # Parent links themselves to child
        link_payload = {
            "parent_id": reg_parent["id"],
            "child_id": reg_child["id"],
            "relation_type": "father",
        }
        link_resp = client.post("/users/link", json=link_payload, headers=headers_parent)
        assert link_resp.status_code == 200
        assert link_resp.json()["status"] == "linked"
