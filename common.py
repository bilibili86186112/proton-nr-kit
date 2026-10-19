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
# 硬拦截路径：这些平台的游戏全部在线 + 强反作弊（Warden/Vanguard），不要注入
HARD_BLOCK_PATHS = ("battlenet", "battle.net", "blizzard", "riot client", "vanguard",
                    "steamapps/common/steamworks")
# 软警告路径：启动器前缀里也有单机游戏，只警告不拦（是否安全交给反作弊检测）
WARN_PATHS = ("epic games", "ea games", "ubisoft connect", "gog galaxy")
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
    return next((p for p in HARD_BLOCK_PATHS if p in low), None)


def warned_by_path(game_dir):
    low = game_dir.lower().replace("\\", "/")
    return next((p for p in WARN_PATHS if p in low), None)



# ---------------------------------------------------------------- launcher mode
LAUNCHER_EXES = {
    "epicgameslauncher.exe": "epic",
    "battle.net.exe": "battlenet",
    "galaxyclient.exe": "gog",
    "ubisoftconnect.exe": "ubisoft",
    "upc.exe": "ubisoft",
    "eadesktop.exe": "ea",
}
SKIP_DIR_NAMES = {"launcher", "directxredist", "directx", "redist", "common files", "support"}


def _listdir_lower(d):
    try:
        return {n.lower(): n for n in os.listdir(d)}
    except OSError:
        return {}


def detect_launcher(game_dir):
    p = os.path.abspath(game_dir)
    for _ in range(4):
        names = _listdir_lower(p)
        for exe, kind in LAUNCHER_EXES.items():
            if exe in names:
                return kind, p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return None, None


def find_drive_c(path):
    p = os.path.abspath(path)
    while True:
        if os.path.basename(p).lower() == "drive_c":
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def _win_to_linux(drive_c, winpath):
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", winpath or "")
    if not m or m.group(1).upper() != "C":
        return None
    return os.path.join(drive_c, m.group(2).replace("\\", "/"))


def epic_games(drive_c):
    """从 Epic 的 manifests 读出已安装游戏目录。"""
    out = []
    mani = os.path.join(drive_c, "ProgramData/Epic/EpicGamesLauncher/Data/Manifests")
    if not os.path.isdir(mani):
        return out
    for f in os.listdir(mani):
        if not f.endswith(".item"):
            continue
        try:
            d = json.load(open(os.path.join(mani, f), encoding="utf-8"))
        except Exception:
            continue
        loc = _win_to_linux(drive_c, d.get("InstallLocation", ""))
        name = d.get("DisplayName") or f
        if loc and os.path.isdir(loc):
            out.append((name, loc))
    return out


def launcher_games(kind, drive_c):
    if kind == "epic":
        return epic_games(drive_c)
    # battle.net / ubisoft / ea：暂不自动扫描（battlenet 本身被硬拦）
    return []


def ensure_launcher(util, appid, kind, root):
    drive_c = find_drive_c(root)
    if not drive_c:
        log(f"{appid}: 启动器模式，但找不到 drive_c（{root}）")
        return
    games = launcher_games(kind, drive_c)
    if not games:
        log(f"{appid}: 启动器模式 {kind}，没找到可扫描的游戏清单")
        return
    dry = os.environ.get("DLSSNR_DRY", "") in ("1", "true", "yes")
    allow = os.environ.get("DLSSNR_ALLOW", "") in ("1", "true", "yes")
    all_games = os.environ.get("DLSSNR_LAUNCHER_ALL", "") in ("1", "true", "yes")
    done, opti = [], []
    for name, gdir in games:
        if os.path.basename(gdir).lower() in SKIP_DIR_NAMES:
            continue
        ac = has_anticheat(gdir)
        if ac and not allow:
            log(f"{appid}: 跳过 {name}（反作弊痕迹 '{ac}'）")
            continue
        st = detect(gdir, "L:" + gdir)
        if not st:
            continue
        if not st["route"].startswith("optiscaler") and not all_games:
            log(f"{appid}: 跳过 {name}（无 DLSS/FSR，reshade 路线需 DLSSNR_LAUNCHER_ALL=1）")
            continue
        if not os.path.exists(os.path.join(gdir, MARKER)):
            log(f"{appid}: 启动器 {kind} → 安装 {name}（{st['route']}）")
            if not dry and not install(st):
                continue
        else:
            log(f"{appid}: 启动器 {kind} → {name} 已安装（{st['route']}）")
        done.append((name, st))
        if st["route"].startswith("optiscaler"):
            opti.append((name, st))

    if not done:
        return
    if opti:
        # VK 层是单值：取第一个 optiscaler 游戏；其余游戏 NR 仍可跑，只是 NR Control 菜单指向第一个
        name, st = opti[0]
        layer = os.path.join(os.path.dirname(st["exe"]), "dlssnr-amd/control/layer")
        util.set_environment("VK_ADD_LAYER_PATH", layer)
        util.set_environment("VK_INSTANCE_LAYERS", "VK_LAYER_DLSSNR_control")
        util.winedll_override("dxgi", getattr(util.OverrideOrder, "NATIVE_BUILTIN", "n,b"))
        if len(opti) > 1:
            log(f"{appid}: 注意：{len(opti)} 个 optiscaler 游戏，VK 层只指向 {name}")
    else:
        order = getattr(util.OverrideOrder, "NATIVE_BUILTIN", "n,b")
        util.winedll_override("winevulkan", order)
        util.winedll_override("vulkan-1", order)
    log(f"{appid}: 启动器模式就绪，{len(done)} 个游戏")


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
        lkind, lroot = detect_launcher(game)
        if lkind:
            if lkind == "battlenet" and not allow:
                log(f"{appid}: 启动器 Battle.net，按策略跳过")
                return
            ensure_launcher(util, appid, lkind, lroot)
            return
        hit = blocked_by_path(game)
        if hit and not allow:
            log(f"{appid}: 跳过（路径含 '{hit}'，在线/反作弊平台）")
            return
        warn = warned_by_path(game)
        if warn:
            log(f"{appid}: 注意（路径含 '{warn}' 启动器前缀），继续依赖反作弊检测")
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
