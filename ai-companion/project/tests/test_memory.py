"""MemoryStore 增查与降级召回（SPEC §6 必测点）。"""
import time

from core.llm.mock_backend import MockBackend
from core.memory import Episode, MemoryStore


def _ep(content, role="master", ts=None, emotion=""):
    return Episode(ts=ts if ts is not None else time.time(),
                   role=role, content=content, emotion=emotion)


def test_add_and_recent_order(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    for i in range(5):
        store.add(_ep(f"第{i}条", ts=1000 + i))
    recent = store.recent(3)
    assert [e.content for e in recent] == ["第2条", "第3条", "第4条"]  # 时间升序


def test_recent_default_20(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    for i in range(25):
        store.add(_ep(f"msg{i}", ts=float(i)))
    assert len(store.recent()) == 20


def test_retrieve_like_keyword_hit(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    store.add(_ep("主人喜欢吃草莓蛋糕", ts=1.0))
    store.add(_ep("今天天气不错出门散步", ts=2.0))
    store.add(_ep("主人说工作压力有点大", ts=3.0))
    hits = store.retrieve("草莓", k=5)
    assert len(hits) == 1
    assert "草莓" in hits[0].content


def test_retrieve_ranks_more_keyword_matches_first(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    store.add(_ep("主人喜欢猫", ts=1.0))
    store.add(_ep("主人喜欢猫也喜欢猫咖", ts=2.0))
    hits = store.retrieve("猫", k=2)
    assert hits[0].content == "主人喜欢猫也喜欢猫咖"


def test_retrieve_empty_query_returns_empty(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    store.add(_ep("随便一条"))
    assert store.retrieve("") == []
    assert store.retrieve("   ") == []


def test_retrieve_respects_k(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    for i in range(10):
        store.add(_ep(f"关于猫的第{i}条", ts=float(i)))
    assert len(store.retrieve("猫", k=3)) == 3


def test_retrieve_fallback_when_chromadb_unavailable(tmp_path):
    """无 chromadb 环境：retrieve 自动走 LIKE 关键词召回（降级路径）。"""
    store = MemoryStore(str(tmp_path / "m.db"))
    store.add(_ep("主人对花生过敏", ts=1.0))
    # chromadb 未安装 → _get_chroma 返回 None → LIKE 召回
    assert store._get_chroma() is None
    hits = store.retrieve("花生过敏")
    assert hits and "花生" in hits[0].content


def test_lazy_table_creation(tmp_path):
    """懒建表：构造后未操作时数据库文件可以不存在表，首次操作后才建。"""
    db = str(tmp_path / "m.db")
    store = MemoryStore(db)
    assert store._conn is None
    store.add(_ep("触发建表"))
    assert store.count() == 1


def test_persistence_across_instances(tmp_path):
    db = str(tmp_path / "m.db")
    MemoryStore(db).add(_ep("主人住在南方", ts=1.0))
    store2 = MemoryStore(db)
    assert [e.content for e in store2.recent(5)] == ["主人住在南方"]


def test_summarize_long_term_compresses_old_episodes(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    for i in range(205):
        store.add(_ep(f"主人的第{i}件小事", ts=float(i)))
    backend = MockBackend(seed=1)
    store.summarize_long_term(backend)
    assert store.count() == 200  # 旧 5 条被压缩
    profile = store.get_profile()
    assert profile  # 「关于主人的事实」档案已写入
    # 最新的记忆仍在
    assert store.recent(1)[0].content == "主人的第204件小事"


def test_summarize_noop_when_under_limit(tmp_path):
    store = MemoryStore(str(tmp_path / "m.db"))
    for i in range(10):
        store.add(_ep(f"第{i}条", ts=float(i)))
    store.summarize_long_term(MockBackend(seed=1))
    assert store.count() == 10
    assert store.get_profile() == ""
