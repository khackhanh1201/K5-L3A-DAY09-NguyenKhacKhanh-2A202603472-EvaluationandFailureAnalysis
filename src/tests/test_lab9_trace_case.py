"""Regression case from docs/trace_case.md: FM-03 ticket_trust on C-002 (ticket 5 days, DB 2 days).

The first wrong step is a `model_override` event that replaces the DB's delay_days with the
ticket's. These tests replay the trial with MockLLM and assert on that step and on the ledger.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
SRC = Path(__file__).resolve().parents[1]


@pytest.fixture
def case(monkeypatch):
    # Lab 8's ci.yml runs `-m student -k swarm` with only Lab 8 deps; the eval-gate job has them.
    pytest.importorskip("pydantic_evals")
    monkeypatch.chdir(SRC)   # investigate() reads data/ relative to src/
    from lab9.trace_case import investigate

    return investigate


def first_override(trial):
    for i, e in enumerate(trial["events"], 1):
        if e.get("kind") == "model_override":
            return i, e["payload"]
    return None, None


@pytest.mark.parametrize("shape,seed", [("swarm", 55), ("seeded_regression", 11)])
def test_c002_ticket_trust_is_caught(case, shape, seed):
    c = case(shape, "C-002", seed)
    t = c["trial"]
    step, payload = first_override(t)
    assert step is not None and payload == {"delay_days": 5}     # first wrong step: ticket beats DB
    assert t["snapshot"]["refund_vnd"] != c["label"]["refund_vnd"]  # money moved on a denied claim
    assert not t["lab8_pass"]


@pytest.mark.parametrize("shape,seed", [("fixed", 11), ("fixed", 55), ("swarm", 11)])
def test_c002_db_fact_kept_when_fixed(case, shape, seed):
    c = case(shape, "C-002", seed)
    t = c["trial"]
    assert first_override(t) == (None, None)
    assert t["snapshot"]["refund_vnd"] == c["label"]["refund_vnd"] == 0
    assert t["result"]["status"] == "denied"
    assert t["lab8_pass"]
