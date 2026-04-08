"""VariantManager 与 SkillManager 可见性控制 单元测试"""
from __future__ import annotations

import copy
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

from agent_system.evaluation.variant_manager import (
    VariantManager,
    VariantResolutionError,
    SUPPORTED_VARIANTS,
)
from agent_system.evaluation.models import RunRecord
from agent_system.evaluation.recorder import RunRecorder
from agent_system.skills.manager import SkillManager
from agent_system.tools.skill_tool import SkillTool, SKILL_TOOL_DESCRIPTION_HEADER


# ── 共享 task 夹具 ────────────────────────────────────────

SAMPLE_TASK = {
    "task_id": "csv_analysis_clean_general",
    "group": "csv_uplift",
    "eval_type": "uplift",
    "description": "测试用 task",
    "input": {
        "user_query": "请分析 csv",
        "session_setup": {"uploads": ["csv/test.csv"]},
    },
    "variants": ["no_skill", "with_skill", "skill_v1", "skill_v2"],
    "target_skills": ["csv-data-summarizer"],
    "expected_signals": ["tool:Bash"],
    "expected_artifacts": [],
    "pass_criteria": {"final_response_non_empty": True},
    "scoring_weights": {"task_success": 0.5},
}


def _task(**overrides) -> dict:
    t = copy.deepcopy(SAMPLE_TASK)
    t.update(overrides)
    return t


# ── VariantManager.resolve_variant ────────────────────────

class TestResolveVariant:

    def setup_method(self):
        self.vm = VariantManager()

    def test_no_skill(self):
        r = self.vm.resolve_variant(SAMPLE_TASK, "no_skill")
        assert r["variant_id"] == "no_skill"
        assert r["enabled_skills"] == []
        assert r["pre_injected_skills"] == []
        assert r["disabled_skills"] == ["*"]
        assert r["routing_enabled"] is False
        assert r["expected_use_mode"] == "none"
        assert r["skill_version_map"] == {}

    def test_with_skill(self):
        r = self.vm.resolve_variant(SAMPLE_TASK, "with_skill")
        assert r["variant_id"] == "with_skill"
        assert r["enabled_skills"] == ["csv-data-summarizer"]
        assert r["pre_injected_skills"] == ["csv-data-summarizer"]
        assert r["disabled_skills"] == ["*"]
        assert r["routing_enabled"] is False
        assert r["expected_use_mode"] == "pre_injected"

    def test_with_skill_multi_targets(self):
        task = _task(target_skills=["csv-data-summarizer", "fin-advisor-math"])
        r = self.vm.resolve_variant(task, "with_skill")
        assert r["enabled_skills"] == ["csv-data-summarizer", "fin-advisor-math"]
        assert r["pre_injected_skills"] == ["csv-data-summarizer", "fin-advisor-math"]

    def test_task_not_support_variant(self):
        task = _task(variants=["no_skill", "with_skill"])
        with pytest.raises(VariantResolutionError, match="不支持 variant 'skill_v1'"):
            self.vm.resolve_variant(task, "skill_v1")

    def test_unknown_variant_id(self):
        with pytest.raises(VariantResolutionError, match="不在受支持列表中"):
            self.vm.resolve_variant(SAMPLE_TASK, "magic_variant")

    def test_skill_v1_fails_without_version_source(self):
        with pytest.raises(VariantResolutionError, match="没有可解析的 skill 版本源"):
            self.vm.resolve_variant(SAMPLE_TASK, "skill_v1")

    def test_skill_v2_fails_without_version_source(self):
        with pytest.raises(VariantResolutionError, match="没有可解析的 skill 版本源"):
            self.vm.resolve_variant(SAMPLE_TASK, "skill_v2")

    def test_irrelevant_skill_not_implemented(self):
        task = _task(variants=["irrelevant_skill"])
        with pytest.raises(VariantResolutionError, match="尚未实现"):
            self.vm.resolve_variant(task, "irrelevant_skill")


# ── VariantManager.validate_variant_resolution ────────────

class TestValidateResolution:

    def setup_method(self):
        self.vm = VariantManager()

    def test_valid_resolution_passes(self):
        r = self.vm.resolve_variant(SAMPLE_TASK, "no_skill")
        self.vm.validate_variant_resolution(r)

    def test_missing_key_fails(self):
        r = self.vm.resolve_variant(SAMPLE_TASK, "no_skill")
        del r["routing_enabled"]
        with pytest.raises(VariantResolutionError, match="缺少必要字段"):
            self.vm.validate_variant_resolution(r)

    def test_wrong_type_fails(self):
        r = self.vm.resolve_variant(SAMPLE_TASK, "no_skill")
        r["routing_enabled"] = "yes"
        with pytest.raises(VariantResolutionError, match="routing_enabled 必须是 bool"):
            self.vm.validate_variant_resolution(r)


# ── VariantManager.get_allowed_skills ─────────────────────

class TestGetAllowedSkills:

    def setup_method(self):
        self.vm = VariantManager()

    def test_no_skill_returns_empty_set(self):
        r = self.vm.resolve_variant(SAMPLE_TASK, "no_skill")
        allowed = self.vm.get_allowed_skills(r)
        assert allowed == set()

    def test_with_skill_returns_target_set(self):
        r = self.vm.resolve_variant(SAMPLE_TASK, "with_skill")
        allowed = self.vm.get_allowed_skills(r)
        assert allowed == {"csv-data-summarizer"}

    def test_no_wildcard_disable_returns_none(self):
        resolved = {
            "variant_id": "custom",
            "enabled_skills": ["x"],
            "pre_injected_skills": [],
            "disabled_skills": [],
            "skill_version_map": {},
            "routing_enabled": True,
            "expected_use_mode": "targeted",
        }
        assert self.vm.get_allowed_skills(resolved) is None


# ── VariantManager.list_supported_variants ────────────────

class TestListVariants:

    def test_returns_all(self):
        vm = VariantManager()
        result = vm.list_supported_variants()
        assert set(result) == SUPPORTED_VARIANTS


# ── SkillManager 可见性控制 ────────────────────────────────

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@pytest.mark.skipif(not SKILLS_DIR.is_dir(), reason="skills/ 不存在")
class TestSkillManagerFiltering:

    def test_default_exposes_all(self):
        sm = SkillManager(SKILLS_DIR)
        assert len(sm.list_skills()) >= 2

    def test_allowed_empty_set_hides_all(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills=set())
        assert sm.list_skills() == []
        assert sm.get_skills_for_tool_description() == ""

    def test_allowed_one_skill(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills={"csv-data-summarizer"})
        assert sm.list_skills() == ["csv-data-summarizer"]
        assert "csv-data-summarizer" in sm.get_skills_for_tool_description()
        assert "fin-advisor-math" not in sm.get_skills_for_tool_description()

    def test_metadata_hidden_for_filtered_skill(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills={"csv-data-summarizer"})
        assert sm.get_skill_metadata("fin-advisor-math") is None
        assert sm.get_skill_metadata("csv-data-summarizer") is not None

    def test_content_hidden_for_filtered_skill(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills={"csv-data-summarizer"})
        result = sm.get_skill_content("fin-advisor-math")
        assert "Error" in result or "not found" in result


# ── SkillTool 执行权限控制 ─────────────────────────────────

@pytest.mark.skipif(not SKILLS_DIR.is_dir(), reason="skills/ 不存在")
class TestSkillToolAccess:

    def test_no_skill_variant_blocks_skill_call(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills=set())
        tool = SkillTool(sm)
        result = tool.execute(skill="csv-data-summarizer")
        assert "Error" in result
        assert "not found" in result

    def test_with_skill_variant_allows_target(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills={"csv-data-summarizer"})
        tool = SkillTool(sm)
        result = tool.execute(skill="csv-data-summarizer")
        assert "Launching skill" in result

    def test_with_skill_variant_blocks_non_target(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills={"csv-data-summarizer"})
        tool = SkillTool(sm)
        result = tool.execute(skill="fin-advisor-math")
        assert "Error" in result

    def test_tool_description_reflects_filter(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills={"fin-advisor-math"})
        tool = SkillTool(sm)
        skills_list = sm.get_skills_for_tool_description()
        assert "fin-advisor-math" in skills_list
        assert "csv-data-summarizer" not in skills_list

    def test_default_mode_exposes_all_skills(self):
        sm = SkillManager(SKILLS_DIR)
        tool = SkillTool(sm)
        desc = tool.description
        assert "csv-data-summarizer" in desc
        assert "fin-advisor-math" in desc


# ── RunRecord variant metadata ────────────────────────────

class TestRunRecordVariantMetadata:

    def test_default_values(self):
        rr = RunRecord(run_id="r1", session_id="s1")
        d = rr.to_dict()
        assert d["enabled_skills"] == []
        assert d["skill_version_map"] == {}
        assert d["routing_enabled"] is None

    def test_variant_fields_serialize(self):
        rr = RunRecord(
            run_id="r1",
            session_id="s1",
            variant_id="with_skill",
            enabled_skills=["csv-data-summarizer"],
            skill_version_map={},
            routing_enabled=True,
        )
        d = rr.to_dict()
        assert d["variant_id"] == "with_skill"
        assert d["enabled_skills"] == ["csv-data-summarizer"]
        assert d["routing_enabled"] is True

    def test_backward_compat_existing_fields(self):
        rr = RunRecord(run_id="r1", session_id="s1", task_id="adhoc", status="passed")
        d = rr.to_dict()
        assert d["task_id"] == "adhoc"
        assert d["status"] == "passed"
        assert "enabled_skills" in d


# ── 端到端：VariantManager -> SkillManager ─────────────────

@pytest.mark.skipif(not SKILLS_DIR.is_dir(), reason="skills/ 不存在")
class TestEndToEndVariantSkillControl:

    def test_no_skill_e2e(self):
        vm = VariantManager()
        resolved = vm.resolve_variant(SAMPLE_TASK, "no_skill")
        allowed = vm.get_allowed_skills(resolved)

        sm = SkillManager(SKILLS_DIR, allowed_skills=allowed)
        assert sm.list_skills() == []

        tool = SkillTool(sm)
        result = tool.execute(skill="csv-data-summarizer")
        assert "Error" in result

    def test_with_skill_e2e(self):
        vm = VariantManager()
        resolved = vm.resolve_variant(SAMPLE_TASK, "with_skill")
        allowed = vm.get_allowed_skills(resolved)

        sm = SkillManager(SKILLS_DIR, allowed_skills=allowed)
        assert "csv-data-summarizer" in sm.list_skills()
        assert "fin-advisor-math" not in sm.list_skills()

        tool = SkillTool(sm)
        assert "Launching skill" in tool.execute(skill="csv-data-summarizer")
        assert "Error" in tool.execute(skill="fin-advisor-math")


# ── variant_context -> RunRecord 落盘 ─────────────────────

class TestVariantContextWriteThrough:
    """验证 variant_context 真正写入 RunRecord"""

    def test_recorder_receives_variant_fields(self, tmp_path):
        vc = {
            "variant_id": "with_skill",
            "enabled_skills": ["csv-data-summarizer"],
            "skill_version_map": {},
            "routing_enabled": False,
            "expected_use_mode": "pre_injected",
            "disabled_skills": ["*"],
            "pre_injected_skills": ["csv-data-summarizer"],
        }
        recorder = RunRecorder(
            session_id="test-sess",
            sessions_root=tmp_path,
            user_input="测试输入",
        )
        recorder.run_record.variant_id = vc.get("variant_id", "baseline")
        recorder.run_record.enabled_skills = list(vc.get("enabled_skills", []))
        recorder.run_record.skill_version_map = dict(vc.get("skill_version_map", {}))
        recorder.run_record.routing_enabled = vc.get("routing_enabled")

        d = recorder.run_record.to_dict()
        assert d["variant_id"] == "with_skill"
        assert d["enabled_skills"] == ["csv-data-summarizer"]
        assert d["routing_enabled"] is False

    def test_finalize_persists_variant_to_json(self, tmp_path):
        import json

        vc = {
            "variant_id": "no_skill",
            "enabled_skills": [],
            "skill_version_map": {},
            "routing_enabled": False,
        }
        recorder = RunRecorder(
            session_id="test-sess2",
            sessions_root=tmp_path,
            user_input="baseline 测试",
        )
        recorder.run_record.variant_id = vc["variant_id"]
        recorder.run_record.enabled_skills = vc["enabled_skills"]
        recorder.run_record.routing_enabled = vc["routing_enabled"]

        recorder.finalize(status="passed", iterations=1)

        run_json_path = tmp_path / "test-sess2" / "runs" / recorder.run_id / "run.json"
        assert run_json_path.exists()
        data = json.loads(run_json_path.read_text(encoding="utf-8"))
        assert data["variant_id"] == "no_skill"
        assert data["enabled_skills"] == []
        assert data["routing_enabled"] is False

    def test_no_variant_context_keeps_defaults(self, tmp_path):
        recorder = RunRecorder(
            session_id="test-sess3",
            sessions_root=tmp_path,
            user_input="普通对话",
        )
        d = recorder.run_record.to_dict()
        assert d["variant_id"] == "baseline"
        assert d["enabled_skills"] == []
        assert d["routing_enabled"] is None

    def test_agent_init_recorder_writes_variant(self, tmp_path):
        """真正经过 Agent(..., variant_context=...) -> _init_recorder() 链路"""
        from agent_system.agent.core import Agent
        from agent_system.tools.base import ToolRegistry

        session_id = "bench-sess-001"
        session_dir = tmp_path / session_id
        session_dir.mkdir()
        log_file = session_dir / "chat_history.log"
        log_file.touch()

        vc = {
            "variant_id": "with_skill",
            "enabled_skills": ["csv-data-summarizer"],
            "skill_version_map": {},
            "routing_enabled": False,
            "expected_use_mode": "pre_injected",
            "disabled_skills": ["*"],
            "pre_injected_skills": ["csv-data-summarizer"],
        }

        sm = MagicMock(spec=SkillManager)
        sm.list_skills.return_value = ["csv-data-summarizer"]
        sm.get_skills_for_tool_description.return_value = "csv-data-summarizer"

        tr = ToolRegistry()

        with patch("agent_system.agent.core.Config") as mock_cfg:
            mock_cfg.SESSIONS_ROOT = tmp_path
            mock_cfg.WORKSPACE_ROOT = tmp_path
            mock_cfg.PERSISTED_OUTPUT_THRESHOLD = 8192
            mock_cfg.PERSISTED_OUTPUT_PREVIEW_SIZE = 2048
            mock_cfg.TOOL_RESULTS_DIR_NAME = ".tool-results"
            mock_cfg.CONTEXT_TOKEN_BUDGET = 100000

            agent = Agent(
                skill_manager=sm,
                tool_registry=tr,
                log_file=str(log_file),
                variant_context=vc,
            )
            recorder = agent._init_recorder("测试 query")

        rr = recorder.run_record
        assert rr.variant_id == "with_skill"
        assert rr.enabled_skills == ["csv-data-summarizer"]
        assert rr.routing_enabled is False
        assert rr.skill_version_map == {}

        recorder.finalize(status="passed", iterations=1)
        run_json = tmp_path / session_id / "runs" / recorder.run_id / "run.json"
        data = json.loads(run_json.read_text(encoding="utf-8"))
        assert data["variant_id"] == "with_skill"
        assert data["enabled_skills"] == ["csv-data-summarizer"]
        assert data["routing_enabled"] is False

    def test_agent_init_recorder_no_variant_keeps_defaults(self, tmp_path):
        """无 variant_context 时 _init_recorder 保持默认值"""
        from agent_system.agent.core import Agent
        from agent_system.tools.base import ToolRegistry

        session_id = "normal-sess-001"
        session_dir = tmp_path / session_id
        session_dir.mkdir()
        log_file = session_dir / "chat_history.log"
        log_file.touch()

        sm = MagicMock(spec=SkillManager)
        sm.list_skills.return_value = []
        sm.get_skills_for_tool_description.return_value = ""

        tr = ToolRegistry()

        with patch("agent_system.agent.core.Config") as mock_cfg:
            mock_cfg.SESSIONS_ROOT = tmp_path
            mock_cfg.WORKSPACE_ROOT = tmp_path
            mock_cfg.PERSISTED_OUTPUT_THRESHOLD = 8192
            mock_cfg.PERSISTED_OUTPUT_PREVIEW_SIZE = 2048
            mock_cfg.TOOL_RESULTS_DIR_NAME = ".tool-results"
            mock_cfg.CONTEXT_TOKEN_BUDGET = 100000

            agent = Agent(
                skill_manager=sm,
                tool_registry=tr,
                log_file=str(log_file),
            )
            recorder = agent._init_recorder("普通对话")

        rr = recorder.run_record
        assert rr.variant_id == "baseline"
        assert rr.enabled_skills == []
        assert rr.routing_enabled is None

    def test_agent_run_preinjects_skill_using_standard_injection_format(self, tmp_path):
        """benchmark 预注入应复用标准 Skill 注入内容格式与 run 记录。"""
        from agent_system.agent.core import Agent
        from agent_system.tools.base import ToolRegistry

        session_id = "bench-sess-preinject"
        session_dir = tmp_path / session_id
        session_dir.mkdir()
        log_file = session_dir / "chat_history.log"
        log_file.touch()

        vc = {
            "variant_id": "with_skill",
            "enabled_skills": ["csv-data-summarizer"],
            "pre_injected_skills": ["csv-data-summarizer"],
            "skill_version_map": {},
            "routing_enabled": False,
            "expected_use_mode": "pre_injected",
            "disabled_skills": ["*"],
        }

        sm = MagicMock(spec=SkillManager)
        sm.list_skills.return_value = ["csv-data-summarizer"]
        sm.get_skills_for_tool_description.return_value = "csv-data-summarizer"
        sm.get_skill_metadata.return_value = {"name": "csv-data-summarizer"}
        sm.get_skill_directory.return_value = Path("/workspace/skills/csv-data-summarizer")
        sm.get_skill_content.return_value = "# CSV skill body"

        tr = ToolRegistry()
        tr.register(SkillTool(sm))

        with patch("agent_system.agent.core.Config") as mock_cfg:
            mock_cfg.SESSIONS_ROOT = tmp_path
            mock_cfg.WORKSPACE_ROOT = tmp_path
            mock_cfg.PERSISTED_OUTPUT_THRESHOLD = 8192
            mock_cfg.PERSISTED_OUTPUT_PREVIEW_SIZE = 2048
            mock_cfg.TOOL_RESULTS_DIR_NAME = ".tool-results"
            mock_cfg.CONTEXT_TOKEN_BUDGET = 100000
            mock_cfg.MAX_ITERATIONS = 1

            agent = Agent(
                skill_manager=sm,
                tool_registry=tr,
                log_file=str(log_file),
                variant_context=vc,
            )
            agent.llm_client = MagicMock()
            agent.llm_client.chat.return_value = {
                "content": "分析完成",
                "tool_calls": [],
                "_meta": {
                    "model": "test-model",
                    "provider": "test-provider",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            }

            result = agent.run("请分析这份 csv", max_iterations=1)

        assert result["response"] == "分析完成"

        history = json.loads(agent.history_file.read_text(encoding="utf-8"))
        skill_msgs = [
            msg for msg in history
            if msg.get("role") == "user"
            and "<skill-loaded>csv-data-summarizer</skill-loaded>" in msg.get("content", "")
        ]
        assert len(skill_msgs) == 1
        assert history.index(skill_msgs[0]) < max(
            idx for idx, msg in enumerate(history)
            if msg.get("role") == "user" and msg.get("content") == "请分析这份 csv"
        )

        run_dirs = list((tmp_path / session_id / "runs").iterdir())
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]

        run_data = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        assert run_data["skills"] == ["csv-data-summarizer"]

        trajectory_lines = (run_dir / "trajectory.jsonl").read_text(encoding="utf-8").splitlines()
        trajectory = [json.loads(line) for line in trajectory_lines if line.strip()]
        assert any(
            evt.get("type") == "skill_injected"
            and evt.get("skills") == ["csv-data-summarizer"]
            for evt in trajectory
        )


# ── SkillTool description 无硬编码业务 skill ──────────────

class TestSkillToolDescriptionNoHardcode:

    def test_template_has_no_hardcoded_skill_names(self):
        assert "csv-data-summarizer" not in SKILL_TOOL_DESCRIPTION_HEADER
        assert "fin-advisor-math" not in SKILL_TOOL_DESCRIPTION_HEADER

    @pytest.mark.skipif(not SKILLS_DIR.is_dir(), reason="skills/ 不存在")
    def test_no_skill_mode_description_hides_business_skills(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills=set())
        tool = SkillTool(sm)
        desc = tool.description
        assert "csv-data-summarizer" not in desc
        assert "fin-advisor-math" not in desc
        assert "(No skills available)" in desc

    @pytest.mark.skipif(not SKILLS_DIR.is_dir(), reason="skills/ 不存在")
    def test_filtered_description_only_shows_allowed(self):
        sm = SkillManager(SKILLS_DIR, allowed_skills={"csv-data-summarizer"})
        tool = SkillTool(sm)
        desc = tool.description
        assert "csv-data-summarizer" in desc
        assert "fin-advisor-math" not in desc
