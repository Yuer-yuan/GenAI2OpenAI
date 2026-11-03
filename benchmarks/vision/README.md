# DeepSeek 真实识图验收

本次直接使用学校 `deepseek-pro`（平台显示 DeepSeek-V4.1-Flash），没有 GPT、辅助识图模型或 OCR 代答。修复后图片作为多模态 `content` 发送；标准答案未放入请求提示词、文件名或 PNG 元数据。

本目录保留提交 `01321fb` 的首次视觉验收记录。后续新增的整段历史图片预算及当前源码验收见 [图片预算回归](../image-budget/README.md)，历史报告不改写。

| 检查 | 结果 |
| --- | --- |
| 有图任务，9 类 × 2 组不同随机内容 | 18/18 通过，46/46 字段正确 |
| 去掉图片的对照，要求未知事实返回 null | 18/18 通过，没有猜出图片答案 |
| HTTP / 模型请求错误 | 0 |
| 真实 Claude Code：Read → Write → Bash | 通过；识别代码、图形和颜色，写 JSON 并运行读取 |
| 离线回归 | 68 项通过 |

这是一套小样本合成图回归，不是通用视觉排行榜，也不能保证任意复杂照片都正确。它验证了真实像素可达模型、基本视觉任务有效，以及结果能进入后续编码工具流程；仅返回 200 或说明“无法识图”不算通过。

## 看测试图与逐项答案

- [完整原始回答、耗时、判分与源码指纹](report.json)
- [第一组图片、问题与标准答案](manifest-0.json)
- [第二组图片、问题与标准答案](manifest-1.json)
- [真实 Claude Code 工作流记录](claude-read-write-run.json)

测试类型包括：随机访问码、中英文 OCR、纯图形计数、柱状图最大值和差值、表格读数与计算、四象限颜色、20px 小字截图、多图顺序和计数差、空白图。每一组使用不同随机内容；问题只说明需要回答哪些字段，不提供答案。

## 复跑

先启动本地 API 服务。在项目上一层执行：

```bash
./GenAI2OpenAI/vision-benchmark.command --seed 93841 --repeats 2
```

或在项目目录执行：

```bash
uv run --locked --group vision python tools/benchmark_vision.py --models deepseek --seed 93841 --repeats 2
uv run --locked python tools/verify_claude_tools.py --model deepseek --case image
```

Pillow 仅用于生成测试图，放在可选 `vision` 依赖组，生产图文转发不依赖它。默认门槛为整题正确率至少 90%，错误、拒绝识图和漏字段都不会冒充成功；无像素对照也要正确承认未知。CLI 非零退出表示未达到门槛。输出默认在忽略提交的 `temp/vision-benchmark/`。

验收 seed 为 93841 和 93842，与最初检查图片渲染使用的 seed 4827 不同。模型生成本身不能固定，复跑成绩可能波动；网络错误也计入失败。

## 传输方式

DeepSeek 原生输入及工具图片都保留为图文内容，不经过旧的单图上传字段，因此不需要额外的图片上传 Token。工具结果的图片放在 `user` 消息里，调用 ID、工具名、文字结果仍保留，base64 不会进入普通文本提示词。多图不会被悄悄丢弃。

`GENAI_IMAGE_TRANSPORT=auto` 对非 GPT 使用原生图文；GPT 保留旧上传兼容路径。此处验证的是学校 DeepSeek 通道；其他模型是否具备视觉能力需要单独测量，不能以格式放行或文字工具测试代替。

参考：[DeepSeek 官方视觉输入说明](https://api-docs.deepseek.com/guides/vision/)。
