"""对话技艺知识库注入测试（SPEC §3.2b）。"""
from __future__ import annotations

from core.persona import PersonaManager


def test_craft_injected_into_prompt():
    pm = PersonaManager()
    prompt = pm.build_system_prompt("female_companion", "主人", "", "")
    assert "对话技艺" in prompt
    assert "共情反映" in prompt      # 心理学
    assert "具象化" in prompt        # 文学
    assert "禁忌" in prompt          # 禁用清单


def test_craft_missing_file_tolerated(tmp_path):
    pm = PersonaManager(craft_path=str(tmp_path / "nonexistent.yaml"))
    prompt = pm.build_system_prompt("female_companion", "主人", "", "")
    assert "对话技艺" not in prompt  # 缺失时静默跳过
    assert "第一铁律" in prompt


def test_craft_cached(tmp_path):
    pm = PersonaManager()
    t1 = pm._load_craft()
    t2 = pm._load_craft()
    assert t1 == t2 and t1
