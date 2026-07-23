"""配置读写往返（SPEC §6 必测点）。"""
import os

import yaml

from core.config import Settings, load_settings, save_settings


def test_load_defaults_when_file_missing(tmp_path):
    s = load_settings(str(tmp_path / "nope.yaml"))
    assert s.tier == "standard"
    assert s.llm_backend == "mock"
    assert s.master_name == "主人"
    assert s.active_persona == "female_companion"
    assert s.active_relationship == "lover"  # SPEC §3.2a 默认关系身份
    assert s.data_dir == "data"


def test_save_load_round_trip(tmp_path):
    path = str(tmp_path / "settings.yaml")
    original = Settings(tier="pro", llm_backend="ollama", model_id="hermes-3-8b-q8",
                        show_thinking=False, master_name="阿宅",
                        active_persona="male_companion",
                        active_relationship="bestie", voice_enabled=False,
                        tts_engine="piper", stt_model_size="tiny",
                        bluetooth_enabled=True, mihome_enabled=True,
                        mihome_mode="cloud", cluster_enabled=True,
                        cluster_role="worker", data_dir=str(tmp_path / "data"))
    save_settings(original, path)
    loaded = load_settings(path)
    assert loaded == original
    assert loaded.active_relationship == "bestie"  # round-trip 含 active_relationship


def test_load_ignores_unknown_fields_and_fills_defaults(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"tier": "lite", "未来字段": 1,
                                    "master_name": "小白"}), encoding="utf-8")
    s = load_settings(str(path))
    assert s.tier == "lite"
    assert s.master_name == "小白"
    assert s.llm_backend == "mock"  # 未写的字段走默认值
    assert not hasattr(s, "未来字段")


def test_load_empty_yaml_uses_defaults(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("", encoding="utf-8")
    s = load_settings(str(path))
    assert s == Settings()


def test_hermes_home_relocates_relative_data_dir(tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"data_dir": "data"}), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    s = load_settings(str(path))
    assert s.data_dir == os.path.join(str(tmp_path / "home"), "data")


def test_hermes_home_keeps_absolute_data_dir(tmp_path, monkeypatch):
    abs_dir = str(tmp_path / "abs_data")
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"data_dir": abs_dir}), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    s = load_settings(str(path))
    assert s.data_dir == abs_dir


def test_load_repo_default_settings():
    """仓库自带的 config/settings.yaml 必须能被契约加载。"""
    s = load_settings("config/settings.yaml")
    assert s.tier in {"lite", "standard", "pro"}
    assert s.llm_backend in {"llamacpp", "ollama", "openai", "mock"}
    assert s.model_id
