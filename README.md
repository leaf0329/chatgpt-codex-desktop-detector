# ChatGPT / Codex Desktop 模型检测器

面向 Codex Desktop 的模型请求与响应观察工具，探索用户所说的“降智检测”。当前版本 **0.2.0**，主要提供本地记录核对、通信日志检查和响应文件解析。它不是 OpenAI 官方产品，也不能独立证明服务端模型身份。

## 项目目标

随 Codex Desktop 启动常驻组件，在独立提示窗口中显示每次请求的模型、响应声明的模型以及匹配状态。没有响应模型字段时显示“未提供”，请求失败与模型不一致分开处理。一轮对话可能包含多次模型请求，界面需要同时支持逐请求展示与对话归组。

以上是后续目标，当前版本尚未实现自动采集、常驻启动和外挂提示窗口。ChatGPT 网页检测暂不在当前实现范围内。

## 当前版本使用

Python 3.11+，无第三方依赖。双击 `start.bat`，打开 http://127.0.0.1:8900/ 。关闭前台服务使用 Ctrl+C；也可运行 `python server.py --port 8900`。

读取 `CODEX_HOME`（缺省为用户目录的 `.codex`）中的 `config.toml` 和 `sessions/**/*.jsonl`。选择最近 100 个本地任务之一，填写目标模型，点击检查。默认目标来自全局配置，仅作起点，不代表预期模型的独立证据。任务来源和 ID 显示在列表中；不读取任务正文作为标题。

支持最新一轮模型比对、推理强度展示、提供方记录、历史差异统计、结构化异常事件、证据行号及 JSON 报告导出。页面不会自动复查；点击检查读取最新文件。报告保留模型相关字段和本地证据路径，不含对话正文、工具输出或登录密钥。

“配置一致”不证明服务端模型身份。历史差异不等于降级。缺失字段或不完整 JSONL 会显示证据不足。默认配置未合并 profile、项目或任务覆盖，逐轮记录为检查依据。推理强度仅展示，不擅自指定预期值。

事件适配器只识别 `event_msg` 下的 error、stream_error、warning、turn_aborted、request_failed、rate_limit、retry、model_fallback；仅显示类型、时间和行号，不导出自由文本。部分类型是兼容性支持，不保证当前客户端一定写入。未知事件和文本中的“error”不作为异常证据。没有事件不代表没有失败。本地记录格式属于适配目标，客户端升级后可能需要更新。本版不读取归档任务，不进行能力测试。

只监听本机 127.0.0.1，拒绝非本机 Host；不修改 Codex、Clash 或登录状态，不发起模型请求。首次部署后台日志存放在 `.local/`，未设置开机自启。不要将此服务暴露至公网。

验证：`python -m unittest -v`。

配置字段参考：https://learn.chatgpt.com/docs/config-file/config-reference


## 通信证据（v0.2）

以只读方式查询 logs_2.sqlite，严格按所选任务 ID 过滤，只处理 WebSocket 端点和断流重试模块的最近 500 条日志。输出允许名单中的握手头：openai-model、x-request-id、content-type、upgrade、date。不会把 tracing span 的 model（请求设置）作为服务端返回模型。连接握手可能被多个轮次复用，不代表某次响应。

日志缺少 openai-model 或原始响应体时，显示未取得响应证据，不判定正常或降级。

新增响应 JSON / SSE 文件解析入口，最大 5 MB。支持 Responses 对象和 response.created/completed 等事件，拒绝仅含 model 的请求体及 turn_context。只返回响应 ID、模型、状态和数字用量；不保存或返回响应正文、工具参数、Cookie 等字段。文件来源由用户提供，不能自动证明与所选任务关联；它不是自动抓包功能。

尚未启用流量代理、TLS 解密、详细响应日志或修改 Desktop 的启动方式。诊断读取失败不影响原任务记录检查。后续采集将优先采用可退出的进程级配置，避免修改系统全局代理和系统证书库。

## 开发与版本管理

- `main` 保存可运行基线，功能通过独立分支开发。
- 使用 `VERSION`、Git 标签和 `CHANGELOG.md` 记录发布版本。
- GitHub Actions 在 Windows 和 Linux 上运行单元测试。
- 本地环境、日志、证书、抓包文件和报告禁止提交，详见 `.gitignore`。

## 参考

需求讨论参考了 [chatgpt-downgrade-detector](https://github.com/lixiaoshuang79/chatgpt-downgrade-detector)。本项目采用针对 Codex Desktop 的独立实现，不沿用匿名网页自报模型名称的判定方法。
