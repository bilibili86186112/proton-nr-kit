# 设计说明

## 目标

让“用 GE-Proton 启动游戏”这一个动作，自动带上 DLSS 5 NR（DLSSNR-AMD）所需的：
文件安装、DLL 覆盖、Vulkan 层、路由选择。

## 为什么挂在 protonfixes 上

Proton 启动任何游戏都会先跑 `protonfixes`（`proton` → `protonfixes.setup/execute`）。
`fix.py` 里的执行顺序是：

1. 本地 `localfixes/default.py`（对所有 appid 生效）
2. 本地 `localfixes/<appid>.py`
3. 全局 `gamefixes-<store>.default`（当前 umu-protonfixes 里不存在）
4. 全局 `gamefixes-<store>.<appid>`

因此 `default.py` 是**唯一一处“对所有游戏生效、又不用改 Proton”**的钩子；它也不会挡 appid 专用的全局 fix。
（如果将来上游加了全局 default，本项目应改为在其中链式调用，或在 `common.py` 里显式调用 `fix._run_fix(..., default=True)`。）

## 检测

| 项 | 方法 |
|---|---|
| 游戏目录 | `util.get_game_install_path()`（Proton 提供的 `STEAM_COMPAT_INSTALL_PATH`） |
| 主 exe | 递归（深度 ≤4）找 `.exe`，按“与目录名匹配 + 体积”打分，排除 launcher/BugSplat/steam |
| 位数 | PE 头 machine 字段：`0x8664`=64，`0x14c`=32 |
| 是否有升频器 | 目录内是否存在 `nvngx_dlss.dll` / `amd_fidelityfx_upscaler_dx12.dll` / `libxess.dll` / `amd_fidelityfx_dx12.dll` |
| 路由 | 32 位→`reshade-feeder-dx9`；64 位且有升频器→`optiscaler`；否则 `reshade-feeder` |

结果缓存在 `~/.config/dlssnr-auto/games.json`（exe 仍存在时直接用缓存，避免每次启动遍历目录）。

## 环境变量矩阵

| 路由 | 变量 |
|---|---|
| `reshade-feeder*` | `WINEDLLOVERRIDES += winevulkan=n,b; vulkan-1=n,b` |
| `optiscaler*` | `WINEDLLOVERRIDES += dxgi=n,b`；`VK_ADD_LAYER_PATH=<exe目录>/dlssnr-amd/control/layer`；`VK_INSTANCE_LAYERS=VK_LAYER_DLSSNR_control` |

用 `util.winedll_override(..., OverrideOrder.NATIVE_BUILTIN)`，由 protonfixes 负责并入 Proton 会话环境（不是直接改 os.environ）。

## 失败模式

- 探测不到 exe / 包缺失 / 安装器失败 → 写日志，跳过，游戏照常启动
- 首次安装最长 600s 超时，超时也放行
- 反作弊游戏：默认不识别，靠 `BLACKLIST` 手工排除；文档明确警告

## 做进 Proton 发行版（fork）的路线

```
dist/share/dlssnr/{x86_64,i686}/      # 不含权重
patches/protonfixes/000X-dlssnr.patch # setup_dlssnr() + compat config
proton 脚本: PROTON_USE_DLSSNR=1 → compat config "dlssnr"
```

照抄 GE 现有 `upscalers.py` 的下载器模式（manifest + md5 + prefix 目录），差别是目标目录是**游戏目录**而非 prefix。
权重只能首次运行时由用户提供（不能随发行版分发）。

## 非目标

- 不改 Proton 本体、不做 system32/umu 全局注入（资源路径按游戏目录，改全局要改上游源码）
- 不分发任何 NVIDIA/ReShade/OptiScaler 二进制
