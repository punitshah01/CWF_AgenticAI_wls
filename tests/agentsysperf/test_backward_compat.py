"""
Backward-compatibility regression tests.

Proves that legacy results.csv / results.json produced by the existing
(pre-AgentSysPerf) pipeline still parse correctly, and that writing new
AgentSysPerf artifacts alongside them does not modify or remove any
existing columns/files.
"""

import json
from collections import OrderedDict

from common.csv_writer import write_csv_row
from common.json_results import ResultsJsonWriter
from common.agentsysperf.summary import build_run_summary, write_run_artifacts


def test_legacy_results_csv_still_parses(tmp_path):
    csv_file = tmp_path / "results.csv"
    header = ["benchmark", "model", "tasks_total", "tasks_passed"]
    values = ["tbench", "8b", "100", "14"]
    assert write_csv_row(csv_file, header, values) is True

    lines = csv_file.read_text().strip().splitlines()
    assert lines[0] == ",".join(header)
    assert lines[1] == ",".join(values)


def test_legacy_results_json_still_parses(tmp_path):
    writer = ResultsJsonWriter(output_dir=tmp_path, run_id="legacy_run")
    common_data = OrderedDict(
        [("run_id", "legacy_run"), ("hostname", "host1"), ("tasks_total", "100"), ("tasks_passed", "14")]
    )
    writer.add_row(common_data=common_data)
    out_file = writer.save()

    data = json.loads(out_file.read_text())
    assert data["run_id"] == "legacy_run"
    assert data["rows"][0]["system"]["hostname"] == "host1"
    assert data["rows"][0]["results"]["tasks_total"] == "100"


def test_new_artifacts_are_additive_and_do_not_touch_legacy_files(tmp_path):
    legacy_csv = tmp_path / "results.csv"
    header = ["benchmark", "tasks_total", "tasks_passed"]
    values = ["tbench", "100", "14"]
    write_csv_row(legacy_csv, header, values)
    legacy_contents_before = legacy_csv.read_text()

    writer = ResultsJsonWriter(output_dir=tmp_path, run_id="run1")
    writer.add_row(common_data=OrderedDict([("tasks_total", "100")]))
    writer.save()
    legacy_json_before = (tmp_path / "results.json").read_text()

    summary = build_run_summary(
        workload="tbench",
        run_id="run1",
        active_agents=1,
        vcpus=64,
        runtime_s=3600,
        tasks_total=100,
        tasks_completed=14,
        loop_latencies_ms=[100, 200],
    )
    write_run_artifacts(tmp_path, summary)

    # Legacy files unchanged.
    assert legacy_csv.read_text() == legacy_contents_before
    assert (tmp_path / "results.json").read_text() == legacy_json_before

    # New files additive.
    assert (tmp_path / "agentsysperf_summary.json").exists()
    assert (tmp_path / "agentsysperf_summary.csv").exists()
    assert (tmp_path / "phase_metrics.csv").exists()
    assert (tmp_path / "slo_evaluation.json").exists()
