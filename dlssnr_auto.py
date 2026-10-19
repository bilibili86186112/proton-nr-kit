#!/usr/bin/env python3
"""dlssnr_auto.py — 给 Steam 游戏自动安装 DLSSNR-AMD 并写 Steam 配置。

用法（在 WolfLutris 容器内，以 retro 运行）：
  python3 dlssnr_auto.py --appid 550 --dry-run
  python3 dlssnr_auto.py --appid 1771300
  python3 dlssnr_auto.py --game-dir "/path/to/game" --route reshade-feeder-dx9

做的事：
  1. 从 appmanifest 找游戏目录、推断主 exe 与位数
  2. 选路由（32 位→reshade-feeder-dx9；有 DLSS/FSR/XeSS DLL→optiscaler；否则 reshade-feeder）
  3. 调用 DLSSNR-AMD 的 install.sh 安装
  4. Steam 关闭时写入 CompatToolMapping + LaunchOptions（自动备份）
  5. 可选 --localfix：生成 protonfixes localfix，实现“文件丢了自动重装”

只依赖 Python 标准库。
"""
import argparse, json, os, re, shutil, struct, subprocess, sys, time

HOME = os.path.expanduser("~")
STEAM = os.environ.get("DLSSNR_STEAM_ROOT", os.path.join(HOME, ".steam/debian-installation"))
COMMON = os.path.join(STEAM, "steamapps/common")
COMPAT_TOOL = "GE-Proton11-9-x86_64"
PKG64 = os.environ.get("DLSSNR_PKG_DIR", os.path.join(HOME, "dlssnr-test"))
PKG32 = os.environ.get("DLSSNR_PKG32_DIR", os.path.join(PKG64, "pkg32"))
STATE_DIR = os.environ.get("DLSSNR_STATE_DIR", os.path.join(HOME, ".config/dlssnr-auto"))


def log(msg):
    print(msg, flush=True)


def steam_running():
    try:
        return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0
    except FileNotFoundError:
        return False


def read_manifest(appid):
    p = os.path.join(STEAM, "steamapps", f"appmanifest_{appid}.acf")
    if not os.path.exists(p):
        return None
    txt = open(p, encoding="utf-8", errors="replace").read()
    m = re.search(r'"installdir"\s+"([^"]+)"', txt)
    return m.group(1) if m else None


def find_exe(game_dir, installdir=None):
    best, best_score = None, -1
    for root, dirs, files in os.walk(game_dir):
        depth = root[len(game_dir):].count(os.sep)
        if depth > 4:
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
            score = 0
            if installdir and (name in installdir.lower() or installdir.lower() in name):
                score += 100
            if "launcher" in name or "sndrpt" in name or "bugsplat" in name or name in ("steam", "steamerrorreporter"):
                score -= 50
            score += min(size / 1e8, 10)
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


def has_upscaler_dlls(game_dir):
    names = {"nvngx_dlss.dll", "amd_fidelityfx_upscaler_dx12.dll", "libxess.dll", "amd_fidelityfx_dx12.dll"}
    for root, dirs, files in os.walk(game_dir):
        if root[len(game_dir):].count(os.sep) > 4:
            dirs[:] = []
            continue
        if any(f.lower() in names for f in files):
            return True
    return False


def pick_route(bits, upscaler, forced):
    if forced:
        return forced
    if bits == 32:
        return "reshade-feeder-dx9"
    return "optiscaler" if upscaler else "reshade-feeder"


def find_userdata():
    ud = os.path.join(STEAM, "userdata")
    if not os.path.isdir(ud):
        return None
    for d in sorted(os.listdir(ud)):
        if os.path.isfile(os.path.join(ud, d, "config/localconfig.vdf")):
            return os.path.join(ud, d, "config/localconfig.vdf")
    return None


def vdf_add_compat(path, appid):
    s = open(path, encoding="utf-8", errors="surrogateescape").read()
    entry = ('\t\t\t\t\t"%s"\n\t\t\t\t\t{\n'
             '\t\t\t\t\t\t"name"\t\t"%s"\n'
             '\t\t\t\t\t\t"config"\t\t""\n'
             '\t\t\t\t\t\t"priority"\t\t"250"\n'
             '\t\t\t\t\t}\n') % (appid, COMPAT_TOOL)
    if re.search(r'"CompatToolMapping"\s*\{(?:[^{}]|\{[^{}]*\})*?"%s"' % appid, s, re.S):
        return False
    m = re.search(r'\t{4}"CompatToolMapping"\n\t{4}\{\n', s)
    if m:
        s = s[:m.end()] + entry + s[m.end():]
    else:
        anchor = '\t\t\t\t"CommittedDepotManifests"'
        block = '\t\t\t\t"CompatToolMapping"\n\t\t\t\t{\n' + entry + '\t\t\t\t}\n'
        if anchor not in s:
            raise SystemExit("找不到 CompatToolMapping 插入点")
        s = s.replace(anchor, block + anchor, 1)
    open(path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    return True


def vdf_set_launch_options(lc_path, appid, value):
    s = open(lc_path, encoding="utf-8", errors="surrogateescape").read()
    esc = value.replace('"', '\\"')
    block_re = re.compile(r'(\t{5}"%s"\n\t{5}\{\n)(.*?)(\n\t{5}\})' % appid, re.S)
    m = block_re.search(s)
    if not m:
        raise SystemExit(f"localconfig 里找不到 appid {appid} 的 apps 块")
    body = m.group(2)
    if '"LaunchOptions"' in body:
        body = re.sub(r'\t{6}"LaunchOptions"\t\t"[^"]*(?:\\.[^"]*)*"\n', '', body)
    body = body + '\n\t\t\t\t\t\t"LaunchOptions"\t\t"%s"' % esc
    s = s[:m.start(2)] + body + s[m.end(2):]
    open(lc_path, "w", encoding="utf-8", errors="surrogateescape").write(s)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--appid")
    ap.add_argument("--game-dir")
    ap.add_argument("--exe")
    ap.add_argument("--route")
    ap.add_argument("--dll", help="nvngx_dlssnr.dll 或其 zip（包里已有模型时不需要）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--localfix", action="store_true", help="生成 protonfixes localfix 自愈脚本")
    ap.add_argument("--skip-steam-config", action="store_true")
    ap.add_argument("--steam-restart", action="store_true", help="自动关闭并重启 Steam 以写配置")
    args = ap.parse_args()

    if args.appid:
        installdir = read_manifest(args.appid)
        if not installdir:
            raise SystemExit(f"appmanifest_{args.appid}.acf 不存在")
        game_dir = os.path.join(COMMON, installdir)
    elif args.game_dir:
        game_dir, installdir = args.game_dir, None
    else:
        raise SystemExit("需要 --appid 或 --game-dir")
    if not os.path.isdir(game_dir):
        raise SystemExit(f"游戏目录不存在: {game_dir}")

    exe = args.exe or find_exe(game_dir, installdir)
    if not exe:
        raise SystemExit("找不到主 exe，用 --exe 指定")
    bits = pe_bits(exe)
    up = has_upscaler_dlls(game_dir)
    route = pick_route(bits, up, args.route)
    pkg = PKG32 if bits == 32 else PKG64
    install_sh = os.path.join(pkg, "install.sh")

    log(f"游戏目录 : {game_dir}")
    log(f"主 exe   : {exe}  ({bits} 位)")
    log(f"DLSS/FSR : {'有' if up else '无'}")
    log(f"路由     : {route}")
    log(f"安装包   : {pkg}")
    log(f"启动选项 : 由安装器生成")

    if args.dry_run:
        log("[dry-run] 不安装、不改 Steam 配置")
        return 0

    if not os.path.exists(install_sh):
        raise SystemExit(f"安装器不存在: {install_sh}")
    cmd = ["bash", install_sh, os.path.dirname(exe), route,
           "--old-model", "--no-int4", "--no-renodx"]
    if args.dll:
        cmd += ["--dll", os.path.abspath(args.dll)]
    log("→ 执行: " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = r.stdout + r.stderr
    print(out)
    if r.returncode != 0:
        raise SystemExit(f"安装失败（{r.returncode}）")
    m = re.search(r"Steam launch options:\s*(.+)", out)
    if not m:
        raise SystemExit("没能从安装器输出里拿到启动选项")
    launch = m.group(1).strip()

    os.makedirs(STATE_DIR, exist_ok=True)
    state = {"appid": args.appid, "game_dir": game_dir, "exe": exe, "bits": bits,
             "route": route, "package": pkg, "launch_options": launch,
             "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if args.appid:
        json.dump(state, open(os.path.join(STATE_DIR, f"{args.appid}.json"), "w"), ensure_ascii=False, indent=1)

    if args.localfix and args.appid:
        write_localfix(args.appid, state)

    if not args.skip_steam_config and args.appid:
        if steam_running():
            if args.steam_restart:
                log("Steam 在运行，正在关闭它以写配置…")
                subprocess.run(["pkill", "-TERM", "-x", "steam"], capture_output=True)
                for _ in range(20):
                    if not steam_running():
                        break
                    time.sleep(1)
                log("Steam 已关闭（记得手动重新打开 Steam）")
            else:
                log("!! Steam 正在运行，跳过配置写入。可以：关掉 Steam 重跑本脚本，或加 --steam-restart")
                _print_manual(args.appid, launch)
                return 0
        cfg = os.path.join(STEAM, "config/config.vdf")
        lc = find_userdata()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for p in (cfg, lc):
            shutil.copy2(p, p + f".bak-auto-{stamp}")
        changed = vdf_add_compat(cfg, args.appid)
        vdf_set_launch_options(lc, args.appid, launch)
        log(f"Steam 配置已写入（兼容性映射{'新增' if changed else '已存在'}，启动选项已更新）")

    _print_manual(args.appid, launch)
    return 0


def _print_manual(appid, launch):
    log("")
    log("完成。启动方式：Steam 里直接启动游戏（兼容性/启动选项已自动设好）。")
    log(f"启动选项：{launch}")
    log(f"回退：bash <安装包>/install.sh \"<游戏目录>\" remove，并把 Steam 启动选项删掉")


def write_localfix(appid, state):
    d = os.path.join(HOME, ".config/protonfixes/localfixes")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{appid}.py")
    code = '''"""自动生成：DLSSNR-AMD 自愈 localfix。

- 每次启动前检查游戏目录，缺文件就重装；
- 同时设置所需环境变量，因此**不需要 Steam 启动选项**（兼容性仍需选 GE-Proton11-9）。
"""
import os, subprocess
from protonfixes import util

STATE = %r
ROUTE = STATE["route"]
GAME = STATE["game_dir"]
PKG = STATE["package"]

def _install():
    exe_dir = os.path.dirname(STATE["exe"])
    cmd = ["bash", os.path.join(PKG, "install.sh"), exe_dir, ROUTE,
           "--old-model", "--no-int4", "--no-renodx"]
    subprocess.run(cmd, check=False)

def main():
    marker = os.path.join(GAME, "dlssnr-amd-install.txt")
    if not os.path.exists(marker):
        _install()
    if ROUTE.startswith("optiscaler"):
        layer = os.path.join(os.path.dirname(STATE["exe"]), "dlssnr-amd/control/layer")
        util.set_environment("VK_ADD_LAYER_PATH", layer)
        util.set_environment("VK_INSTANCE_LAYERS", "VK_LAYER_DLSSNR_control")
        util.set_environment("WINEDLLOVERRIDES", "dxgi=n,b")
    else:
        util.set_environment("WINEDLLOVERRIDES", "winevulkan=n,b;vulkan-1=n,b")
''' % (state,)
    open(p, "w", encoding="utf-8").write(code)
    log(f"localfix 已生成: {p}")


if __name__ == "__main__":
    sys.exit(main())
