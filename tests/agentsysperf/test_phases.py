from common.agentsysperf.models import PhaseTiming
from common.agentsysperf.phases import aggregate_phases, infer_phase_shares_from_mean_latency


def test_aggregate_phases_all_measured():
    samples = [
        PhaseTiming(admit_ms=10, retrieve_ms=20, act_ms=100, decision_ms=50, commit_ms=15),
        PhaseTiming(admit_ms=12, retrieve_ms=22, act_ms=110, decision_ms=55, commit_ms=17),
    ]
    result = {p.phase: p for p in aggregate_phases(samples)}
    assert result["admit"].source == "measured"
    assert result["admit"].mean_ms == 11.0
    assert result["act"].p95_ms is not None


def test_aggregate_phases_partial_missing_data():
    samples = [
        PhaseTiming(admit_ms=10, retrieve_ms=None, act_ms=100, decision_ms=None, commit_ms=15),
        PhaseTiming(admit_ms=12, retrieve_ms=None, act_ms=110, decision_ms=None, commit_ms=17),
    ]
    result = {p.phase: p for p in aggregate_phases(samples)}
    assert result["admit"].source == "measured"
    assert result["retrieve"].source == "unavailable"
    assert result["retrieve"].mean_ms is None
    assert result["retrieve"].reason is not None


def test_aggregate_phases_inferred_fallback():
    shares = infer_phase_shares_from_mean_latency(1000.0)
    result = {p.phase: p for p in aggregate_phases([], inferred_from_total=shares)}
    for phase in ("admit", "retrieve", "act", "decision", "commit"):
        assert result[phase].source == "inferred"
        assert result[phase].mean_ms is not None
        assert result[phase].reason is not None


def test_infer_phase_shares_none_when_no_latency():
    assert infer_phase_shares_from_mean_latency(None) is None


def test_aggregate_phases_no_data_no_inference():
    result = {p.phase: p for p in aggregate_phases([])}
    for phase in ("admit", "retrieve", "act", "decision", "commit"):
        assert result[phase].source == "unavailable"
        assert result[phase].mean_ms is None
