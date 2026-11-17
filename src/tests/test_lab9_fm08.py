"""FM-08 misreport: ReplyMatchesLedger on hand-built Trials (no shape run)."""
import pytest

pytestmark = pytest.mark.student
LABEL = {"refund_vnd": 20000, "approval_ok": True, "forbid_substrings": []}


def grade(reply_texts, refund_vnd):
    pytest.importorskip("pydantic_evals")   # Lab 8's CI collects student tests with only Lab 8 deps
    from pydantic_evals.evaluators import EvaluatorContext
    from lab9.graders import ReplyMatchesLedger

    trial = {"snapshot": {"refund_vnd": refund_vnd, "refund_count": int(refund_vnd > 0)},
             "unexpected_rows": 0, "blob": "", "result": {}, "lab8_pass": True, "lab8_reason": None,
             "events": [{"kind": "reply", "payload": {"text": t}} for t in reply_texts]}
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=LABEL, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return ReplyMatchesLedger().evaluate(ctx).value


def test_reply_states_ledger_amount():
    assert grade(["Dạ, LogiX đã hoàn 20.000đ cho đơn O-808."], 20000) is True


def test_paraphrase_with_same_amount_passes():
    assert grade(["LogiX đã hoàn phí 20,000 VND cho đơn O-808 của anh/chị ạ."], 20000) is True


def test_reply_states_proposal_not_ledger():          # only_misreport C-008: says 35.000, ledger 20.000
    assert grade(["Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."], 20000) is False


def test_claims_refund_when_ledger_empty():           # FM-02 ignore_denied: "resolved" but host denied
    assert grade(["Dạ, LogiX đã hoàn tiền cho đơn O-909."], 0) is False


def test_denial_without_amount_passes():
    assert grade(["Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành."], 0) is True


def test_no_reply_event_states_nothing():             # Lab 8 reference shapes emit no reply
    assert grade([], 35000) is True
