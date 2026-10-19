# proton-nr-kit

**DLSS 5 Neural Rendering on AMD, automatically, under GE-Proton.**

把 [DLSSNR-AMD](https://github.com/mochizuki0323/DLSSNR-AMD)（Vulkan 重实现的 DLSS 5 NR）接到 Proton GE 的启动链上：在 Steam 里给游戏选 **GE-Proton11** 然后点开始，其余全自动——自动判位数、选路由、装包、设环境变量、缺文件自愈。

> 本项目只包含“自动化层”。NR 本体、ReShade/OptiScaler 二进制、NVIDIA 权重都不在本仓库内。

---

## 它是怎么工作的

```
Steam 启动游戏（GE-Proton11）
        │
        ▼
protonfixes  ~/.config/protonfixes/localfixes/default.py   ← 对所有游戏生效
        │
        ├─ common.detect()   找主 exe、判 32/64 位、选路由
        ├─ common.install()  没有安装标记 → 调 DLSSNR-AMD 的 install.sh
        └─ common.set_env()  util.winedll_override() / util.set_environment()
        ▼
游戏进程（带正确的 WINEDLLOVERRIDES / VK 层变量）
```

- 路由：32 位 → `reshade-feeder-dx9`；64 位且有 DLSS/FSR/XeSS → `optiscaler`；否则 `reshade-feeder`
- 环境变量：DX9/ReShade 路线 `winevulkan=n,b;vulkan-1=n,b`；OptiScaler 路线 `dxgi=n,b` + `VK_ADD_LAYER_PATH` / `VK_INSTANCE_LAYERS`
- 结果缓存：`~/.config/dlssnr-auto/games.json`，日志 `~/.config/dlssnr-auto/auto.log`
- 任何异常都被吞掉，**不会影响游戏启动**

## 前置条件

| 项 | 要求 |
|---|---|
| GPU / 驱动 | AMD RDNA4（gfx1200 / gfx1201），Mesa 带 `VK_KHR_cooperative_matrix` + `VK_EXT_shader_float8`（本项目用 Mesa 25.3.3） |
| Proton | GE-Proton11 系列（测试：11-7 / 11-9） |
| 游戏包 | [DLSSNR-AMD](https://github.com/mochizuki0323/DLSSNR-AMD) 的 Linux 包，解压到 `~/dlssnr-test`（64 位）与 `~/dlssnr-test/pkg32`（32 位） |
| 权重 | 包内需有 `dlssnr-amd/dlssnr.bin`（由**你自己的** `nvngx_dlssnr.dll` 310.8.0 / 310.9.16 提取，本仓库不提供） |

## 安装

```bash
git clone git@github.com:lj189cn/proton-nr-kit.git
cd proton-nr-kit
bash scripts/install.sh          # 拷 default.py/common.py 到 ~/.config/protonfixes/localfixes
```

然后：Steam → 游戏属性 → 兼容性 → **GE-Proton11**，点开始。

首次启动会多等一次安装时间；日志：

```bash
tail -f ~/.config/dlssnr-auto/auto.log
```

### 可选：命令行单游戏安装（不依赖 localfix）

```bash
python3 dlssnr_auto.py --appid 1771300 --dry-run    # 只报判断
python3 dlssnr_auto.py --appid 1771300 --localfix   # 安装 + 生成自愈脚本
```

## 已验证

| 游戏 | 结果 |
|---|---|
| Left 4 Dead 2 (550, DX9/32 位) | `reshade-feeder-dx9`；2376×1104 @ RX 9060 XT，NR 网络 15 ms/帧，ReShade 显示 57 fps |
| Kingdom Come: Deliverance II (1771300, DX12/64 位) | 识别 `optiscaler` 路由；`dlssnr_core.dll` 加载成功（游戏内表现待测） |

## 不包含

- ❌ NVIDIA 的 `nvngx_dlssnr.dll` / 提取出的权重
- ❌ ReShade / OptiScaler 二进制
- ❌ DLSSNR-AMD 本体及其安装包

## 法律与风险

- 本仓库代码 MIT。DLSSNR-AMD 是 GPL-3.0，本项目只调用其安装器，不捆绑。
- NVIDIA 的 DLL 与权重属于 NVIDIA；请使用你合法拥有的副本，不要上传/再分发。
- **不要用于带反作弊的在线游戏**。可在 `common.py` 的 `BLACKLIST` 里加 appid 避免误注入。

## 卸载

```bash
bash scripts/install.sh --uninstall
# 再对每个装过的游戏跑：
#   bash ~/dlssnr-test/install.sh "<游戏目录>" remove
```

## 设计文档

见 [docs/DESIGN.md](docs/DESIGN.md)（路由、钩子、边界、后续把逻辑做进 Proton fork 的方案）。

---

## Lutris 支持

| 用法 | 是否自动 | 说明 |
|---|---|---|
| Lutris → **Steam** → 游戏（本机就是这种） | ✅ 完全自动 | 实际是 Steam 的 GE-Proton 在跑，protonfixes 照常触发 |
| Lutris 直接用 **Proton runner**（GE-Proton） | ⚠️ 通常可以 | Proton 会跑 protonfixes；取决于 Lutris 是否传 `STEAM_COMPAT_INSTALL_PATH`，可用 `~/.config/dlssnr-auto/auto.log` 验证 |
| Lutris 用 **Wine runner**（wine-ge / lutris-GE） | ❌ 无 protonfixes | 用下面的 `--lutris` 写环境变量；文件安装仍用 `install.sh` |

Wine runner 场景两条命令：

```bash
# 1) 只装文件（不碰 Steam 配置）
python3 dlssnr_auto.py --game-dir "/games/xxx" --route reshade-feeder-dx9 --skip-steam-config

# 2) 把环境变量写进 Lutris 游戏 yml（自动匹配，或 --lutris-yml 指定）
python3 dlssnr_auto.py --game-dir "/games/xxx" --lutris
```

写入内容（`system.env`，自动备份 `.bak-dlssnr`）：

```yaml
system:
  env:
    WINEDLLOVERRIDES: dxgi=n,b                       # optiscaler 路线
    VK_ADD_LAYER_PATH: /games/xxx/dlssnr-amd/control/layer
    VK_INSTANCE_LAYERS: VK_LAYER_DLSSNR_control
```

`reshade-feeder*` 路线则只写 `WINEDLLOVERRIDES: winevulkan=n,b;vulkan-1=n,b`。
需要 `python3-yaml`（Lutris 自带依赖通常已装）。

---

## 安全开关（2026-10-19 新增）

自动注入会把 DLL 塞进游戏目录，**在线游戏/反作弊游戏必须排除**。`common.py` 现在三层保护：

| 层 | 规则 | 触发结果 |
|---|---|---|
| appid 黑名单 | Steam Linux Runtime / Proton 本体 / Diablo IV(2344520) / Overwatch 2(2357570) 等 | 跳过 |
| 路径关键词 | 路径含 `battlenet`、`blizzard`、`epic games`、`ubisoft connect`、`riot client`、`easyanticheat`、`battleye` 等 | 跳过并记日志 |
| 反作弊文件 | 目录内出现 `EasyAntiCheat` / `BattlEye` / `BEService` / `Warden` / `Vanguard` / `Ricochet` / `FACEIT` | 跳过并记日志 |

跳过时会写进 `~/.config/dlssnr-auto/auto.log`，例如：

```
[2026-10-19 11:20:01] 1234: 跳过（路径含 'battlenet'，在线/启动器前缀）
```

确实要强制（例如某个单机游戏目录恰好带 `anticheat` 字样）：

```bash
DLSSNR_ALLOW=1 <启动>
```

Lutris 里可以在游戏条目的环境变量中加 `DLSSNR_ALLOW: "1"`。

### v0.2.2 调整：启动器路径分级

| 级别 | 路径 | 行为 |
|---|---|---|
| **硬拦截** | `battlenet` / `battle.net` / `blizzard` / `riot client` / `vanguard` | 跳过（这些平台全线在线 + Warden/Vanguard） |
| **软警告** | `epic games` / `ea games` / `ubisoft connect` / `gog galaxy` | 只记日志，继续；是否安全交给反作弊检测 |
| **反作弊检测** | 目录含 `EasyAntiCheat` / `BattlEye` / `BEService` / `Warden` / `Vanguard` / `Ricochet` / `FACEIT` | 跳过 |

这样 Epic/EA/Ubisoft 的**单机游戏**（Alan Wake 2、Control、Death Stranding 等）不会被误杀，而 Fortnite/Rocket League 这类带 EAC/BattlEye 的仍会被拦。

---

## v0.3.0：启动器自动识别（Epic / GOG / Ubisoft / EA）

当 Proton 启动的是**启动器**（`EpicGamesLauncher.exe`、`GalaxyClient.exe`、`UbisoftConnect.exe`、`EADesktop.exe`）而不是游戏时：

1. 向上 4 层探测启动器 exe，识别平台
2. 从平台清单里读出**已安装游戏目录**（Epic 读 `ProgramData/Epic/EpicGamesLauncher/Data/Manifests/*.item` 的 `InstallLocation`）
3. 对每个游戏：判位数/路由/反作弊，缺文件就装
4. 设环境变量（游戏是启动器子进程，会继承）

默认策略：

| 行为 | 条件 |
|---|---|
| 只自动装 **带 DLSS/FSR/XeSS** 的游戏（`optiscaler` 路由） | 默认 |
| 也装上纯后处理（`reshade-feeder`）的游戏 | `DLSSNR_LAUNCHER_ALL=1` |
| Battle.net 启动器 | 硬跳过（策略） |
| 带 `EasyAntiCheat`/`BattlEye` 的游戏 | 跳过 |

实测（本机 Epic 前缀，dry-run）：

```
启动器 epic → 安装 DEATHLOOP（optiscaler）
跳过 Dying Light（无 DLSS/FSR，reshade 路线需 DLSSNR_LAUNCHER_ALL=1）
...
启动器模式就绪，1 个游戏
VK_ADD_LAYER_PATH=.../DEATHLOOP/dlssnr-amd/control/layer
```

限制：`VK_ADD_LAYER_PATH` 是单值，多个 `optiscaler` 游戏时只指向第一个（NR 本体仍可跑，NR Control 菜单指向第一个）；多游戏建议用 `reshade-feeder`。

---

## 模型版本（2026-10-19 更新）

DLSSNR-AMD 支持两个 NR 模型，ini 里 `[Network] Model` 切换（重启生效）：

| 值 | 模型 | 权重文件 | 速度（RX 9070 XT, 1080p） |
|---|---|---|---|
| `small` | 310.9.16 新模型（默认） | `dlssnr-small.bin`（109 MB） | 3.27 ms |
| `original` | 310.8.0 旧模型 | `dlssnr.bin`（141 MB） | 5.60 ms |

`--new-model` / `--old-model` 只影响安装后 ini 的默认值；两个模型都会装上（前提是包里有或缺 `--dll` 指向 310.9.16）。

**注意**：DLSSNR-AMD 的安装器按 **DLL 的 SHA256 白名单**（310.8.0 / 310.9.16 各一个）判版本。社区重打包的 310.9.16 变体（PE 哈希不同）会被拒；但用 `model-tools/extract_model.sh` 的权重条目哈希（599 / 255 条）可以独立验证权重是否为正品。

DLL 获取：本项目不提供。可从自己拥有的 DLSS 5 游戏，或社区镜像（如 RHI、`thx114/HoYoShadeHub-DLSSNR-Runtimes` 的 310.9.16 资产）取得，哈希自担。
