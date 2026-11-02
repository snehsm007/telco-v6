from types import SimpleNamespace

import cxas_app.tools.file_warranty_claim.python_function.python_code as tool


def _logged_in(**extra) -> SimpleNamespace:
    state = {"account_id": "A1001", "phone_last4": "0186", "auth_status": "pass", "logged_in": True}
    state.update(extra)
    return SimpleNamespace(state=state)


def test_file_warranty_claim_checks_then_files(monkeypatch) -> None:
    session = _logged_in()
    monkeypatch.setattr(tool, "context", session, raising=False)
    check = tool.file_warranty_claim(device="Pixel", issue="microphone dead")
    assert check["status"] == "ok"
    assert check["data"]["claim_filed"] is False
    assert check["data"]["device_model"]
    claim = tool.file_warranty_claim(device="Pixel", issue="microphone dead", physical_damage=False, water_damage="false")
    assert claim["status"] == "ok"
    assert claim["data"]["claim_id"].startswith("WC-")
    assert claim["data"]["replacement_eta_display"]
    assert session.state["sales_claims"] == claim["data"]["claim_id"]


def test_file_warranty_claim_needs_login_but_gives_safety_advice(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", SimpleNamespace(state={"language": "fr-CA"}), raising=False)
    reply = tool.file_warranty_claim(issue="batterie gonflée")
    assert reply["error"] == "NOT_LOGGED_IN"
    assert reply["data"]["safety_advice_key"] == "battery_safety"
    assert "sécurité" in reply["data"]["safety_advice"]


def test_file_warranty_claim_without_a_session() -> None:
    assert tool.file_warranty_claim(issue="screen flickers")["error"] == "NOT_LOGGED_IN"


def test_file_warranty_claim_water_damage_not_covered(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", _logged_in(), raising=False)
    reply = tool.file_warranty_claim(device="iPhone", issue="won't turn on", physical_damage="no", water_damage="yes")
    assert reply["error"] == "NOT_ELIGIBLE"
    assert reply["data"]["repair_options"]
