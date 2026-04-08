"""
VariantManager — 统一控制 benchmark 实验条件

职责：
- 定义标准 variant（no_skill / with_skill / skill_v1 / skill_v2）
- 根据 task 声明解析出当前 run 的实验条件
- 对 skill_v1 / skill_v2 在缺少版本源时显式失败
- 不把 variant 逻辑散落在 runner 或 task loader 中
"""
from __future__ import annotations

from typing import Any


SUPPORTED_VARIANTS = {"no_skill", "with_skill", "skill_v1", "skill_v2", "irrelevant_skill"}


class VariantResolutionError(Exception):
    """variant 解析失败时抛出"""


class VariantManager:
    """benchmark 侧 variant 解析入口"""

    def list_supported_variants(self) -> list[str]:
        return sorted(SUPPORTED_VARIANTS)

    def resolve_variant(self, task: dict, variant_id: str) -> dict:
        """
        根据 task 和 variant_id 解析出标准实验条件对象。

        Returns:
            {
                "variant_id": str,
                "enabled_skills": list[str],
                "pre_injected_skills": list[str],
                "disabled_skills": list[str],
                "skill_version_map": dict,
                "routing_enabled": bool,
                "expected_use_mode": str,
            }
        """
        if variant_id not in SUPPORTED_VARIANTS:
            raise VariantResolutionError(
                f"variant_id '{variant_id}' 不在受支持列表中。"
                f"支持: {', '.join(sorted(SUPPORTED_VARIANTS))}"
            )

        task_variants = task.get("variants", [])
        if variant_id not in task_variants:
            raise VariantResolutionError(
                f"task '{task.get('task_id', '?')}' 不支持 variant '{variant_id}'。"
                f"该 task 声明的 variants: {task_variants}"
            )

        target_skills: list[str] = task.get("target_skills", [])

        if variant_id == "no_skill":
            resolved = {
                "variant_id": "no_skill",
                "enabled_skills": [],
                "pre_injected_skills": [],
                "disabled_skills": ["*"],
                "skill_version_map": {},
                "routing_enabled": False,
                "expected_use_mode": "none",
            }

        elif variant_id == "with_skill":
            resolved = {
                "variant_id": "with_skill",
                "enabled_skills": list(target_skills),
                "pre_injected_skills": list(target_skills),
                "disabled_skills": ["*"],
                "skill_version_map": {},
                "routing_enabled": False,
                "expected_use_mode": "pre_injected",
            }

        elif variant_id == "skill_v1":
            resolved = self._resolve_versioned(target_skills, "skill_v1", "v1")

        elif variant_id == "skill_v2":
            resolved = self._resolve_versioned(target_skills, "skill_v2", "v2")

        elif variant_id == "irrelevant_skill":
            raise VariantResolutionError(
                "variant 'irrelevant_skill' 尚未实现。"
                "该 variant 需要额外的 irrelevant skill 注入机制，将在后续版本支持。"
            )
        else:
            raise VariantResolutionError(f"未知 variant: {variant_id}")

        return resolved

    def validate_variant_resolution(self, resolved: dict) -> None:
        """校验 resolved variant 对象的完整性"""
        required_keys = {
            "variant_id", "enabled_skills", "pre_injected_skills", "disabled_skills",
            "skill_version_map", "routing_enabled", "expected_use_mode",
        }
        missing = required_keys - set(resolved.keys())
        if missing:
            raise VariantResolutionError(
                f"resolved variant 缺少必要字段: {', '.join(sorted(missing))}"
            )

        if not isinstance(resolved["enabled_skills"], list):
            raise VariantResolutionError("enabled_skills 必须是 list")
        if not isinstance(resolved["pre_injected_skills"], list):
            raise VariantResolutionError("pre_injected_skills 必须是 list")
        if not isinstance(resolved["disabled_skills"], list):
            raise VariantResolutionError("disabled_skills 必须是 list")
        if not isinstance(resolved["skill_version_map"], dict):
            raise VariantResolutionError("skill_version_map 必须是 dict")
        if not isinstance(resolved["routing_enabled"], bool):
            raise VariantResolutionError("routing_enabled 必须是 bool")

    def get_allowed_skills(self, resolved: dict) -> set[str] | None:
        """
        从 resolved variant 提取 SkillManager 的 allowed_skills 参数。

        Returns:
            - set[str]: 允许的技能集合（可能为空集，表示不允许任何 skill）
            - None: 不做限制（默认模式，非 benchmark 场景）
        """
        if resolved["disabled_skills"] == ["*"]:
            return set(resolved["enabled_skills"])
        return None

    # ── 内部 ──────────────────────────────────────────────

    @staticmethod
    def _resolve_versioned(
        target_skills: list[str], variant_id: str, version_tag: str
    ) -> dict:
        """
        解析版本化 variant（skill_v1 / skill_v2）。
        当前系统没有 skill 版本仓库，必须显式失败。
        """
        version_map = {skill: version_tag for skill in target_skills}
        raise VariantResolutionError(
            f"variant '{variant_id}' 要求版本 '{version_tag}'，"
            f"但系统当前没有可解析的 skill 版本源。"
            f"需要的版本映射: {version_map}。"
            f"请先实现 skill 版本管理后再使用此 variant。"
        )
