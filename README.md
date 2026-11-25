# Abaqus/CAE Bridge for Codex

让 Codex 连接已经打开的 **Abaqus/CAE**，按你的指令检查、复制或修改有限元模型，并在 CAE 窗口中查看操作结果。也可以查看作业状态、排查求解日志、读取 ODB 概览和导出视口截图。 仓库也包含无需图形桥接的 INP 检查、ODB 提取和单位换算工具。

The skill connects Codex to an open Abaqus/CAE session through a local file bridge. It supports model inspection and editing, job and log diagnostics, ODB summaries, and viewport capture.

## 可以做什么

| 场景 | 操作 |
| --- | --- |
| 接手已有模型 | 查看模型、零件、装配、集合和表面，确认对象名后再修改。 |
| 边操作边检查 | 在 CAE 中复制模型，分步调整模型并刷新视口，查看各阶段结果。 |
| 排查作业失败 | 查询作业与求解目录，结合 `.sta`、`.log`、`.msg` 和 `.dat` 定位中止或收敛问题。 |
| 快速查看结果 | 以只读方式查看 ODB 的分析步、采样帧和可用输出变量，或导出当前视口图像。 |

## 安装到 Codex

需要 **Windows、本机 Codex、可启动的 Abaqus/CAE 和可在终端调用的 Python**。仓库的工作流以 Abaqus/CAE 2021 为例。自定义 Abaqus Python 脚本应匹配你安装的 Abaqus 版本。

在 PowerShell 中运行以下命令。也可以从 GitHub 下载 ZIP，将解压后的整个目录放到 `%USERPROFILE%\.agents\skills\abaqus-cae-bridge`。确保 `SKILL.md` 和 `scripts\` 在同一层。

```powershell
$skillDir = Join-Path $env:USERPROFILE '.agents\skills\abaqus-cae-bridge'
New-Item -ItemType Directory -Path (Split-Path -Parent $skillDir) -Force | Out-Null
git clone https://github.com/zzysmilezzy/abaqus-cae-bridge-skill.git $skillDir
```

已经安装过的用户可跳过克隆，先确认你要使用的是哪个副本。如果当前会话未显示该 Skill，可以新开一个 Codex 会话。

## 首次连接

1. 打开 Abaqus/CAE，进入要检查的模型。
2. 在 Abaqus/CAE 中选择 **File → Run Script…**，运行 Skill 目录下的 [`scripts/abaqus_cae_bridge.py`](scripts/abaqus_cae_bridge.py)。
3. 看到消息区显示 `Codex Abaqus bridge watching: ...` 后，在 PowerShell 中测试连接。

   ```powershell
   $skillDir = Join-Path $env:USERPROFILE '.agents\skills\abaqus-cae-bridge'
   $sender = Join-Path $skillDir 'scripts\abaqus_bridge_send.py'
   python $sender --ping
   ```

4. 返回 `ABAQUS_BRIDGE_OK`、模型名和视口名后，就可以在 Codex 对话中发出指令。

桥接脚本默认使用 `E:\Abaqus-Codex job\.abaqus_cae_bridge`。如果没有 E 盘或该目录不可写，可指定一个本机可写目录。下面以能够调用 `abaqus` 命令的 PowerShell 为例。先设置环境变量，再从同一个终端启动 CAE。

```powershell
$env:CODEX_ABAQUS_BRIDGE_DIR = Join-Path $env:LOCALAPPDATA 'AbaqusCodexBridge'
abaqus cae
```

运行桥接脚本后，在发送端的终端也设置同一个 `CODEX_ABAQUS_BRIDGE_DIR`，或在每条发送命令末尾添加 `--bridge-dir "实际目录"`。可以从 CAE 消息区显示的 `inbox.json` 路径确认两端使用的目录。

## 给 Codex 的指令示例

- “连接我打开的 Abaqus/CAE，列出模型、零件和作业。”
- “复制当前模型，在副本上调整网格。每完成一步，刷新视口给我看。”
- “检查 `Job-1` 为什么中止，告诉我关键日志在哪个文件。”
- “读取这个 ODB 的分析步和可用输出变量，并保存当前视口截图。”

如果需要从终端直接操作，可在定义了 `$sender` 的 PowerShell 里使用以下命令。示例中的作业名与文件路径请替换为实际值。

```powershell
python $sender --get-model-info
python $sender --list-jobs
python $sender --monitor-job-status Job-1
python $sender --inspect-odb '.\Job-1.odb'
python $sender --capture-viewport '.\viewport.png'
python $sender --stop
```

要提交 CAE 中已存在的作业，可以运行 `python $sender --submit-job Job-1`。当前版本开启 Abaqus 一致性检查，提交后即返回。请用 `--monitor-job-status Job-1` 和求解日志跟踪进度。提交返回或发送端超时都不能证明求解已完成，发送端超时也不会自动取消作业。

## 离线分析

以下工具可直接检查文件，无需启动 Abaqus/CAE 的图形桥接。运行前把示例路径替换成实际路径。

| 工具 | 能做什么 | 运行环境 |
| --- | --- | --- |
| [`abaqus_diagnostics.py`](scripts/abaqus_diagnostics.py) | 对 INP 进行静态检查，或根据作业文件汇总状态和日志线索 | 系统 Python 3 |
| [`abaqus_odb_extract.py`](scripts/abaqus_odb_extract.py) | 只读提取 ODB 字段、历史输出和能量记录 | 对应版本的 Abaqus Python |
| [`abaqus_units.py`](scripts/abaqus_units.py) | 在 SI 与 N–mm–s–tonne 体系之间转换指定量 | 系统 Python 3 |

```powershell
python (Join-Path $skillDir 'scripts\abaqus_diagnostics.py') inp-check '.\Job-1.inp'
python (Join-Path $skillDir 'scripts\abaqus_diagnostics.py') monitor (Join-Path $PWD 'Job-1')
abaqus python (Join-Path $skillDir 'scripts\abaqus_odb_extract.py') '.\Job-1.odb' --field U
```

INP 检查用于发现常见问题。完整模型检查仍需使用 Abaqus。单位转换只适用于明确采用上述单位体系的任务。ODB 工具的 `ok: true` 表示提取成功，求解状态需另行核实。详见[离线分析与验证说明](references/analysis-workflow.md)。

[参考资料目录](references/upstream-catalog.md)按主题列出脚本和子程序资料。上游来源、版本和兼容性说明见[来源审查](references/source-review.md)，附带参考资料适用[上游 MIT 许可](references/upstream/LICENSE)。

## 工作方式与排查

桥接通过本地目录交换指令，模型和视口操作在 Abaqus/CAE 主线程中执行。要边看边改，可以把长任务拆成几次简短操作，让 CAE 在各步之间刷新。

- **连接超时** · 检查 CAE 消息区是否出现监听提示，核对两端的目录，并确认 CAE 当前没有被长任务占用。
- **调试已有模型** · 先查询对象名。在模型副本上试改，便于和原模型对照。
- **结束会话** · 使用 `--stop` 停止桥接。作业的停止和结果保存由 Abaqus 管理。

桥接会在当前 CAE 会话中执行接收到的 Abaqus Python。请使用自己的本地目录，并仅发送你信任的脚本。

Skill 的详细操作说明见 [`SKILL.md`](SKILL.md)。桥接端与发送端的实现分别见 [`abaqus_cae_bridge.py`](scripts/abaqus_cae_bridge.py) 和 [`abaqus_bridge_send.py`](scripts/abaqus_bridge_send.py)。
