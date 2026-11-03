# 工具调用 benchmark

本套测试面向上海科技大学 GenAI → 本地网关 → Claude Code 的工具调用链路。`tools/benchmark_models.py` 仍只测生成速度；本目录测调用是否正确、工作是否实际完成。

从项目上一层目录可直接执行 `./GenAI2OpenAI/benchmark.command --split all`；启动器会使用锁定的项目依赖。默认调用 DeepSeek 与 GLM，报告保存到项目的 `temp/benchmarks/`。

## 测什么

| 层次 | 测试内容 | 验收方式 |
| --- | --- | --- |
| BFCL 固定抽样 | 单工具、多工具选择、并行调用、无关工具拒用 | 工具名与参数逐项匹配，调用一一对应，不能只返回合法 JSON |
| 本地回传 | 读后写、错误恢复、中英文继续执行、缺参澄清、工具结果中的指令、执行后的总结 | 核对下一步调用、参数或实际结果标记 |
| 多步执行 | 读数据写排序脚本并运行、修复程序并运行、读取文件指针后计算、文件缺失后的恢复 | 真实文件、真实 Python 子进程、独立状态与输出检查；最终回复须包含运行后才产生的 run_id |
| Claude Code | WebFetch、WebSearch、Read 图片、Glob/Grep/Read/Edit/Write/Bash、任务管理、搜索→写程序→运行 | 真正启动 Claude Code，检查工具结果和磁盘状态；图片项必须正确识别像素事实、写 JSON 并执行检查，拒绝识图不算成功 |

BFCL 数据来自 [Berkeley Function Calling Leaderboard](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard)，固定到 `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8`。四类各用固定随机种子抽取 6 题，共 24 题；每类前 3 题为 dev、后 3 题为 holdout。本地另有 12 题，总计 36 个不同任务；每个 split 18 题。模型看到的请求不含标准答案。

BFCL 片段使用本地严格 JSON 参数评分器，允许标准答案显式列出的选项、可省略参数及调用乱序；没有复刻官方 AST 评分的所有宽松等价规则，因此**分数不是官方 BFCL leaderboard score**。抽样与类型转换规则、原文件 SHA256、固定版本在 `bfcl_sample.json`；来源许可见 `BFCL_LICENSE`。

## 直接运行

以下命令均在 `GenAI2OpenAI` 目录执行。先完成 `uv sync --locked` 并在项目 `.env` 配置 `GENAI_TOKEN`；benchmark 会调用真实学校模型。Token 不写入报告。

```bash
# 默认 DeepSeek 与 GLM，各题两次；直接使用已保存的数据，不需要重新下载
uv run --locked python tools/benchmark_tools.py --split all

# 开发中先跑本地任务；调整后用未参与调参的题验收
uv run --locked python tools/benchmark_tools.py --suite local --split dev
uv run --locked python tools/benchmark_tools.py --split holdout --repeats 3

# 可选 CI 门槛：每个模型的总体成功率至少 85%
uv run --locked python tools/benchmark_tools.py --split all --min-success-rate 0.85

# 真实 Claude Code 工作流；为测试工作目录生成其本地配置
uv run --locked python tools/verify_claude_tools.py --directory .. --model deepseek --case all --report temp/claude-deepseek.json
uv run --locked python tools/verify_claude_tools.py --directory .. --model glm --case all --report temp/claude-glm.json

# 验证 Read 返回 image 后，实际识别、写文件、运行的完整流程
uv run --locked python tools/verify_claude_tools.py --directory .. --model deepseek --case image

# 视觉效果：随机测试图、标准答案，以及无像素对照
uv run --locked --group vision python tools/benchmark_vision.py --models deepseek --seed 93841

# 离线回归（含真正启动本地重载服务、评分器反例；不请求学校模型）
uv run --locked python -m unittest discover -s tests -q
```

`benchmark_tools.py` 直接调用与 API 共用的准备、生成、解析、校验函数，并通过真实学校网络接口生成；它绕过本地 HTTP 这一跳，以便在同一运行环境中加载旧版本。Claude Code 测试单独覆盖 HTTP/SSE、客户端权限和完整 agent 提示词。不要把这两个层次的分数混成一个指标。

默认 `--jobs 2`，最多允许 4；`--models deepseek` 可只测一个模型。`--output` 指定报告路径。默认输出到忽略提交的 `temp/benchmarks/`，每题结束后原子保存，`complete` 为 true 才是完整结果。单题失败会保留原始输出，继续测试其余题；默认完成测试退出 0，指定成功率门槛时低于门槛退出 1。中断的半份报告不能参与对比。

报告记录每题成败、调用参数、原始模型输出、工具结果、真实执行校验、额外纠正请求、提示词字符数和耗时。字符数不是 token 计费；耗时含网络波动。BFCL 抽样不访问搜索引擎；公共搜索可用性只在 Claude Code 的联网测试中单独体现。

学校接口未提供本项目可用的生成 seed / temperature 控制，固定题目和工具环境不能使模型输出完全确定。本次前后测试非交错运行，且部分时段同时运行 Claude Code 检查；延迟不是受控性能比较，不能据此声称模型变快。

## 调优前后对照

修改协议前保存代码快照；不复制 `.env`，旧版本仍由 benchmark 按请求传入当前 Token。

```bash
uv run --locked python tools/benchmark_tools.py --snapshot temp/benchmarks/before-change

# 完成修改后，对旧代码和当前代码使用相同题目与重复次数
uv run --locked python tools/benchmark_tools.py --backend temp/benchmarks/before-change --split all --output temp/before.json
uv run --locked python tools/benchmark_tools.py --split all --output temp/after.json

uv run --locked python tools/compare_tool_benchmarks.py --before temp/before.json --after temp/after.json --output temp/comparison
```

对比器拒绝不完整报告、重复计数、不同的模型/题号/重复次数集合，以及与当前数据文件不一致的指纹。开发集可迭代调参；候选代码冻结后再运行 holdout。若根据 holdout 继续修改，下一次验收应另取未使用题目，不能继续称原 holdout 为未见测试。

快照中的 `utility` 是指向当前项目的链接；本测试按请求提供 Token，不依赖该自动登录模块。快照冻结项目根目录的 Python 协议代码，不冻结 Python 解释器和依赖；完整报告记录解释器、主要依赖版本与源码指纹。需要比较不同依赖版本时应另用隔离环境。

## 本次实测

[同题对比报告](reports/tool-tuning.md) 和 [机器可读报告](reports/tool-tuning.json) 保留了开发集、holdout、纠正次数、延迟和全部剩余失败。原始运行记录在 `reports/runs/`，包括失败的原生历史实验；协议改动补丁在 `reports/baseline-to-tuned.patch`。

这些调优报告对应首次发布提交 `2fd5aad`，原始记录保留当时的源码指纹；后续修复不会改写历史测量。复原该版本或应用其协议补丁时应使用对应提交。新增的 `--case image` 和 [视觉效果验收](vision/README.md) 是实际识图的独立回归，不包含在历史报告的五类工作流中。

本次每模型每 split 18 题 × 2 次。开发集用于三次候选实验；最终协议冻结后才执行 holdout，未根据它继续修改协议。真实 Claude Code 五类任务两种模型均通过；这仍是小样本回归，不能保证任意任务都成功。重复运行共享题目，不是 36 道独立测试题；没有统计显著性结论。

若需要完整公开 benchmark，可按 [BFCL 官方安装与评分流程](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard#running-evaluations) 使用 `bfcl-eval`；本项目没有把小样本结果冒充完整 BFCL 成绩。[τ-bench](https://github.com/sierra-research/tau-bench) 则面向业务环境中的多轮用户交互，其原仓库提示转向新版任务；当前调优优先覆盖实际使用的编码工具流程。

## 数据来源说明

`bfcl_sample.json` 改编自 ShishirPatil/gorilla 的 BFCL 数据，使用 Apache-2.0 许可；保留来源版本与原文件散列。修改包括固定抽样、dev/holdout 标签，以及将 Python 风格类型名转换成 JSON Schema 类型。其余本地任务与评分器属于本项目。
