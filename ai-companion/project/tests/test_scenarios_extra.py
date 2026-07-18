"""日常场景扩充测试（v4）：18 个新场景四身份命中校验。"""
from __future__ import annotations

import pytest

from core.config import Settings
from core.llm.mock_backend import MockBackend

CASES = [
    ("好无聊啊", ("接龙", "笑话", "唠", "故事", "晒太阳")),
    ("给我讲个笑话", ("哈", "嘿", "笑", "饺子", "固执", "螃蟹", "气球", "抄蚌", "懒汉", "怕老婆")),
    ("我们玩游戏吧", ("接龙", "猜", "谜", "当然了", "问题")),
    ("今天我生日", ("生日快乐", "蛋糕", "长寿面", "撒花", "愿望", "新的一岁")),
    ("你觉得ChatGPT怎么样", ("AI", "吃醋", "懂", "替补", "闺蜜", "交情")),
    ("对不起我错了", ("原谅", "翻篇", "不气", "没事", "道歉", "心软")),
    ("今天好冷", ("冷", "天气", "穿", "热", "加衣", "衣裳")),
    ("周末去哪玩", ("周末", "安排", "睡", "逛", "电影", "晒太阳", "歇")),
    ("最近有什么电影好看", ("电影", "片子", "剧", "歌", "看", "听")),
    ("你在干嘛", ("想你", "等你", "惦记", "盼", "守着", "数日子")),
    ("你会什么", ("会", "聊天", "记住", "语音", "提醒", "陪")),
    ("你这个笨蛋", ("笨", "可爱", "闹", "哭", "聪明", "喜欢")),
    ("都凌晨了还睡不着", ("睡", "熬夜", "数羊", "手机", "休息", "晚安")),
    ("我出门了", ("出门", "路上", "安全", "回来", "信", "饭")),
    ("我回来了", ("回来", "欢迎", "饿", "歇", "今天", "抱抱")),
    ("我不行，什么都做不好", ("不许", "打住", "胡说", "低谷", "最棒", "废物", "歇", "累")),
    ("我有点害怕", ("怕", "别怕", "顶着", "拆", "定心丸", "陪")),
    ("哦", ("冷淡", "淡淡", "话少", "心事", "委屈", "吱一声", "说说", "哦")),
]


@pytest.mark.parametrize("rel", ["lover", "friend", "bestie", "elder"])
@pytest.mark.parametrize("text, keys", CASES)
def test_daily_scenes_hit(rel, text, keys):
    b = MockBackend(settings=Settings(active_relationship=rel), seed=1)
    r = b.generate([{"role": "user", "content": text}])
    assert "<think>" in r.text and "</think>" in r.text
    reply = r.text.split("</think>")[-1]
    # 命中场景 ≠ 兜底模板（兜底话术特征词不得出现）
    assert "然后呢" not in reply and "接着说" not in reply, f"[{rel}] {text} -> {r.text!r}"
