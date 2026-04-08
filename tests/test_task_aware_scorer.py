"""Task-aware RuleScorer 单元测试"""
from __future__ import annotations

import copy
import pytest

from agent_system.evaluation.scorer import RuleScorer
from agent_system.evaluation.models import RunRecord


# ── 共享夹具 ──────────────────────────────────────────────

SAMPLE_TASK = {
    "task_id": "csv_analysis_clean_general",
    "group": "csv_uplift",
    "eval_type": "uplift",
    "description": "测试任务",
    "input": {
        "user_query": "请分析 csv",
        "session_setup": {"uploads": ["csv/test.csv"]},
    },
    "variants": ["no_skill", "with_skill"],
    "target_skills": ["csv-data-summarizer"],
    "expected_signals": [
        "skill:csv-data-summarizer",
        "tool:Read:/workspace/uploads/",
        "tool:Write:/workspace/temp/",
        "tool:Bash",
        "client_tool:render_chart|render_table",
    ],
    "forbidden_signals": [],
    "expected_artifacts": ["/workspace/temp/*.py"],
    "pass_criteria": {
        "final_response_non_empty": True,
        "tool_errors_max": 0,
        "iterations_max": 12,
    },
    "scoring_weights": {
        "task_success": 0.40,
        "signal_match": 0.20,
        "artifact_match": 0.10,
        "tool_efficiency": 0.10,
        "trajectory_quality": 0.20,
    },
}


def _task(**overrides) -> dict:
    t = copy.deepcopy(SAMPLE_TASK)
    t.update(overrides)
    return t


def _run(**overrides) -> RunRecord:
    defaults = dict(
        run_id="r1",
        session_id="s1",
        task_id="csv_analysis_clean_general",
        variant_id="with_skill",
        status="passed",
        iterations=5,
        tool_calls=8,
        tool_errors=0,
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


def _verifier_task(**overrides) -> dict:
    task = _task(
        expected_signals=[],
        expected_artifacts=[],
        pass_criteria={},
        ground_truth={"answer": "ok", "nested": {"answer": "ok"}},
        scoring_weights={
            "task_success": 0.40,
            "signal_match": 0.20,
            "artifact_match": 0.10,
            "tool_efficiency": 0.10,
            "trajectory_quality": 0.20,
        },
        verifier={
            "mode": "rubric",
            "target": "final_response_json",
            "checks": [
                {
                    "id": "answer",
                    "type": "exact_match",
                    "path": "answer",
                    "weight": 1.0,
                }
            ],
        },
    )
    task.update(overrides)
    return task


FULL_TRAJECTORY = [
    {"type": "skill_injected", "run_id": "r1", "skills": ["csv-data-summarizer"]},
    {"type": "tool_call_started", "run_id": "r1", "tool_name": "Read",
     "arguments": {"path": "/workspace/uploads/test.csv"}},
    {"type": "tool_call_finished", "run_id": "r1", "tool_name": "Read", "status": "success"},
    {"type": "tool_call_started", "run_id": "r1", "tool_name": "Write",
     "arguments": {"path": "/workspace/temp/analysis.py", "content": "..."}},
    {"type": "tool_call_finished", "run_id": "r1", "tool_name": "Write", "status": "success"},
    {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash",
     "arguments": {"command": "python /workspace/temp/analysis.py"}},
    {"type": "tool_call_finished", "run_id": "r1", "tool_name": "Bash", "status": "success"},
    {"type": "client_tool_emitted", "run_id": "r1", "tool_name": "render_chart",
     "arguments": {"data": {}}},
]

FULL_ARTIFACTS = ["/workspace/temp/analysis.py"]


# ── 1. 基础成功 case ─────────────────────────────────────

class TestBasicSuccess:

    def test_all_signals_hit_all_artifacts_present(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert ev.scores["task_success"] == 1.0
        assert ev.scores["signal_match"] == 1.0
        assert ev.scores["artifact_match"] == 1.0
        assert ev.scores["tool_efficiency"] > 0
        assert ev.scores["trajectory_quality"] > 0
        assert ev.metrics["weighted_score"] > 0
        assert not any("失败" in n for n in ev.notes)

    def test_weighted_score_in_metrics(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert "weighted_score" in ev.metrics
        ws = ev.metrics["weighted_score"]
        assert 0.0 <= ws <= 1.0


# ── 2. signal 缺失 ───────────────────────────────────────

class TestSignalMissing:

    def test_partial_signals(self):
        partial = [
            {"type": "skill_injected", "run_id": "r1", "skills": ["csv-data-summarizer"]},
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash",
             "arguments": {"command": "python x.py"}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(),
            trajectory=partial,
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert ev.scores["signal_match"] < 1.0
        assert ev.scores["signal_match"] > 0.0
        assert any("signal 缺失" in n for n in ev.notes)

    def test_no_signals_hit(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(),
            trajectory=[],
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert ev.scores["signal_match"] == 0.0
        assert any("signal 缺失" in n for n in ev.notes)


# ── 3. forbidden signal 命中 ─────────────────────────────

class TestForbiddenSignal:

    def test_forbidden_hit_reduces_score(self):
        task = _task(
            forbidden_signals=["skill:wrong-skill"],
            expected_signals=["tool:Bash"],
        )
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash",
             "arguments": {}},
            {"type": "skill_injected", "run_id": "r1", "skills": ["wrong-skill"]},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(),
            trajectory=trajectory,
            artifacts=[],
            final_response_present=True,
        )
        assert ev.scores["signal_match"] < 1.0
        assert any("forbidden signal 命中" in n for n in ev.notes)


# ── 4. artifact 缺失 ────────────────────────────────────

class TestArtifactMissing:

    def test_no_matching_artifact(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=["/workspace/output/result.html"],
            final_response_present=True,
        )
        assert ev.scores["artifact_match"] == 0.0
        assert any("artifact 缺失" in n for n in ev.notes)

    def test_partial_artifact_match(self):
        task = _task(expected_artifacts=["/workspace/temp/*.py", "/workspace/output/*.html"])
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=["/workspace/temp/analysis.py"],
            final_response_present=True,
        )
        assert ev.scores["artifact_match"] == 0.5
        assert any("artifact 缺失" in n for n in ev.notes)

    def test_empty_expected_artifacts_gives_full_score(self):
        task = _task(expected_artifacts=[])
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=[],
            final_response_present=True,
        )
        assert ev.scores["artifact_match"] == 1.0

    def test_relative_artifact_matches_workspace_pattern(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=["temp/analysis.py"],
            final_response_present=True,
        )
        assert ev.scores["artifact_match"] == 1.0


# ── 5. final_response_non_empty 失败 ────────────────────

class TestFinalResponseCriteria:

    def test_empty_response_fails(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=False,
        )
        assert ev.scores["task_success"] == 0.0
        assert any("final_response_non_empty" in n for n in ev.notes)

    def test_criteria_not_set_allows_empty(self):
        task = _task(pass_criteria={})
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=False,
        )
        assert ev.scores["task_success"] == 1.0


# ── 6. tool_errors_max 超限 ──────────────────────────────

class TestToolErrorsMax:

    def test_over_limit(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(tool_errors=3),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert ev.scores["task_success"] == 0.0
        assert any("tool_errors_max" in n for n in ev.notes)

    def test_at_limit_passes(self):
        task = _task(pass_criteria={"tool_errors_max": 2})
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(tool_errors=2),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert ev.scores["task_success"] == 1.0


# ── 7. iterations_max 超限 ───────────────────────────────

class TestIterationsMax:

    def test_over_limit(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(iterations=20),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert ev.scores["task_success"] == 0.0
        assert any("iterations_max" in n for n in ev.notes)


# ── 8. client_tool:a|b 任一命中 ──────────────────────────

class TestClientToolAlternative:

    def test_first_alternative_hits(self):
        task = _task(expected_signals=["client_tool:render_chart|render_table"])
        trajectory = [
            {"type": "client_tool_emitted", "run_id": "r1", "tool_name": "render_chart",
             "arguments": {}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0

    def test_second_alternative_hits(self):
        task = _task(expected_signals=["client_tool:render_chart|render_table"])
        trajectory = [
            {"type": "client_tool_emitted", "run_id": "r1", "tool_name": "render_table",
             "arguments": {}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0

    def test_neither_alternative_hits(self):
        task = _task(expected_signals=["client_tool:render_chart|render_table"])
        trajectory = [
            {"type": "client_tool_emitted", "run_id": "r1", "tool_name": "show_notification",
             "arguments": {}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 0.0


# ── 9. tool:Read:/workspace/uploads/ path-containing ─────

class TestToolPathContaining:

    def test_path_containing_match(self):
        task = _task(expected_signals=["tool:Read:/workspace/uploads/"])
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Read",
             "arguments": {"path": "/workspace/uploads/data.csv"}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0

    def test_path_not_matching(self):
        task = _task(expected_signals=["tool:Read:/workspace/uploads/"])
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Read",
             "arguments": {"path": "/workspace/temp/script.py"}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 0.0

    def test_relative_path_also_matches_workspace_signal(self):
        task = _task(expected_signals=["tool:Read:/workspace/uploads/"])
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Read",
             "arguments": {"path": "uploads/data.csv"}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0

    def test_tool_without_path_spec(self):
        task = _task(expected_signals=["tool:Bash"])
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash",
             "arguments": {"command": "python x.py"}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0


# ── 10. scoring_weights 生效 ─────────────────────────────

class TestScoringWeights:

    def test_manual_weighted_score_calculation(self):
        task = _task(
            scoring_weights={
                "task_success": 0.50,
                "signal_match": 0.30,
                "artifact_match": 0.20,
            },
            expected_signals=["tool:Bash"],
            expected_artifacts=[],
            pass_criteria={},
        )
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash",
             "arguments": {}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(),
            trajectory=trajectory,
            artifacts=[],
            final_response_present=True,
        )
        ts = ev.scores["task_success"]   # 1.0
        sm = ev.scores["signal_match"]   # 1.0
        am = ev.scores["artifact_match"] # 1.0
        expected_ws = (ts * 0.50 + sm * 0.30 + am * 0.20) / (0.50 + 0.30 + 0.20)
        assert ev.metrics["weighted_score"] == pytest.approx(expected_ws, abs=0.001)

    def test_partial_scores_weighted(self):
        task = _task(
            scoring_weights={"task_success": 0.60, "signal_match": 0.40},
            expected_signals=["tool:Bash", "skill:x"],
            pass_criteria={},
        )
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash",
             "arguments": {}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        ts = ev.scores["task_success"]   # 1.0
        sm = ev.scores["signal_match"]   # 0.5
        expected_ws = round((ts * 0.60 + sm * 0.40) / 1.0, 4)
        assert ev.metrics["weighted_score"] == pytest.approx(expected_ws, abs=0.001)

    def test_empty_weights(self):
        task = _task(scoring_weights={})
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS, final_response_present=True,
        )
        assert ev.metrics["weighted_score"] == 0.0


# ── 11. 旧 score() 不回归 ────────────────────────────────

class TestLegacyScoreCompat:

    def test_old_score_still_works(self):
        scorer = RuleScorer()
        run = _run()
        ev = scorer.score(run, ["/workspace/temp/out.py"])
        assert "task_success" in ev.scores
        assert "tool_efficiency" in ev.scores
        assert "artifact_completeness" in ev.scores
        assert "trajectory_quality" in ev.scores
        assert ev.run_id == "r1"

    def test_old_score_exception_handling(self):
        scorer = RuleScorer()
        run = RunRecord(run_id="r2", session_id="s2")
        ev = scorer.score(run, [])
        assert ev.run_id == "r2"
        assert "task_success" in ev.scores


# ── 补充覆盖 ─────────────────────────────────────────────

class TestEdgeCases:

    def test_run_failed_task_success_zero(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(status="failed"),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=True,
        )
        assert ev.scores["task_success"] == 0.0

    def test_no_expected_signals_gives_full_score(self):
        task = _task(expected_signals=[], forbidden_signals=[])
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=[],
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0

    def test_no_skill_waives_skill_dependent_expected_signals(self):
        task = _task(
            expected_signals=[
                "skill:csv-data-summarizer",
                "tool:Read:/workspace/skills/csv-data-summarizer/SKILL.md",
                "tool:Bash",
            ]
        )
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash", "arguments": {}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(variant_id="no_skill"),
            trajectory=trajectory,
            artifacts=[],
            final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0
        assert ev.metrics["signal_match_detail"]["waived_expected"] == [
            "skill:csv-data-summarizer",
            "tool:Read:/workspace/skills/csv-data-summarizer/SKILL.md",
        ]
        assert any("signal 豁免(no_skill)" in n for n in ev.notes)

    def test_non_no_skill_keeps_skill_dependent_expected_signals(self):
        task = _task(
            expected_signals=[
                "skill:csv-data-summarizer",
                "tool:Read:/workspace/skills/csv-data-summarizer/SKILL.md",
                "tool:Bash",
            ]
        )
        trajectory = [
            {"type": "tool_call_started", "run_id": "r1", "tool_name": "Bash", "arguments": {}},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task,
            run=_run(variant_id="with_skill"),
            trajectory=trajectory,
            artifacts=[],
            final_response_present=True,
        )
        assert ev.scores["signal_match"] == pytest.approx(0.33, abs=0.001)
        assert ev.metrics["signal_match_detail"]["waived_expected"] == []

    def test_only_forbidden_no_expected(self):
        task = _task(expected_signals=[], forbidden_signals=["skill:bad"])
        trajectory = [
            {"type": "skill_injected", "run_id": "r1", "skills": ["bad"]},
        ]
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=trajectory,
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 0.0
        assert any("forbidden" in n for n in ev.notes)

    def test_only_forbidden_not_hit(self):
        task = _task(expected_signals=[], forbidden_signals=["skill:bad"])
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=_run(), trajectory=[],
            artifacts=[], final_response_present=True,
        )
        assert ev.scores["signal_match"] == 1.0

    def test_pass_criteria_detail_in_metrics(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=SAMPLE_TASK,
            run=_run(tool_errors=5, iterations=20),
            trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS,
            final_response_present=False,
        )
        pc = ev.metrics["pass_criteria"]
        assert pc["final_response_non_empty"] is False
        assert pc["tool_errors_max"]["ok"] is False
        assert pc["iterations_max"]["ok"] is False

    def test_task_id_from_task_dict_not_run(self):
        """task_id 优先取 task["task_id"]，不受 run.task_id 影响"""
        task = _task(task_id="csv_analysis_clean_financial")
        run = _run(task_id="adhoc")
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=task, run=run, trajectory=FULL_TRAJECTORY,
            artifacts=FULL_ARTIFACTS, final_response_present=True,
        )
        assert ev.task_id == "csv_analysis_clean_financial"

    def test_exception_returns_degraded_eval(self):
        """异常输入不抛出，返回降级 EvalRecord"""
        scorer = RuleScorer()
        bad_task = {"task_id": "broken", "scoring_weights": "not_a_dict"}
        ev = scorer.score_task_run(
            task=bad_task,
            run=_run(),
            trajectory=[],
            artifacts=[],
            final_response_present=True,
        )
        assert ev.task_id == "broken"
        assert ev.scores["task_success"] is None
        assert any("评分异常" in n for n in ev.notes)


class TestVerifierScoring:

    def test_result_score_drives_task_success(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=_verifier_task(),
            run=_run(),
            trajectory=[],
            artifacts=[],
            final_response_present=True,
            final_response_text='{"answer":"ok"}',
            session_id="s1",
            run_dir="/tmp/run",
        )
        assert ev.scores["result_score"] == 1.0
        assert ev.scores["task_success"] == 1.0
        assert ev.metrics["result_pass"] is True
        assert ev.metrics["result_detail"]["summary"]["passed_checks"] == 1
        assert ev.metrics["result_detail"]["checks"][0]["expected_source"] == "task.ground_truth.answer"

    def test_invalid_json_only_response_returns_explicit_failure(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=_verifier_task(),
            run=_run(),
            trajectory=[],
            artifacts=[],
            final_response_present=True,
            final_response_text="answer=ok",
            session_id="s1",
            run_dir="/tmp/run",
        )
        assert ev.scores["result_score"] == 0.0
        assert ev.scores["task_success"] == 0.0
        assert ev.metrics["result_pass"] is False
        assert "failure_reason" in ev.metrics["result_detail"]
        assert "合法 JSON-only 输出" in ev.metrics["result_detail"]["failure_reason"]
        assert any("result 验证失败" in n for n in ev.notes)

    def test_result_first_weights_override_legacy_weights(self):
        scorer = RuleScorer()
        ev = scorer.score_task_run(
            task=_verifier_task(),
            run=_run(),
            trajectory=[],
            artifacts=[],
            final_response_present=True,
            final_response_text='{"answer":"bad"}',
            session_id="s1",
            run_dir="/tmp/run",
        )
        assert ev.metrics["scoring_weights_used"]["result_score"] == pytest.approx(0.65)
        assert "task_success" not in ev.metrics["scoring_weights_used"]
        assert ev.metrics["weighted_score"] < 0.5

    def test_expected_from_can_override_default_ground_truth_path(self):
        scorer = RuleScorer()
        task = _verifier_task(
            verifier={
                "mode": "rubric",
                "target": "final_response_json",
                "checks": [
                    {
                        "id": "answer_alias",
                        "type": "exact_match",
                        "path": "answer_alias",
                        "expected_from": "nested.answer",
                        "weight": 1.0,
                    }
                ],
            }
        )
        ev = scorer.score_task_run(
            task=task,
            run=_run(),
            trajectory=[],
            artifacts=[],
            final_response_present=True,
            final_response_text='{"answer_alias":"ok"}',
            session_id="s1",
            run_dir="/tmp/run",
        )
        assert ev.scores["result_score"] == 1.0
        assert ev.metrics["result_detail"]["checks"][0]["expected_source"] == "task.ground_truth.nested.answer"
