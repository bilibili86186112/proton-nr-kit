#!/usr/bin/env bash
# proton-nr-kit installer: 把全局 localfix 装进 ~/.config/protonfixes/localfixes
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="${XDG_CONFIG_HOME:-$HOME/.config}/protonfixes/localfixes"

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$DEST/default.py" "$DEST/common.py"
  echo "removed: $DEST/default.py $DEST/common.py"
  echo "记得对每个装过的游戏执行: bash ~/dlssnr-test/install.sh \"<游戏目录>\" remove"
  exit 0
fi

mkdir -p "$DEST"
if [[ -f "$DEST/default.py" ]] && ! grep -q "DLSSNR" "$DEST/default.py" 2>/dev/null; then
  echo "warn: $DEST/default.py 已存在且不是本项目的，已备份为 default.py.bak"
  cp -f "$DEST/default.py" "$DEST/default.py.bak"
fi
cp -f "$ROOT/default.py" "$ROOT/common.py" "$DEST/"
touch "$DEST/__init__.py"
chmod 644 "$DEST/default.py" "$DEST/common.py"

echo "installed: $DEST/default.py  $DEST/common.py"
if command -v python3 >/dev/null 2>&1; then
  python3 -m py_compile "$DEST/default.py" "$DEST/common.py" && echo "syntax ok"
else
  echo "warn: 没找到 python3，跳过语法检查"
fi

echo
echo "下一步：Steam → 游戏属性 → 兼容性 → 选 GE-Proton11 → 启动。"
echo "首次启动会安装一次，日志：~/.config/dlssnr-auto/auto.log"
