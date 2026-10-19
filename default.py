"""全局默认 localfix（protonfixes）：任何游戏启动前自动装/自愈 DLSSNR-AMD。

用户只需要在 Steam 里给游戏选 GE-Proton11 并启动，其余自动完成。
可在环境变量里设 DLSSNR_AUTO=0 关闭。
"""
import os


def _run(game_id):
    try:
        from protonfixes import util
        from localfixes.common import ensure
        ensure(util, game_id or os.environ.get("STEAM_COMPAT_APP_ID", "0"))
    except Exception:
        # 任何问题都不能影响游戏启动
        pass


def main_with_id(game_id):
    _run(game_id)


def main():
    _run(os.environ.get("STEAM_COMPAT_APP_ID", "0"))
