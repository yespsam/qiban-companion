#!/usr/bin/env bash
# 栖伴 · 声线模型下载脚本（SPEC §3.7b 配套）
# 从 ModelScope（AI-Hobbyist GPT-SoVITS 模型合集）下载 6 个成品声线模型：
#   萝莉音·可莉 / 御姐音·八重神子 / 搞笑女·胡桃 / 少年音·温迪 / 大叔音·钟离 / 搞笑男·荒泷一斗
#
# ⚠️ 游戏角色音色，仅限个人本地娱乐使用；禁止商用、禁止二次分发、禁止随本项目发布。
#
# 用法：
#   bash tools/fetch_voice_models.sh [输出目录]     # 默认 ./voice-models
# 依赖：curl、python3
set -euo pipefail

OUT="${1:-voice-models}"
BASE="https://www.modelscope.cn/models/aihobbyist/GPT-SoVITS_Model_Collection/resolve/master/%E5%8E%9F%E7%A5%9E/%E4%B8%AD%E6%96%87"
mkdir -p "$OUT/tmp"

# 声线目录名|URL编码的角色文件名
ITEMS=(
  "loli_萝莉音_可莉|%E5%8F%AF%E8%8E%89_ZH.zip"
  "yujie_御姐音_八重神子|%E5%85%AB%E9%87%8D%E7%A5%9E%E5%AD%90_ZH.zip"
  "funny_搞笑女_胡桃|%E8%83%A1%E6%A1%83_ZH.zip"
  "shonen_少年音_温迪|%E6%B8%A9%E8%BF%AA_ZH.zip"
  "uncle_大叔音_钟离|%E9%92%9F%E7%A6%BB_ZH.zip"
  "funny_m_搞笑男_荒泷一斗|%E8%8D%92%E6%B3%B7%E4%B8%80%E6%96%97_ZH.zip"
)

for item in "${ITEMS[@]}"; do
  dir="${item%%|*}"; file="${item##*|}"
  dest="$OUT/$dir"
  if ls "$dest"/*.ckpt >/dev/null 2>&1; then
    echo "[跳过] $dir 已存在"
    continue
  fi
  echo "[下载] $dir（约 200MB）…"
  curl -L --retry 3 -o "$OUT/tmp/$dir.zip" "$BASE/$file"
  mkdir -p "$dest"
  # 解出权重与参考音频（文件名含 #Uxxxx 转义，用 python 还原）
  python3 - "$OUT/tmp/$dir.zip" "$dest" <<'PY'
import os, re, sys, zipfile
zpath, dest = sys.argv[1], sys.argv[2]
dec = lambda n: re.sub(r'#U([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), n)
with zipfile.ZipFile(zpath) as z:
    for info in z.infolist():
        if info.is_dir():
            continue
        base = os.path.basename(dec(info.filename))
        if base.endswith(('.ckpt', '.pth', '.wav')):
            with open(os.path.join(dest, base), 'wb') as f:
                f.write(z.read(info))
print('  ->', sorted(os.listdir(dest)))
PY
  rm -f "$OUT/tmp/$dir.zip"
done
rmdir "$OUT/tmp" 2>/dev/null || true

cat <<'EOF'

✅ 全部完成。使用方式：
A. 完整权重（推荐）：.ckpt 放入 GPT-SoVITS 的 GPT_weights_v4，
   .pth 放入 SoVITS_weights_v4，推理界面选角色合成；
   栖伴侧 settings.yaml 设 tts_engine: clone，clone_api_base 指向该服务。
B. 零样本：启动 GPT-SoVITS api.py 后，用角色目录里的【默认】*.wav 上传：
   curl -X POST "http://127.0.0.1:8000/api/voice/upload?target=female_companion" \
        -H "Content-Type: audio/wav" --data-binary "@voice-models/loli_萝莉音_可莉/【默认】xxx.wav"

⚠️ 仅限个人本地使用，禁止商用与二次分发。
EOF
