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
