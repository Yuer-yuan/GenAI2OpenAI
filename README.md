# GenAI2OpenAI

## 写在前面

写这个项目的时候, GenAI平台还是比较好的, 当时我也没申请API. 虽然GenAI平台实际上烂完了,但胜在免费,自己用用还是可以的. 后来申请了API, 只能说难兄难弟,没比公开的好用多少. 现在我已经不缺token了,所以维护这个repo的动力很低很低. 我建议大家玩一玩genai就够了, 最多是一些高通量的任务用一下, 除此之外别折腾了. 嫌贵可以去买那些中转服务, 一个平台可以用所有模型的那种,其实是挺好用的. 最近我看到大家对于这个项目还是挺热情的,所以参考其他人的工作补全了很多很多的功能. 当然距离一个“能用”的API还有距离, 当然这个距离我也无能为力了. 一想当GenAI刚出的时候我还是非常有信心的, Yu老师亲口说这个平台很吊, 但是我只能说烂完了(除了免费). 希望大家能利用AI改善自己的生活. 最后如果不出意外这个项目基本不会再更新了,如果有本科生小朋友愿意接手的话可以联系我(issue里直接提也可以). ciallo (∠·ω )⌒★


## 项目简介

GenAI 是一个基于 Flask 的聊天机器人接口服务，兼容 OpenAI 的聊天完成接口，利用上海科技大学的 GenAI API 进行智能对话。项目通过封装 GenAI API，支持思维链、流式响应和普通响应，从而方便客户端集成与调用。该项目适合开发具有中文支持及本地化需求的智能聊天机器人应用。

**OpenAI Compatible 功能对比**

| 能力项                                    | OpenAI 官方接口 | 本项目实现情况 | 说明                                                       |
| ----------------------------------------- | --------------- | -------------- | ---------------------------------------------------------- |
| `POST /v1/chat/completions`               | ✅ 原生支持     | ✅ 已兼容      | 入参/出参保持 OpenAI 风格，转发至 GenAI 上游               |
| `POST /v1/responses`                      | ✅ 原生支持     | ✅ 最小兼容    | 支持基础 `input`、流式与非流式输出                         |
| 流式输出（SSE）                           | ✅              | ✅             | 支持 Chat Completions 与 Responses 两条链路                |
| 非流式输出                                | ✅              | ✅             | 统一聚合上游增量后返回标准 JSON                            |
| 推理内容字段（reasoning）                 | 部分模型支持    | ✅ 兼容输出    | 通过 `reasoning_content` / `response.reasoning.delta` 暴露 |
| Tool Calling（`tools/tool_choice`）       | ✅ 原生         | ✅ 提示词兼容  | 上游无原生工具调用，本项目做 JSON 约定与本地解析           |
| 旧版函数调用（`functions/function_call`） | 已逐步废弃      | ✅ 兼容        | 自动转换为 `tools/tool_choice` 语义                        |
| 图片输入（Vision）                        | ✅              | ✅（DeepSeek 原生 / GPT 兼容） | DeepSeek 原生图文；GPT 保留旧上传模式 |
| 模型列表接口（`GET /v1/models`）          | ✅              | ✅             | 返回本项目映射后的可用模型列表                             |
| 认证头兼容（Bearer/API Key）              | ✅              | ✅             | 支持 `Authorization`、`X-Access-Token`、`api-key` 等       |

### Agent Tool 生态测试

| 客户端 / Agent | 兼容性 |
|---|---|
| Chatbox | ✅ 完美支持 | 
| Kilo Code | ❌ 不支持(模型限制) |

## 安装与运行

### 环境要求

- Python 3.11 及以上版本
- 依赖包见 `pyproject.toml`，推荐使用 uv 管理环境。

### 启动服务

#### 本机配置（macOS）

```bash
uv sync --locked
cp .env.example .env
chmod 600 .env
```

登录 [GenAI 对话平台](https://genai.shanghaitech.edu.cn/dialogue)，在浏览器开发者工具的 Network 面板发送一条消息，找到 `chat` 请求，将请求头 `x-access-token` 的值填入 `.env` 的 `GENAI_TOKEN=` 后面（不加 `Bearer`）。`.env` 已被 Git 忽略。

```bash
./start.command
# 或者
uv run --locked python main.py
```

`start.command` 也可以在 Finder 中双击启动；终端按 `Ctrl+C` 停止服务。此配置使用 `127.0.0.1:8000`，避开 macOS 常用的 5000 端口。

本机开发配置默认 `GENAI_RELOAD=1`：修改 Python 源码或 `.env` 后，服务自动重启工作进程，后续 API 请求使用新代码和配置，不必退出 Claude Code。日志、`.venv`、`temp/` 等目录的变化不会触发重载。重载时正在进行的请求可能中断，需要重试；这不是在原进程内替换函数。`/health` 的 `runtime` 会显示工作进程 PID、重载开关和日志级别。关闭可设置 `GENAI_RELOAD=0` 或运行 `./start.command --no-reload`；关闭后，重新开启需要再次启动服务。

程序每次启动会自行读取 `.env`，因此开发重载时请使用上述命令，不要额外用 `uv --env-file` 将文件内容固定到父进程环境。显式环境变量和命令行参数仍优先于 `.env`。监听地址由父进程持有，修改 host/port 需手动重启服务，并同步调整客户端连接地址。此重载范围是 API 服务代码与 `.env`；`tests/`、`tools/` 不会触发 API 重载，避免编写 benchmark 时打断实际请求。独立工具脚本、依赖安装和 Claude Code 设置需重新启动相应进程才生效。

在 Chatbox 等支持 OpenAI 兼容接口的客户端中填写：

- 服务商：OpenAI 兼容 / 自定义 OpenAI
- API Base URL：`http://127.0.0.1:8000/v1`
- API Key：与 `.env` 中相同的 GenAI Token（请求中的 Key 会覆盖服务端 Token）
- 模型：`deepseek-pro`（2026-11-02 本机已通过真实对话验证；平台显示为 DeepSeek-V4.1-Flash）。项目历史模型表可能已过时，本次验证中 `deepseek-v3` 的上游返回“未找到模型”。

健康检查：`curl http://127.0.0.1:8000/health`；查看内置模型：`curl http://127.0.0.1:8000/v1/models`。

支持的配置为 `GENAI_TOKEN`、`GENAI_UPLOAD_TOKEN`、`GENAI_HOST`、`GENAI_PORT`、`GENAI_LOG_LEVEL`、`GENAI_RELOAD`，以及可选的 `GENAI_CLAUDE_HELPER_MODEL`。从项目 `.env` 读取默认值，显式环境变量可覆盖它们，命令行参数优先。

#### 命令行启动

```bash
uv run main.py [--token <token>] [--account <student_id@password>] [--upload-token <upload_token>] [--log-level INFO] [--port 5000]
```

端口默认 5000。服务将在本地 `0.0.0.0:5000` 端口启动。

可选参数：

- `--token` ：若不在启动时提供，可由客户端在每次请求中通过 `Authorization: Bearer <token>` 或其他兼容 API key 请求头传递。
- `--account`：上海科技大学统一身份认证账号，格式为 `学号@密码`。当未提供 `--token` 时，服务启动时会自动登录并获取 GenAI token。
- `--upload-token`：图片上传接口 `token` 请求头值（默认内置项目当前可用值）。
- `--log-level`：控制台日志级别，支持 `DEBUG / INFO / WARNING / ERROR / CRITICAL`，默认 `INFO`。
- `--reload` / `--no-reload`：开启 / 关闭本地开发自动重载；独立运行且未配置时默认关闭，示例 `.env` 中开启。

## 功能和用法

- 兼容 OpenAI API，支持 `POST /v1/chat/completions`、`POST /v1/responses`接口，实现智能聊天功能。
- 支持流式（stream）及非流式响应，方便高效地获取 AI 回复。
- `POST /v1/chat/completions` 支持基于提示词工程和 JSON 解析的 OpenAI `tools`/`tool_choice` 兼容工具调用，也兼容旧版 `functions`/`function_call` 入参。
- `POST /v1/chat/completions` 支持图片输入：DeepSeek 保留原生多模态内容，GPT 默认沿用图片上传兼容模式。
- 提供 `/v1/models` 接口列出可用模型，如 `deepseek-pro`、`deepseek-chat`、`gpt-5.5`、`glm-5.1` 等。
- 内置 `/health` 健康检查接口，用于服务状态监测。

### Claude Code（GLM / DeepSeek）

项目现在同时提供 Anthropic 格式的 `POST /v1/messages` 和 `POST /v1/messages/count_tokens`。Claude Code 可直接连接同一个本地服务，不需要额外的协议转换服务。

先按前面的本机配置填写 `.env` 的 `GENAI_TOKEN`。在希望使用 Claude Code 的目录中运行：

```bash
# 当前目录就是 GenAI2OpenAI 时
./claude.command
./claude.command --model deepseek

# 当前目录是本项目的上一层时
./GenAI2OpenAI/claude.command
./GenAI2OpenAI/claude.command --model deepseek
```

启动器会检查本地服务，必要时自动启动，并为**当前目录**生成 `.claude/settings.local.json`。默认模型为已通过工具与识图验收的 `deepseek`；在会话中可用 `/model glm` 和 `/model deepseek` 切换。模型别名对应当前平台的 `chatglm`（GLM-5.3-Flash）和 `deepseek-pro`（DeepSeek-V4.1-Flash），不是 Claude 模型。

启动器默认传入 `--permission-mode bypassPermissions`，工具调用（包括 Bash）自动执行；已有明确的 deny 规则仍由 Claude Code 处理。同时，项目配置设置 `disableAutoMode: "disable"`，默认关闭 Auto 模式，避免权限分类器不可用时拦住 Bash。此模式按本机用户要求设置，不依赖学校模型提供 Claude Code 的 Auto 模式权限分类器。新版 Claude Code 不接受仅从项目配置开启 `bypassPermissions`，因此需要使用启动器，或直接运行 `claude --permission-mode bypassPermissions`。若想逐次确认工具操作，可用 `./claude.command --permission-mode manual`。

已打开的 Auto 模式会话不会因为配置文件更新就切换模式。先退出旧会话，再从本项目上一层目录执行 `./GenAI2OpenAI/claude.command --model deepseek -- --continue`，可用新的权限模式继续原会话。

如果只想生成配置，再自己启动 Claude Code：

```bash
# 从 GenAI2OpenAI 目录执行，为上一层目录配置
uv run --locked python tools/claude_code.py setup --directory ..
# 先用 start.command 启动服务，再在配置的目录执行 claude --permission-mode bypassPermissions
```

配置使用 `apiKeyHelper` 按需从本项目 `.env` 读取 Token，不把 Token 复制到 Claude 配置，也不修改用户级的 `~/.claude/settings.json`。开启重载后，Token 更新会自动重启 API 服务；Claude Code 可能缓存 apiKeyHelper 的旧值，更新 Token 后应重开 Claude Code。只修改 API 服务源码无需退出 Claude Code。Claude Code 的 `ANTHROPIC_BASE_URL` 不带 `/v1`，例如 `http://127.0.0.1:8000`。启动器的服务日志位于 `.logs/server.log`。

兼容范围：

- 支持系统提示词、文本消息、客户端工具定义、`tool_use` / `tool_result` 往返，以及 Anthropic SSE 流式事件。
- 普通文本逐段转发；带工具的请求沿用本项目的提示词工具调用，需要先收集完整输出再转换为 `tool_use`。工具调用能力仍取决于上游模型。
- 这不是原生 DeepSeek / GLM 工具协议的无损透传。当前学校聊天接口在标准 `tools` / `tool_choice` 探测中没有返回原生工具调用，网关因此使用提示词约定。Claude Code 路径要求模型输出工具 JSON 或 `{"final":"回答"}`；格式不合法时最多进行一次纠正，仍不合法则返回错误，避免把未执行的操作误报为完成。解析器兼容对象、OpenAI 工具调用数组及 XML 工具块。
- Token 计数使用 `cl100k_base` 估算，不代表 GLM / DeepSeek 的精确用量。没有原生 Anthropic 提示词缓存或签名思考块；服务端工具目前支持 `web_search`。图片块的处理见下文，文档输入仍不支持。
- Claude Code 对自定义模型显示的费用与上下文信息也只是客户端估计，不能用作平台账单或模型上限。上游偶尔返回空回复时会明确报错，由客户端决定重试。
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS=8192` 是单次生成长度限制，不是上下文窗口。出现“我来写/运行”但没有文件或命令结果时，应先检查工具调用链路，不能仅据此认定上下文不足。
- 本地验证：`uv run --locked python -m unittest discover -s tests -v`。

工具调优现采用统一的 JSON 历史：保留工具名、调用 ID、参数对象及结果状态，避免把参数字符串再次转义；执行结果附带继续原任务的说明。实际调用前校验参数 JSON Schema，并执行 `tool_choice` 约束，错误最多纠正一次。标准上游 `tool_calls` SSE 增量也会收集和校验，但不能据此认定学校接口完整暴露了原生工具协议。`GENAI_TOOL_HISTORY` 默认 `tagged`；`legacy` 可回放旧格式，`native` 为诊断选项，本轮完整测试中它导致 DeepSeek 多轮空回复，因此不作为默认。

`tool_result.content` 可以合法包含 `image`。网关接受 base64 / URL 图片与混合文字，并保留真实图片。DeepSeek 原生视觉使用多模态 `content`，不再把图片丢弃、转成占位文字或错误地使用旧 `imageUrl` 字段；工具结果保留调用 ID 和名称，实际图片作为 user 图文内容送给模型。支持单图、多图及直接用户图片，不会自动切换到 GPT。Anthropic `file_id` 无法用学校接口解析，会返回要求提供 base64 / URL 的明确错误。图像计数按每张最多 1024 token 作粗略估算，不把 base64 当正文计数，不能用作计费依据。

`GENAI_IMAGE_TRANSPORT=auto` 默认对非 GPT 路由保留原生图文，GPT 保持旧版单图上传；`native` 可强制原生模式，`legacy` 使用旧 GPT 上传模式。格式放行不等于模型具备视觉能力：本次已验证的是学校 DeepSeek 通道，GLM 的文字工具测试不能当作识图通过。DeepSeek Flash 的视觉格式见 [官方说明](https://api-docs.deepseek.com/guides/vision/)。

图片效果验收包含随机文字、图形计数、颜色位置、图表、表格、小字、多图、中英文，以及无图片对照；测试不把答案写入提示词。见 [视觉验收结果与测试图](benchmarks/vision/README.md)。可在项目上一层执行 `./GenAI2OpenAI/vision-benchmark.command` 复跑；仅测接口是否返回 200、或只声明“无法看图”，均不能通过此验收。

工具质量测试已与生成速度测试分开：固定 BFCL 抽样、真实文件与 Python 多步执行、Claude Code 全流程，以及调优前后同题比较，详见 [工具 benchmark](benchmarks/README.md) 和 [本次实测报告](benchmarks/reports/tool-tuning.md)。小样本结果用于本项目回归，不是官方 BFCL 排名分数。

真实编码验证（会调用学校模型并使用 Claude Code 的 Read / Write / Bash 工具，产物在忽略提交的 `temp/` 目录）：

```bash
# 在已经配置 Claude Code 的目录执行；下面以本项目的上一层目录为例
uv run --project GenAI2OpenAI --locked python GenAI2OpenAI/tools/verify_claude_code.py --model deepseek
```

此检查要求 Claude Code 实际创建并执行 quicksort 程序，不能仅返回计划或代码文本；还会独立验证 104 组排序输入。默认不作为离线单元测试运行。

#### 联网与其他工具

当前 DeepSeek 接入的工具范围和验证状态：

| 能力 | 工具 / 接入方式 | 验证内容 |
| --- | --- | --- |
| 文件读写与修改 | Read / Write / Edit | 创建文件、读取内容、精确替换并核对结果 |
| 工具图片返回 | Read / Write / Bash | 读取 PNG，识别代码与图形，写 JSON 并实际运行检查 |
| 文件发现与代码搜索 | Glob / Grep | 找到文件和其中的指定标记 |
| 命令执行 | Bash | 实际运行 Python 程序和断言 |
| 网页读取 | WebFetch | 抓取网页，再使用当前模型提取页面标题 |
| 网络搜索 | WebSearch | 真实查询公共搜索服务并返回标题、网址和摘要 |
| 任务管理 | TaskCreate / TaskUpdate / TaskList | 创建任务、标记完成并查询状态 |
| 自定义客户端工具 | 标准 MCP 工具格式 | 协议测试覆盖定义、参数和文本/检索结果；未配置外部 MCP 服务，服务器连接仍由 Claude Code 管理 |

`WebSearch` 使用 Anthropic 的 `web_search_20250305` 工具协议：网关通过 DDGS 查询 DuckDuckGo，失败或只有明显无关的结果时尝试 Yahoo，返回 `server_tool_use`、`web_search_tool_result`、真实来源网址及搜索次数。已停用曾把排序算法查询返回为测速、登录页面的 Bing RSS 路径。支持 `max_uses`、`allowed_domains` 和 `blocked_domains`，每种搜索工具每请求最多执行 8 次。会进行基本的查询词匹配检查，过滤明显跑题的结果；这不是完整的语义相关性判断，来源内容仍需核实。全部失败会返回搜索错误块，不会编造结果。公共搜索服务可能限流或改变返回格式。

协议转换可以把模型输出转换为 Claude Code 可执行的 `tool_use`，并将实际 `tool_result` 回传给模型；格式转换本身不保证搜索质量或任务完成。对于已要求运行、当前轮还没有 Bash 执行结果的请求，适配器会识别部分“要我运行吗 / I'll run it”式提前结束，进行一次纠正；仍不符合协议时返回错误。这项检查有意保持有限范围，不能验证任意自然语言任务是否完成，也不会绕过客户端的权限规则。

`WebFetch` 沿用 Claude Code 原生抓取与提取流程。由于此环境无法完成 Anthropic 域名预检查，项目设置 `skipWebFetchPreflight: true`，取消该项外部服务依赖；这是本项目配置，不修改全局设置。原生提取仍会调用本地模型。Sonnet / Opus / Haiku 辅助模型默认使用启动器选中的模型；硬编码的 `claude-*` 请求会映射到 `GENAI_CLAUDE_HELPER_MODEL`（默认 `deepseek`），`deepseek-flash` 也可作为当前 DeepSeek 模型的请求别名。

当当前环境只有 `socks5h://` 等 SOCKS 代理时，启动器会启动一个仅监听 `127.0.0.1` 的 HTTP CONNECT 转接，再让 Claude Code 使用它。这样 WebFetch 可以使用原有 SOCKS 连接，不会出现 `Protocol "socks5h:" not supported`。系统代理不变；`localhost` 和 `127.0.0.1` 仍直连。转接日志和端口记录在 `.logs/proxy.log`、`.logs/proxy.json`。

自定义模型默认没有任务管理工具时，启动器设置 `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` 将它们开启。MCP 客户端工具的输入和文本结果可以正常往返，检索结果块及工具引用也会转换为带来源的文本；未预装第三方 MCP 服务。图像、PDF 和 Anthropic 托管的代码执行服务并不因为开启工具权限就变成可用能力。

可重复执行的工具验证：

```bash
# 从本项目上一层目录执行，默认分别检查网页读取、搜索、文件工具链和任务管理
uv run --project GenAI2OpenAI --locked python GenAI2OpenAI/tools/verify_claude_tools.py

# 也可以只检查其中一类
uv run --project GenAI2OpenAI --locked python GenAI2OpenAI/tools/verify_claude_tools.py --case websearch

# 复现完整的搜索排序算法、创建基准程序、执行并核对输出流程
uv run --project GenAI2OpenAI --locked python GenAI2OpenAI/tools/verify_claude_tools.py --case workflow
```

这些是联网实测，会调用学校模型；工作流检查要求实际 WebSearch、Write、Bash 成功，并独立重新执行生成的程序验证输出。普通 `unittest` 测试仍可离线运行。更新配置后，应退出旧 Claude Code，再通过 `claude.command -- --continue` 重新进入，确保新的权限和代理设置生效。

参考：[Claude Code 网关配置](https://code.claude.com/docs/en/llm-gateway-connect)、[Anthropic 流式事件格式](https://platform.claude.com/docs/en/build-with-claude/streaming)。

### 支持模型

| 模型 id           | 可用性 | 思维链 | 实测上下文长度     | first_token_delay | 输出速度       |
| ----------------- | ------ | ------ | ------------------ | -------------- | -------------- |
| deepseek-r1       | ✅     | ✅     | ~100k-128k tokens  | 0.880s         | 73.04 tokens/s | 
| deepseek-v3       | ✅     | ❌     | ≥200k tokens       | 0.917s         | 83.85 tokens/s | 
| glm-5.1           | ✅     | ❌     | ≥200k tokens       | 0.874s         | 98.15 tokens/s | 
| minimax-m1        | ✅     | ✅     | ≥200k tokens       | 0.827s         | 129.94 tokens/s |
| qwen3.5-397b-a17b | ✅     | ✅     | <100k tokens       | 0.851s         | 2.47 tokens/s  | 
| gpt-5.5           | ✅     | 隐藏   | 未测试（额度限制） | 5.639s         | 128.93 tokens/s |
| gpt-5.4           | ✅     | 隐藏   | 未测试（额度限制） | 4.205s         | 107.74 tokens/s |
| gpt-5.2           | ✅     | 隐藏   | 未测试（额度限制） | 2.940s         | 142.57 tokens/s |
| gpt-5             | ✅     | 隐藏   | 未测试（额度限制） | 41.525s        | 87.74 tokens/s | 
| gpt-4.1           | ✅     | 隐藏   | 未测试（额度限制） | 2.534s         | 133.66 tokens/s |
| gpt-4.1-mini      | ✅     | 隐藏   | 未测试（额度限制） | 2.385s         | 81.96 tokens/s | 
| gpt-o4-mini       | ✅     | 隐藏   | 未测试（额度限制） | 11.030s        | 175.94 tokens/s |
| gpt-o3            | ✅     | 隐藏   | 未测试（额度限制） | 11.612s        | 254.31 tokens/s |
| deepseek-pro      | ✅     | 未知   | 未测试             | 1.012s         | 62.13 tokens/s | 
| deepseek-chat     | ✅     | 未知   | 未测试             | 0.983s         | 19.62 tokens/s | 

兼容层同时兼容历史请求名和底层模型名，详见[模型列表](docs/模型列表.md)。
以上信息最后更新于 `2026-05-08`。

### 测试模型上下文长度

项目内置 `context_length_tester` skill，可用于测试模型的实际上下文处理能力：

```bash
# 大海捞针测试（推荐）
uv run tools/skills/context_length_tester/context_length_tester.py --model deepseek-v3

# 快速探测 API 上限
uv run tools/skills/context_length_tester/context_length_tester.py --model deepseek-v3 --mode probe
```

测试方法采用**大海捞针法**（Needle in a Haystack）：在长文本中间插入关键信息，验证模型能否准确检索。这比简单的二分查找更能反映模型的真实上下文处理能力。

**注意**：Azure GPT 模型有严格的额度限制，无法进行上下文长度测试。建议参考各模型的官方文档了解其标称上下文长度。

### 工具调用兼容

上游 GenAI API 没有原生 tool calling 能力。本项目在 Chat Completions 接口中通过系统提示词要求模型输出工具调用 JSON，并在本地解析为 OpenAI 兼容的 `tool_calls`：

```json
{
  "model": "gpt-5.5",
  "messages": [{ "role": "user", "content": "上海今天适合带伞吗？" }],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "查询城市天气",
        "parameters": {
          "type": "object",
          "properties": {
            "city": { "type": "string" }
          },
          "required": ["city"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

如果模型决定调用工具，非流式响应会返回 `finish_reason: "tool_calls"` 和 `message.tool_calls`。流式请求也会返回兼容的 `tool_calls` chunk，但为了可靠解析 JSON，带工具的流式请求会先在服务端收集完整上游输出后再发送结果。

兼容性补充：

- 解析优先级为 **JSON 优先**；
- 同时兼容 XML 标签形式的工具调用块：`<tool_call>{"name":"...","arguments":{...}}</tool_call>`；
- 当模型输出多个 `<tool_call>...</tool_call>` 块时，会按顺序解析为多个 `tool_calls`。

### 图片输入

`/v1/chat/completions` 支持 OpenAI 常见多模态消息格式：

- `type: "image_url"` + `image_url.url`（可传公网图片 URL）
- `type: "input_image"` + `image_url.url` / `url`
- 支持 `data:image/...;base64,...` 的 data URL

DeepSeek 原生模式将文本和 `image_url` 内容块直接发送到学校接口，图片不会变成提示词中的 base64 字符串，也无需配置图片上传 Token。Anthropic 用户消息及 `tool_result` 中的 `image` 会转换为同样的多模态结构。

GPT 旧上传兼容模式的处理流程：

1. 从最后一条包含图片的用户消息或工具结果提取图片输入。
2. 自动调用 GenAI 图片上传接口 `https://genaipic.shanghaitech.edu.cn//sys/common/upload`。
3. 将返回的 `imageUrl`、`width`、`height` 透传到上游对话请求。

限制：

- DeepSeek 图像能力已进行真实效果验收，当前请求无需切换模型或调用 GPT 辅助。
- 旧 GPT 上传模式每条消息只支持一张图片；多图需使用兼容原生多模态的模型及 `GENAI_IMAGE_TRANSPORT=native`。

示例：

```bash
curl http://127.0.0.1:5000/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "text", "text": "这张图里有什么？"},
          {
            "type": "image_url",
            "image_url": {
              "url": "https://example.com/demo.jpg"
            }
          }
        ]
      }
    ]
  }'
```

## Token 获取

1. 首先前往[GenAI 对话平台](https://genai.shanghaitech.edu.cn/dialogue)
2. 打开浏览器开发者工具，随便发送一条消息，捕获名为`chat`的请求
3. 复制请求标头中的`x-access-token`字段，即为`<token>`

服务启动时可通过 `--token <token>` 设置默认 GenAI token；也可通过 `--account <学号@密码>` 在启动时自动登录获取 token。客户端也可以通过传统的 API key 传递 token，此时请求级 key 会覆盖启动参数中的默认 token，并作为上游 GenAI 的 `X-Access-Token` 使用。

支持的请求头：

- `Authorization: Bearer <token>`（推荐，兼容 OpenAI SDK）
- `X-Access-Token: <token>`
- `api-key: <token>`
- `X-API-Key: <token>`

示例：

```bash
curl http://127.0.0.1:5000/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v3","messages":[{"role":"user","content":"你好"}]}'
```

![图片说明](images/chrome.png)

仅 GPT 旧上传模式需要捕获 `upload` API 的请求头 `token` 并配置 `--upload-token`；DeepSeek 原生图文不需要此上传 Token。

## 开发与贡献指南

- 欢迎 fork 并提交 PR，改进功能或修复 bug。
- 请遵守项目代码风格，代码中请添加必要注释。
- 贡献代码时建议附带测试，确保功能完整性。
- 遇到问题可通过 issue 反馈。

## 联系方式与许可

- 联系邮箱：arnoliu@shanghaitech.edu.cn
- 本项目采用 MIT 许可证，详见 LICENSE 文件。
