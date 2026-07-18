"""长期记忆（SPEC §3.5）：sqlite 存储，懒建表。

retrieve 默认 LIKE 关键词召回；若 chromadb 可用（懒加载、try 包住）则升级为
向量召回，任一环节失败自动降级回关键词召回。
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass

from core.logging_utils import get_logger

log = get_logger(__name__)

_LONG_TERM_LIMIT = 200  # 超过该条数时，旧记忆将被压缩进 profile


@dataclass
class Episode:
    ts: float
    role: str                 # "master" | "companion"
    content: str
    emotion: str = ""
    tags: str = ""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    emotion TEXT DEFAULT '',
    tags TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    content TEXT NOT NULL DEFAULT '',
    updated_ts REAL NOT NULL DEFAULT 0
);
"""


class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._tables_ready = False
        self._chroma = None
        self._chroma_disabled = False

    # ---------------- 基础：连接与懒建表 ----------------

    def _ensure(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        if not self._tables_ready:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            self._tables_ready = True
        return self._conn

    @staticmethod
    def _row_to_ep(row: sqlite3.Row) -> Episode:
        return Episode(ts=row["ts"], role=row["role"], content=row["content"],
                       emotion=row["emotion"] or "", tags=row["tags"] or "")

    # ---------------- 增查 ----------------

    def add(self, ep: Episode) -> None:
        conn = self._ensure()
        cur = conn.execute(
            "INSERT INTO episodes(ts, role, content, emotion, tags) VALUES (?,?,?,?,?)",
            (ep.ts, ep.role, ep.content, ep.emotion, ep.tags),
        )
        conn.commit()
        self._chroma_add(cur.lastrowid, ep)

    def recent(self, n: int = 20) -> list[Episode]:
        conn = self._ensure()
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM episodes ORDER BY ts DESC, id DESC LIMIT ?)"
            " ORDER BY ts ASC, id ASC",
            (n,),
        ).fetchall()
        return [self._row_to_ep(r) for r in rows]

    def count(self) -> int:
        return int(self._ensure().execute("SELECT COUNT(*) FROM episodes").fetchone()[0])

    # ---------------- 召回：LIKE 关键词 + 可选向量 ----------------

    @staticmethod
    def _keywords(query: str) -> list[str]:
        """中文友好：整词 + 二元组（bigram）作为 LIKE 关键词。"""
        kws: list[str] = []
        for token in re.split(r"\s+", query.strip()):
            if not token:
                continue
            kws.append(token)
            if len(token) > 2:
                kws.extend(token[i:i + 2] for i in range(len(token) - 1))
        # 去重保序
        seen, out = set(), []
        for kw in kws:
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
        return out

    def _retrieve_like(self, query: str, k: int) -> list[Episode]:
        keywords = self._keywords(query)
        if not keywords:
            return []
        conn = self._ensure()
        where = " OR ".join("content LIKE ?" for _ in keywords)
        rows = conn.execute(
            f"SELECT * FROM episodes WHERE {where} ORDER BY ts DESC, id DESC LIMIT 500",
            tuple(f"%{kw}%" for kw in keywords),
        ).fetchall()
        scored = []
        for row in rows:
            score = sum(1 for kw in keywords if kw in row["content"])
            scored.append((score, row["ts"], row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [self._row_to_ep(row) for _, _, row in scored[:k]]

    def _get_chroma(self):
        """懒加载 chromadb；不可用则返回 None 并永久降级。"""
        if self._chroma_disabled:
            return None
        if self._chroma is None:
            try:
                import chromadb  # 懒加载

                client = chromadb.PersistentClient(path=self.db_path + ".chroma")
                self._chroma = client.get_or_create_collection("episodes")
            except Exception:  # noqa: BLE001
                log.info("chromadb 不可用，记忆召回使用 LIKE 关键词模式")
                self._chroma_disabled = True
                return None
        return self._chroma

    def _chroma_add(self, rowid: int | None, ep: Episode) -> None:
        if rowid is None:
            return
        try:
            chroma = self._get_chroma()
            if chroma is not None:
                chroma.upsert(ids=[str(rowid)], documents=[ep.content],
                              metadatas=[{"ts": ep.ts, "role": ep.role}])
        except Exception:  # noqa: BLE001
            log.info("chromadb 写入失败，降级为纯关键词召回")
            self._chroma_disabled = True

    def _retrieve_vector(self, query: str, k: int) -> list[Episode] | None:
        """向量召回；失败或为空返回 None 让调用方降级。"""
        try:
            chroma = self._get_chroma()
            if chroma is None:
                return None
            result = chroma.query(query_texts=[query], n_results=k)
            ids = (result.get("ids") or [[]])[0]
            if not ids:
                return None
            conn = self._ensure()
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"SELECT * FROM episodes WHERE id IN ({placeholders})",
                tuple(int(i) for i in ids),
            ).fetchall()
            by_id = {str(r["id"]): r for r in rows}
            return [self._row_to_ep(by_id[i]) for i in ids if i in by_id]
        except Exception:  # noqa: BLE001
            log.info("chromadb 查询失败，自动降级为 LIKE 关键词召回")
            self._chroma_disabled = True
            return None

    def retrieve(self, query: str, k: int = 5) -> list[Episode]:
        """召回相关记忆：向量优先（chromadb 可用时），失败自动降级 LIKE。"""
        if not query or not query.strip():
            return []
        episodes = self._retrieve_vector(query, k)
        if episodes:
            return episodes
        return self._retrieve_like(query, k)

    # ---------------- 长期压缩 ----------------

    def get_profile(self) -> str:
        row = self._ensure().execute(
            "SELECT content FROM profile WHERE id = 1").fetchone()
        return str(row["content"]) if row else ""

    def summarize_long_term(self, backend) -> None:
        """把超过 200 条的旧记忆压缩为「关于主人的事实」档案，存入 profile 表。"""
        conn = self._ensure()
        total = self.count()
        if total <= _LONG_TERM_LIMIT:
            return
        old_rows = conn.execute(
            "SELECT * FROM episodes ORDER BY ts ASC, id ASC LIMIT ?",
            (total - _LONG_TERM_LIMIT,),
        ).fetchall()
        if not old_rows:
            return
        lines = [f"[{r['role']}] {r['content']}" for r in old_rows]
        existing = self.get_profile()
        prompt = (
            "请把下面的对话记录压缩成「关于主人的事实」档案要点"
            "（偏好、习惯、重要事件、关系状态），用简洁的中文分条列出。\n"
        )
        if existing:
            prompt += f"已有档案：\n{existing}\n"
        prompt += "对话记录：\n" + "\n".join(lines)
        messages = [
            {"role": "system", "content": "你负责整理长期记忆档案，只输出事实要点。"},
            {"role": "user", "content": prompt},
        ]
        result = backend.generate(messages, temperature=0.3, max_tokens=1024)
        summary = (result.text or "").strip()
        if not summary:
            log.warning("长期记忆压缩结果为空，保留原始记录")
            return
        ids = [r["id"] for r in old_rows]
        conn.execute(
            f"DELETE FROM episodes WHERE id IN ({','.join('?' for _ in ids)})", ids)
        conn.execute(
            "INSERT INTO profile(id, content, updated_ts) VALUES (1, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET content = excluded.content,"
            " updated_ts = excluded.updated_ts",
            (summary, time.time()),
        )
        conn.commit()
        log.info("长期记忆已压缩：%d 条 → profile（%d 字）", len(ids), len(summary))

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._tables_ready = False
