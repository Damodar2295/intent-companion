import pytest

from agent.context.models import ContextRequest
from agent.context.service import ContextBuilder, estimate


def req(**changes):
    base = {
        "customer_id": "cust-dining",
        "consent": {"allowed": True},
        "messages": [
            {"role": "system", "content": "You are a grounded assistant. Use evidence only.", "priority": 100},
            {"role": "user", "content": "Find dinner in Rome.", "evidence_ids": ["e1"]},
            {"role": "assistant", "content": "Earlier answer with no new facts."},
            {"role": "user", "content": "Keep the museum stop too.", "evidence_ids": ["e2"]},
        ],
        "evidence": [
            {"role": "tool", "content": "Restaurant source fact.", "evidence_ids": ["e1"]},
            {"role": "tool", "content": "Unreferenced secret.", "evidence_ids": ["other"]},
        ],
        **changes,
    }
    return ContextRequest(**base)


def test_budget_prunes_old_messages_and_unreferenced_evidence():
    result = ContextBuilder().build(
        req(
            token_budget=128,
            debug=True,
            messages=[
                {"role": "system", "content": "grounding rules", "priority": 100},
                {"role": "user", "content": "old detail " * 200, "priority": 0},
                {"role": "user", "content": "latest fact", "priority": 90},
            ],
        )
    )
    assert result.status == "PARTIAL"
    assert all("secret" not in m.content for m in result.messages)
    assert result.estimated_tokens <= result.token_budget
    assert result.diagnostics["dropped_messages"] >= 0


def test_evidence_requires_explicit_reference():
    result = ContextBuilder().build(req())
    assert any("Restaurant source" in m.content for m in result.messages)
    assert all("secret" not in m.content for m in result.messages)


def test_system_message_is_preserved_and_truncates_if_needed():
    long = "system guidance " * 700
    result = ContextBuilder().build(
        req(messages=[{"role": "system", "content": long, "priority": 100}], token_budget=128)
    )
    assert result.messages[0].role == "system"
    assert result.estimated_tokens <= 128
    assert result.warnings


def test_latest_messages_are_preferred():
    result = ContextBuilder().build(
        req(
            messages=[
                {"role": "system", "content": "system", "priority": 100},
                {"role": "user", "content": "old " * 100, "priority": 0},
                {"role": "user", "content": "latest fact", "priority": 90},
            ],
            token_budget=128,
        )
    )
    assert any("latest fact" in m.content for m in result.messages)


def test_estimate_positive():
    assert estimate("") == 1 and estimate("one two") >= 2


def test_request_limits():
    with pytest.raises(ValueError):
        ContextRequest(customer_id="x", consent={"allowed": True}, messages=[], token_budget=128)
