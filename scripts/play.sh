#!/usr/bin/env bash
# 绕过 Steam 启动器，直接用 GE-Proton 跑游戏（protonfixes 的 localfix 仍会执行）
#
# 用法:
#   scripts/play.sh <appid> "<游戏 exe 所在目录>" <exe 文件名> [游戏参数...]
# 例:
#   scripts/play.sh 550 "$HOME/.steam/debian-installation/steamapps/common/Left 4 Dead 2" left4dead2.exe -steam
set -euo pipefail

APPID=${1:?appid}
GAMEDIR=${2:?game dir}
EXE=${3:?exe name}
shift 3

PROTON_DIR=${PROTON_DIR:-$HOME/.local/share/Steam/compatibilitytools.d/GE-Proton11-9-x86_64}
STEAM_ROOT=${STEAM_ROOT:-$HOME/.steam/debian-installation}

export STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM_ROOT"
export STEAM_COMPAT_DATA_PATH="$STEAM_ROOT/steamapps/compatdata/$APPID"
export STEAM_COMPAT_INSTALL_PATH="$GAMEDIR"
export STEAM_COMPAT_APP_ID="$APPID"
export STEAM_COMPAT_LAUNCHER_SERVICE="proton"

cd "$GAMEDIR"
exec "$PROTON_DIR/proton" waitforexitandrun "$EXE" "$@"
