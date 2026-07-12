from common.agentsysperf.models import SLOConfig
from common.agentsysperf.sla import evaluate_slo


def test_slo_pass_when_all_within_thresholds():
    slo = SLOConfig(p95_latency_ms_max=2000, min_success_rate=0.5, max_cost_per_task_usd=1.0)
    result = evaluate_slo(slo, p95_latency_ms=1500, success_rate=0.8, cost_per_completed_task_usd=0.4)
    assert result.passed is True
    assert result.failure_reasons == []
    assert result.status == "pass"


def test_slo_fail_on_latency():
    slo = SLOConfig(p95_latency_ms_max=1000)
    result = evaluate_slo(slo, p95_latency_ms=1500, success_rate=None)
    assert result.passed is False
    assert any("exceeds threshold" in r for r in result.failure_reasons)
    assert result.status == "fail"


def test_slo_fail_on_success_rate():
    slo = SLOConfig(min_success_rate=0.9)
    result = evaluate_slo(slo, p95_latency_ms=None, success_rate=0.5)
    assert result.passed is False
    assert any("success_rate" in r for r in result.failure_reasons)


def test_slo_fail_on_cost():
    slo = SLOConfig(max_cost_per_task_usd=0.1)
    result = evaluate_slo(slo, p95_latency_ms=None, success_rate=None, cost_per_completed_task_usd=0.5)
    assert result.passed is False


def test_slo_missing_data_reported_as_failure_reason():
    slo = SLOConfig(p95_latency_ms_max=1000)
    result = evaluate_slo(slo, p95_latency_ms=None, success_rate=None)
    assert result.passed is False
    assert "p95_loop_latency_unavailable" in result.failure_reasons


def test_slo_no_thresholds_always_passes():
    slo = SLOConfig()
    result = evaluate_slo(slo, p95_latency_ms=None, success_rate=None, cost_per_completed_task_usd=None)
    assert result.passed is True
    assert result.as_dict()["slo_failure_reason"] is None
