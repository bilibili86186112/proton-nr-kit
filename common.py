"""DLSSNR-AMD 全局自动安装/自愈（供 ~/.config/protonfixes/localfixes/default.py 调用）。

设计目标：用户只需要在 Steam 里给游戏选 GE-Proton11 并启动，其余全自动：
  1. 按游戏目录自动判位数、选路由（32 位 → reshade-feeder-dx9；有 DLSS/FSR/XeSS → optiscaler；否则 reshade-feeder）
  2. 缺文件就调用 DLSSNR-AMD 的 install.sh 装上
  3. 用 util.set_environment 设好 WINEDLLOVERRIDES / VK_ADD_LAYER_PATH / VK_INSTANCE_LAYERS
     （因此不需要 Steam 启动选项）

只依赖标准库；所有异常都吞掉，绝不影响游戏启动。
"""
import json
import os
import re
import struct
import subprocess
import time

HOME = os.path.expanduser("~")
STATE_DIR = os.environ.get("DLSSNR_STATE_DIR", os.path.join(HOME, ".config/dlssnr-auto"))
STATE_FILE = os.path.join(STATE_DIR, "games.json")
LOG_FILE = os.path.join(STATE_DIR, "auto.log")
PKG64 = os.environ.get("DLSSNR_PKG_DIR", os.path.join(HOME, "dlssnr-test"))
PKG32 = os.environ.get("DLSSNR_PKG32_DIR", os.path.join(PKG64, "pkg32"))
MARKER = "dlssnr-amd-install.txt"
UPSCALER_DLLS = {"nvngx_dlss.dll", "amd_fidelityfx_upscaler_dx12.dll", "libxess.dll", "amd_fidelityfx_dx12.dll"}
# 不处理的 appid：Steam Linux Runtime / Proton 本体 / 反作弊运行时等
BLACKLIST = {"228980", "1070560", "1391110", "1628350", "4183110", "1493710", "2180100",
             "1826330", "1161040", "1054830", "1580130", "1887720", "2348590", "2805730",
             "3658110", "4628710", "961940",
             # 在线/反作弊游戏：Diablo IV / Overwatch 2 等
             "2344520", "2357570", "2073850", "1203220"}
# 路径关键词（Lutris/Battle.net 等没有 appid 的场景）
BLACKLIST_PATHS = ("battlenet", "battle.net", "blizzard", "epic games", "ea games", "ubisoft connect",
                   "riot client", "steamapps/common/steamworks", "easyanticheat", "battleye")
# 目录里出现这些名字 → 视为反作弊，默认跳过（DLSSNR_ALLOW=1 可强制）
ANTICHEAT_MARKERS = ("easyanticheat", "battleye", "beservice", "warden", "anticheat",
                     "vanguard", "ricochet", "faceit")


def log(msg):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg) + "\n")
    except OSError:
        pass


def _load_state():
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        json.dump(st, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except OSError:
        pass


def find_exe(game_dir):
    best, best_score = None, -1.0
    base = os.path.basename(game_dir.rstrip("/")).lower()
    for root, dirs, files in os.walk(game_dir):
        if root[len(game_dir):].count(os.sep) > 4:
            dirs[:] = []
            continue
        for f in files:
            if not f.lower().endswith(".exe"):
                continue
            p = os.path.join(root, f)
            try:
                size = os.path.getsize(p)
            except OSError:
                continue
            name = f[:-4].lower()
            score = min(size / 1e8, 10.0)
            if name in base or base in name:
                score += 100
            if any(k in name for k in ("launcher", "sndrpt", "bugsplat", "steam", "crash", "setup")):
                score -= 50
            if score > best_score:
                best, best_score = p, score
    return best


def pe_bits(path):
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                return None
            f.seek(0x3C)
            off = struct.unpack("<I", f.read(4))[0]
            f.seek(off)
            if f.read(4) != b"PE\0\0":
                return None
            machine = struct.unpack("<H", f.read(2))[0]
            return 64 if machine == 0x8664 else 32 if machine in (0x14C, 0x1C0, 0x1C4) else None
    except OSError:
        return None


def has_upscaler(game_dir):
    for root, dirs, files in os.walk(game_dir):
        if root[len(game_dir):].count(os.sep) > 4:
            dirs[:] = []
            continue
        if any(f.lower() in UPSCALER_DLLS for f in files):
            return True
    return False


def detect(game_dir, appid):
    st = _load_state().get(str(appid))
    if st and st.get("game_dir") == game_dir and os.path.exists(st.get("exe", "")):
        return st
    exe = find_exe(game_dir)
    if not exe:
        return None
    bits = pe_bits(exe)
    route = "reshade-feeder-dx9" if bits == 32 else ("optiscaler" if has_upscaler(game_dir) else "reshade-feeder")
    st = {"game_dir": game_dir, "exe": exe, "bits": bits, "route": route,
          "package": PKG32 if bits == 32 else PKG64}
    state = _load_state()
    state[str(appid)] = st
    _save_state(state)
    return st


def install(st):
    pkg, exe = st["package"], st["exe"]
    sh = os.path.join(pkg, "install.sh")
    if not os.path.exists(sh):
        log(f"缺少安装器: {sh}")
        return False
    cmd = ["bash", sh, os.path.dirname(exe), st["route"], "--old-model", "--no-int4", "--no-renodx"]
    log("install: " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        log(f"install rc={r.returncode}\n{r.stdout[-2000:]}\n{r.stderr[-1000:]}")
        return r.returncode == 0
    except Exception as e:
        log(f"install 异常: {e!r}")
        return False


def set_env(util, st):
    """优先用 util.winedll_override（它会正确合并进 Proton 的会话环境）。"""
    route = st["route"]
    try:
        order = util.OverrideOrder.NATIVE_BUILTIN
    except Exception:
        order = "n,b"
    if route.startswith("optiscaler"):
        layer = os.path.join(os.path.dirname(st["exe"]), "dlssnr-amd/control/layer")
        util.set_environment("VK_ADD_LAYER_PATH", layer)
        util.set_environment("VK_INSTANCE_LAYERS", "VK_LAYER_DLSSNR_control")
        util.winedll_override("dxgi", order)
    else:
        util.winedll_override("winevulkan", order)
        util.winedll_override("vulkan-1", order)


def has_anticheat(game_dir):
    try:
        for root, dirs, files in os.walk(game_dir):
            if root[len(game_dir):].count(os.sep) > 3:
                dirs[:] = []
                continue
            for name in list(dirs) + list(files):
                low = name.lower()
                if any(m in low for m in ANTICHEAT_MARKERS):
                    return name
    except OSError:
        pass
    return None


def blocked_by_path(game_dir):
    low = game_dir.lower().replace("\\", "/")
    return next((p for p in BLACKLIST_PATHS if p in low), None)


def ensure(util, appid):
    """default.py 的入口：幂等、异常安全。"""
    try:
        if os.environ.get("DLSSNR_AUTO", "1") in ("0", "false", "no"):
            return
        appid = str(appid)
        if appid in BLACKLIST or not appid.isdigit():
            return
        game = util.get_game_install_path()
        if not game or not os.path.isdir(game):
            return
        allow = os.environ.get("DLSSNR_ALLOW", "") in ("1", "true", "yes")
        hit = blocked_by_path(game)
        if hit and not allow:
            log(f"{appid}: 跳过（路径含 '{hit}'，在线/启动器前缀）")
            return
        ac = has_anticheat(game)
        if ac and not allow:
            log(f"{appid}: 跳过（检测到反作弊痕迹 '{ac}'）")
            return
        st = detect(game, appid)
        if not st:
            return
        if not os.path.exists(os.path.join(game, MARKER)):
            log(f"{appid}: 未安装，开始安装（{st['route']}）")
            if not install(st):
                return
        set_env(util, st)
        log(f"{appid}: 就绪 route={st['route']} bits={st['bits']}")
    except Exception as e:  # 绝不影响游戏启动
        log(f"ensure 异常: {e!r}")
