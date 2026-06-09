"""Variant resolution for benchmark experiment conditions."""
from __future__ import annotations


SUPPORTED_VARIANTS = {"no_skill", "with_skill", "skill_v1", "skill_v2", "irrelevant_skill"}


class VariantResolutionError(Exception):
    """Raised when a task cannot be resolved into a runnable variant."""


class VariantManager:
    """Single place for benchmark variant semantics."""

    def list_supported_variants(self) -> list[str]:
        return sorted(SUPPORTED_VARIANTS)

    def resolve_variant(self, task: dict, variant_id: str) -> dict:
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

        target_skills: list[str] = list(task.get("target_skills", []))

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
            if task.get("eval_type") == "routing":
                resolved = {
                    "variant_id": "with_skill",
                    "enabled_skills": target_skills,
                    "pre_injected_skills": [],
                    "disabled_skills": ["*"],
                    "skill_version_map": {},
                    "routing_enabled": True,
                    "expected_use_mode": "routed",
                }
            else:
                resolved = {
                    "variant_id": "with_skill",
                    "enabled_skills": target_skills,
                    "pre_injected_skills": target_skills,
                    "disabled_skills": ["*"],
                    "skill_version_map": {},
                    "routing_enabled": False,
                    "expected_use_mode": "pre_injected",
                }
        elif variant_id == "skill_v1":
            resolved = self._resolve_versioned(task, target_skills, "skill_v1", "v1")
        elif variant_id == "skill_v2":
            resolved = self._resolve_versioned(task, target_skills, "skill_v2", "v2")
        elif variant_id == "irrelevant_skill":
            irrelevant_skills = list(task.get("irrelevant_skills") or [])
            if not irrelevant_skills:
                raise VariantResolutionError(
                    "variant 'irrelevant_skill' 尚未实现自动选择干扰技能；"
                    f"task '{task.get('task_id', '?')}' 必须声明 irrelevant_skills"
                )
            resolved = {
                "variant_id": "irrelevant_skill",
                "enabled_skills": irrelevant_skills,
                "pre_injected_skills": irrelevant_skills,
                "disabled_skills": ["*"],
                "skill_version_map": {},
                "routing_enabled": False,
                "expected_use_mode": "irrelevant_pre_injected",
            }
        else:
            raise VariantResolutionError(f"未知 variant: {variant_id}")

        return resolved

    def validate_variant_resolution(self, resolved: dict) -> None:
        required_keys = {
            "variant_id",
            "enabled_skills",
            "pre_injected_skills",
            "disabled_skills",
            "skill_version_map",
            "routing_enabled",
            "expected_use_mode",
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
        if resolved["disabled_skills"] == ["*"]:
            return set(resolved["enabled_skills"])
        return None

    @staticmethod
    def _resolve_versioned(
        task: dict,
        target_skills: list[str],
        variant_id: str,
        version_tag: str,
    ) -> dict:
        version_defs = task.get("skill_versions") or {}
        mapping = version_defs.get(variant_id) or version_defs.get(version_tag)
        if not isinstance(mapping, dict) or not mapping:
            raise VariantResolutionError(
                f"variant '{variant_id}' 没有可解析的 skill 版本源；"
                f"请在 task.skill_versions.{variant_id} 显式声明 skill 版本映射"
            )

        enabled_skills: list[str] = []
        version_map: dict[str, str] = {}
        for skill in target_skills:
            concrete_skill = mapping.get(skill)
            if not isinstance(concrete_skill, str) or not concrete_skill:
                raise VariantResolutionError(
                    f"task '{task.get('task_id', '?')}' 缺少 {variant_id} 对 "
                    f"target skill '{skill}' 的版本目录映射"
                )
            enabled_skills.append(concrete_skill)
            version_map[skill] = version_tag

        return {
            "variant_id": variant_id,
            "enabled_skills": enabled_skills,
            "pre_injected_skills": enabled_skills,
            "disabled_skills": ["*"],
            "skill_version_map": version_map,
            "routing_enabled": False,
            "expected_use_mode": f"pre_injected_{version_tag}",
        }
