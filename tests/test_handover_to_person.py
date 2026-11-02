import json
from types import SimpleNamespace

import cxas_app.tools.handover_to_person.python_function.python_code as tool
from lib.fakes import SPOKEN_LINES


def test_handover_to_person_sets_state_and_returns_message(monkeypatch) -> None:
    session = SimpleNamespace(state={"account_id": "A1001", "language": "fr-CA"})
    monkeypatch.setattr(tool, "context", session, raising=False)
    reply = tool.handover_to_person(reason="besoin d'aide", language="fr-CA")
    assert reply["status"] == "ok"
    assert reply["data"]["queue"] == "general"
    assert reply["data"]["handoff_status"] == "completed_via_specialist_queue"
    assert reply["data"]["language"] == "fr-CA"
    assert session.state["handover_complete"] is True
    assert session.state["handoff_message"] == SPOKEN_LINES["live_agent_handoff"]["fr-CA"]
    assert json.loads(session.state["handoff_context"])["reason"] == "user_requested_agent"


def test_handover_fraud_business_and_refund_lines(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", {}, raising=False)
    fraud = tool.handover_to_person(reason="fraud_escalation", summary="SIM swapped", language="en-US")
    assert fraud["handoff_message"] == (
        SPOKEN_LINES["empathy_protocol"]["en-US"] + " " + SPOKEN_LINES["live_agent_handoff"]["en-US"]
    )
    monkeypatch.setattr(tool, "context", {}, raising=False)
    business = tool.handover_to_person(reason="business_handoff", language="fr-CA")
    assert business["handoff_message"] == SPOKEN_LINES["business_handoff"]["fr-CA"]
    monkeypatch.setattr(tool, "context", {}, raising=False)
    refund = tool.handover_to_person(reason="refund_threshold_exceeded", language="fr-CA")
    assert refund["handoff_message"] == (
        SPOKEN_LINES["refund_over_limit"]["fr-CA"].replace("[limit]", tool.display_amount(tool.SELF_SERVE_ADJUSTMENT_LIMIT))
        + " "
        + SPOKEN_LINES["transfer_to_specialist"]["fr-CA"]
    )


def test_handover_without_a_session_detects_turn_one_french(monkeypatch) -> None:
    monkeypatch.setattr(tool, "context", None, raising=False)
    reply = tool.handover_to_person(reason="user_requested_agent", summary="Je veux parler à quelqu'un")
    assert reply["data"]["language"] == "fr-CA"
