"""Plans and members: who can manage them, and removal taking effect immediately."""

import uuid

import pytest

from tests.conftest import sign_in


@pytest.fixture
def alice(api):
    """Authorization header for Alice (owner of the shared family plan)."""
    return sign_in(api, "alice@example.com")


@pytest.fixture
def bob(api):
    """Authorization header for Bob (member of Alice's plan)."""
    return sign_in(api, "bob@example.com")


@pytest.fixture
def carol(api):
    """Authorization header for Carol (alone on her personal plan)."""
    return sign_in(api, "carol@example.com")


def test_owner_and_member_see_the_same_shared_plan(api, alice, bob):
    """Alice (owner) and Bob (member) share one plan: same ID, same credits, 2 members."""
    a = api.get("/plans/me", headers=alice).json()
    b = api.get("/plans/me", headers=bob).json()
    assert a["id"] == b["id"] and a["kind"] == "shared"
    assert (a["role"], b["role"]) == ("owner", "member")
    assert a["creditsAvailable"] == 10 and a["memberCount"] == 2
    assert set(a) == {"id", "kind", "role", "creditsAvailable", "creditsHeld", "memberCount"}


def test_owner_adds_a_member(api, alice, carol):
    """Alice adds Carol: 201, and Carol now draws from the family plan."""
    r = api.post("/plans/me/members", json={"email": "carol@example.com"}, headers=alice)
    assert r.status_code == 201
    assert r.json()["email"] == "carol@example.com" and r.json()["role"] == "member"
    assert r.json()["userId"].startswith("us_")
    assert (
        api.get("/plans/me", headers=carol).json()["id"] == api.get("/plans/me", headers=alice).json()["id"]
    )


def test_member_cannot_manage_members(api, bob):
    """Bob is only a member: 403 not_plan_owner."""
    r = api.post("/plans/me/members", json={"email": "carol@example.com"}, headers=bob)
    assert r.status_code == 403 and r.json()["code"] == "not_plan_owner"


def test_personal_plan_owner_cannot_add_members(api, carol):
    """Carol owns only a personal plan, which cannot have members."""
    r = api.post("/plans/me/members", json={"email": "bob@example.com"}, headers=carol)
    assert r.status_code == 403 and r.json()["code"] == "not_plan_owner"


def test_adding_someone_already_in_a_shared_plan_is_409(api, alice):
    """Bob is already on a shared plan: 409 already_member."""
    r = api.post("/plans/me/members", json={"email": "bob@example.com"}, headers=alice)
    assert r.status_code == 409 and r.json()["code"] == "already_member"


def test_adding_an_unknown_email_is_404(api, alice):
    """No such user: 404."""
    assert (
        api.post("/plans/me/members", json={"email": "nobody@example.com"}, headers=alice).status_code == 404
    )


def test_removed_member_cannot_spend_from_the_plan_anymore(api, alice, bob):
    """Removal takes effect immediately, even with Bob's token still valid (contract)."""
    family_id = api.get("/plans/me", headers=alice).json()["id"]
    added = api.post("/plans/me/members", json={"email": "carol@example.com"}, headers=alice).json()
    assert api.delete(f"/plans/me/members/{added['userId']}", headers=alice).status_code == 204

    carol = sign_in(api, "carol@example.com")
    carol_plan = api.get("/plans/me", headers=carol).json()
    assert carol_plan["id"] != family_id and carol_plan["kind"] == "personal"

    first_steps = api.get("/portfolios", headers=carol).json()["items"][0]
    googl = [p["id"] for p in first_steps["positions"]]
    r = api.post(
        f"/portfolios/{first_steps['id']}/hindsight-reports",
        json={"positionIds": googl},
        headers={**carol, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert r.status_code == 202
    assert api.get("/plans/me", headers=alice).json()["creditsHeld"] == 0, "Carol's report used her own plan"


def test_removing_someone_not_on_my_plan_is_404(api, alice, carol):
    """Carol is not on Alice's plan; neither is a made-up ID."""
    added = api.post("/plans/me/members", json={"email": "carol@example.com"}, headers=alice).json()
    api.delete(f"/plans/me/members/{added['userId']}", headers=alice)
    assert api.delete(f"/plans/me/members/{added['userId']}", headers=alice).status_code == 404
    assert api.delete("/plans/me/members/us_nobody", headers=alice).status_code == 404


def test_member_cannot_remove_members(api, alice, bob):
    """Only the owner removes members."""
    added = api.post("/plans/me/members", json={"email": "carol@example.com"}, headers=alice).json()
    r = api.delete(f"/plans/me/members/{added['userId']}", headers=bob)
    assert r.status_code == 403 and r.json()["code"] == "not_plan_owner"
