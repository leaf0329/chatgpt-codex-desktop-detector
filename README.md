# ChatGPT / Codex Desktop 模型检测器

面向 **Windows Codex Desktop** 的常驻模型观察工具。通过联动入口启动 Codex 后，在独立窗口中实时显示每次请求的模型、响应声明的模型及匹配状态，也提供本地任务记录检查。

当前版本 **v0.3.1**，用户已反馈当前环境整体可用。Desktop 联动启动仅支持 Windows Store 的 `OpenAI.Codex` 安装，ChatGPT 网页暂不支持。本项目不是 OpenAI 官方产品。

**名称一致不能证明底层模型身份或能力；名称不同也不直接等于“降智”。** 本工具比较真实请求字段与响应声明，不通过模型在对话中自报的名称判断。

## 快速安装

准备 Windows、可正常使用的 Codex Desktop，以及 **Python 3.11**（包含 pip 和 Tcl/Tk）。依赖和 CI 使用 Python 3.11，其他 Python 版本未验证。安装 Python 时勾选加入 PATH。

1. 从 [Releases](https://github.com/leaf0329/chatgpt-codex-desktop-detector/releases/latest) 下载 **Source code (zip)**，解压到长期保留的目录。也可使用 Git：

   ```powershell
   git clone --branch v0.3.1 https://github.com/leaf0329/chatgpt-codex-desktop-detector.git
   cd chatgpt-codex-desktop-detector
   ```

2. 在项目目录打开 PowerShell，确认 `python --version` 为 3.11，再执行：

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-monitor.ps1
   ```

   安装器下载依赖到项目独立 `.venv`，在桌面和开始菜单创建 **Codex Desktop - Model Monitor** 快捷方式。无需导入系统证书或配置 API 密钥。目录移动后须重跑安装器更新快捷方式。

3. **完全退出已经运行的 Codex Desktop**，再打开新快捷方式，或双击 `start-monitor.bat`。它同时启动观察窗、本地采集代理和 Codex。安装脚本本身不会启动 Codex。

4. 在 Codex 中发送正常消息，观察窗随请求更新。原来的 Codex 入口仍可使用，但普通入口启动的进程不会自动接入监测。

当前发布提供源码和安装脚本，没有独立 EXE 安装包。首次安装需要联网下载依赖。

## 如何读结果

观察窗分别显示“模型匹配”和“请求状态”。例如 **名称一致 · 连接中断** 表示已观察到相同模型名称，但没有取得响应完成事件；后续重试会保留为另一条请求，不覆盖中断记录。

| 模型匹配 | 含义 |
| --- | --- |
| 名称一致 | 请求模型与响应声明模型名称相同 |
| 名称不同 | 名称不同，需结合模型别名、服务端配置进一步判断 |
| 等待响应 | 尚未取得可用于判断的响应 |
| 响应未提供模型 | 请求已完成或停止，但未取得响应模型字段，无法比较 |
| 配对不确定 | 无法可靠关联请求和响应，不猜测对应关系 |

| 请求状态 | 含义 |
| --- | --- |
| 等待响应 / 响应中 | 尚未收到响应，或尚未取得完成事件 |
| 已完成 | 已观察到响应完成事件 |
| 连接中断 | 连接结束时未取得完成事件，可能断线、取消或重试，不能确认具体原因 |
| 服务端报错 / 响应未完成 | 收到服务端错误、失败或未完成状态 |
| HTTP 错误 | 收到 HTTP 错误状态 |
| 采集解析异常 | 采集器无法解析响应，不代表 Codex 请求一定失败 |
| 状态未知 | 采集到未识别的状态 |

请求状态不会覆盖已有模型名称的比较结果；模型名称一致也不表示请求一定完成。选中条目可查看状态解释。

一轮对话可能发出多个请求，列表按请求展示。选中条目可查看任务、轮次和响应 ID；缺失字段如实标注。WebSocket 预热请求不计入对话结果。

观察窗默认置顶，新事件自动显示，可取消勾选。右上关闭按钮仅最小化，采集继续；重复打开联动入口会复用观察窗。“停止并退出”会结束本工具启动的代理，此后应退出 Codex 并从普通入口重新启动，避免继续连接已停止的代理。

仅打开观察窗或预览演示：

```powershell
.\.venv\Scripts\pythonw.exe monitor.py
.\.venv\Scripts\pythonw.exe monitor.py --demo
```

演示使用合成数据和临时数据库，不启动 Codex，也不发送模型请求。

## 采集范围与数据

- 仅解析 `chatgpt.com/backend-api/codex/responses` 和 `api.openai.com/v1/responses`。**第三方域名、自定义 API 地址及本地中转（例如 `127.0.0.1:9097`）目前不在采集范围内**。
- 支持 WebSocket、未压缩 SSE 和非流式 Responses JSON。压缩 SSE 保持转发但报告解析异常；同连接并发无法可靠配对时标记不确定。
- 通过新启动进程的代理变量和 `CODEX_CA_CERTIFICATE` 接入，不修改系统全局代理或 Windows 证书库。客户端更新、网络或启动方式变化可能影响兼容性。
- 正文在本地代理内存中可见，用于提取字段和转发；不保存原始抓包、正文或鉴权头。持久化白名单元数据含模型、状态、时间、任务/轮次/响应标识和数字用量，存于 `.local/live.sqlite`，保留最近 1000 条。
- CA 证书和私钥位于 `.local/ca`。**分享时只分享仓库源码或 Release，不要打包自己的 `.local`、`.venv`、证书、数据库、日志或报告**。标识符和本地证据路径也可能含个人信息。

| 本机地址 | 用途 |
| --- | --- |
| `127.0.0.1:8901` | 采集代理 |
| `127.0.0.1:8902` | 观察窗单实例控制 |
| `127.0.0.1:8900` | 可选的本地记录检查页面 |

若本机 `127.0.0.1:7897` 可连接，使用它作为 HTTP 上游代理，否则直接连接。这是当前固定行为，其他上游端口暂未提供配置入口。服务仅供本机使用，不应暴露公网。

可选 `.local/launch-settings.json` 支持 `{"timezone":"America/Los_Angeles"}`，仅给联动启动进程设置 `TZ`，默认不覆盖时区。

## 常见问题

| 现象 | 检查方式 |
| --- | --- |
| 提示已有 Codex 运行，或一直无请求 | 完全退出原来的 Codex，再从 Model Monitor 入口启动；关闭窗口可能没有结束进程 |
| 无法发现 Desktop 安装 | 当前要求 Windows Store 的 `OpenAI.Codex` 包，其他发行方式未适配 |
| Python/依赖安装失败 | 确认 Python 3.11、pip 及下载网络可用，再重跑安装命令 |
| 采集器启动失败 | 检查 8901/8902 是否被其他程序占用；启动结果见 `.local/launch-result.json`（若已生成） |
| 接入后网络不通 | 确认 7897 上游是可用 HTTP 代理；退出观察窗并普通重启 Codex 可恢复原连接方式 |
| 元数据采集失败 | 检查写入权限和磁盘空间；`.local/capture-error.json` 仅记录通用错误，不含正文 |
| 响应未提供模型或配对不确定 | 证据不足，不应判定正常或降级；用下一次正常请求复查 |
| 自定义中转没有结果 | 当前允许名单不包含该地址；本地记录检查仍可用，但不能替代真实响应证据 |

反馈请使用 [GitHub Issues](https://github.com/leaf0329/chatgpt-codex-desktop-detector/issues)，附项目、Windows、Python、Codex 版本，启动方式和错误状态。不要提交密钥、证书私钥、完整对话或原始流量。

## 升级与卸载

升级前退出 Codex 和观察窗。Git 安装且没有自己的代码改动时可执行：

```powershell
git switch main
git pull --ff-only
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-monitor.ps1
```

ZIP 安装则将新版解压到新目录并运行安装器，更新同名快捷方式。新目录生成自己的 CA 和数据库，无需复制旧私钥。

卸载快捷方式：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\uninstall-monitor.ps1
```

随后退出观察窗，从普通入口重启 Codex。卸载脚本只删除指向本项目的快捷方式，保留目录和数据；确定不再使用后可自行删除项目目录。没有系统证书或全局代理需要回滚。

## 本地记录检查（可选）

此功能与常驻采集独立，无需第三方 Python 依赖。双击 `start.bat`，打开 [本地检查页面](http://127.0.0.1:8900/)，或运行 `python server.py --port 8900`。关闭前台服务使用 Ctrl+C。

读取 `CODEX_HOME`（默认用户目录的 `.codex`）中的 `config.toml`、`sessions/**/*.jsonl`。可选最近 100 个任务，检查逐轮模型、推理强度、提供方、历史差异、结构化异常和证据行号，导出 JSON 报告。默认目标来自全局配置，不自动合并 profile/项目覆盖；逐轮记录是检查依据。页面不自动复查，点击检查读取最新文件。报告不含正文、工具输出或密钥，但包含本地证据路径。

“配置一致”不证明服务端模型身份，历史差异不等于降级。记录格式变化、缺少字段或不完整 JSONL 会影响检查；不读取归档任务，不做能力测试。异常适配器仅识别明确事件类型，没有异常记录不代表没有失败。

通信诊断按所选任务读取 `logs_2.sqlite` 最近 500 条相关日志，仅提取允许的握手头及重试元数据；不会把 tracing span 的请求模型当成返回模型，复用握手也不代表单次响应。可导入最大 5 MB 的 Responses JSON/SSE，仅解析模型、响应 ID、状态和数字用量，不保存正文；来源及与所选任务的关联未经自动核验。缺少响应证据时不判定正常或降级。

## 开发与验证

```powershell
python -m unittest -v
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe smoke_proxy.py
```

GitHub Actions 在 Windows/Linux 上运行单元测试和离线传输检查。离线测试使用临时 CA、合成上游和临时数据库，验证 TLS、HTTPS/SSE、同连接多次 WSS 请求、原样转发与正文不入库，不访问真实 OpenAI 服务。当前 15 项单元测试覆盖解析、隐私过滤、配对和断线后重试等场景，真实客户端兼容性仍取决于版本和环境。

发布版本记录在 `VERSION`、Git 标签和 [CHANGELOG.md](CHANGELOG.md)。

## 参考

需求参考 [chatgpt-downgrade-detector](https://github.com/lixiaoshuang79/chatgpt-downgrade-detector)。本项目针对 Codex Desktop 独立实现。
