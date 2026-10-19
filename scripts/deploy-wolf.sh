#!/usr/bin/env bash
# 在 WolfLutris 容器里一键部署 proton-nr-kit（幂等，可重复执行）
#
# 用法:
#   bash scripts/deploy-wolf.sh              # 部署 + 写 Steam 映射（默认 550 1771300）
#   bash scripts/deploy-wolf.sh 550 1771300  # 指定要强制 GE-Proton 的 appid
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
HOME_DIR=${HOME:-/home/retro}
STEAM="$HOME_DIR/.steam/debian-installation"
TOOL="GE-Proton11-9-x86_64"
if [ $# -gt 0 ]; then APPIDS=("$@"); else APPIDS=(550 1771300); fi

say() { printf '\033[1m== %s\033[0m\n' "$*"; }

say "1/6 安装 protonfixes localfix"
bash "$ROOT/scripts/install.sh"

say "2/6 兼容工具软链"
SRC="$HOME_DIR/.local/share/Steam/compatibilitytools.d"
DST="$STEAM/compatibilitytools.d"
if [[ -d "$SRC" ]]; then
  [[ -e "$DST" ]] || ln -s "$SRC" "$DST"
  echo "   $DST -> $(readlink "$DST")"
else
  echo "   !! 找不到 $SRC（GE-Proton 装了吗？）"
fi

say "3/6 Mesa 扩展检查"
if command -v vulkaninfo >/dev/null 2>&1; then
  ext=$(vulkaninfo 2>/dev/null | grep -cE "VK_KHR_cooperative_matrix|VK_EXT_shader_float8" || true)
  if [[ "$ext" -ge 2 ]]; then echo "   cooperative_matrix + float8 都在"; else
    echo "   !! 缺扩展；可先跑 ~/dlssnr-test/fix-mesa.sh"
  fi
else
  echo "   !! 没有 vulkaninfo，跳过"
fi

say "4/6 DLSSNR 包与模型"
for d in "$HOME_DIR/dlssnr-test" "$HOME_DIR/dlssnr-test/pkg32"; do
  if [[ -x "$d/install.sh" ]]; then echo "   ok: $d"; else echo "   !! 缺: $d/install.sh"; fi
done
for f in "$HOME_DIR/dlssnr-test/dlssnr-amd/dlssnr.bin" "$HOME_DIR/dlssnr-test/dlssnr-amd/dlssnr-small.bin"; do
  [[ -f "$f" ]] && echo "   ok: $(basename "$f")" || echo "   !! 缺模型: $f"
done

say "5/6 Steam 兼容性映射"
if pgrep -x steam >/dev/null 2>&1; then
  echo "   Steam 正在运行，跳过配置写入（关掉 Steam 后重跑本脚本即可）"
else
  python3 - "$STEAM" "$TOOL" "${APPIDS[@]}" <<'PY'
import io, os, re, shutil, sys, time
steam, tool, appids = sys.argv[1], sys.argv[2], sys.argv[3:]
cfg = os.path.join(steam, "config/config.vdf")
s = io.open(cfg, encoding="utf-8", errors="surrogateescape").read()
shutil.copy2(cfg, cfg + ".bak-deploy-" + time.strftime("%Y%m%d-%H%M%S"))
def entry(a):
    return ('\t\t\t\t\t"%s"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"%s"\n'
            '\t\t\t\t\t\t"config"\t\t""\n\t\t\t\t\t\t"priority"\t\t"250"\n\t\t\t\t\t}\n') % (a, tool)
if '"CompatToolMapping"' not in s:
    anchor = '\t\t\t"Steam"\n\t\t\t{\n'
    block = '\t\t\t\t"CompatToolMapping"\n\t\t\t\t{\n' + ''.join(entry(a) for a in appids) + '\t\t\t\t}\n'
    s = s.replace(anchor, anchor + block, 1)
else:
    m = re.search(r'"CompatToolMapping"\n\t{4}\{\n', s)
    for a in appids:
        if not re.search(r'"%s"\s*\n\s*\{[^}]*"name"' % a, s):
            s = s[:m.end()] + entry(a) + s[m.end():]
io.open(cfg, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("   已写入映射:", " ".join(appids), "->", tool)
PY
fi

say "6/6 自检"
python3 - "$ROOT" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import common as c
print("   硬拦截路径:", ", ".join(c.HARD_BLOCK_PATHS))
print("   反作弊标记:", ", ".join(c.ANTICHEAT_MARKERS[:6]), "...")
PY

echo
echo "完成。启动 Steam → 直接开始游戏（localfix 会自动安装/设环境变量）。"
echo "日志: ~/.config/dlssnr-auto/auto.log"
