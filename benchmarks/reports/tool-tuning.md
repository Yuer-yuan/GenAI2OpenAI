# 工具调用调优实测

Small sampled regression benchmark, not an official BFCL leaderboard score. Dev data was used for tuning; holdout data was evaluated after freezing the candidate. Latency includes network variability.

分母为尝试次数，包含重复运行；题目、重复次数、版本指纹及原始输出保存在输入报告中。

## 未参与调参的测试

| 模型 | 类别 | 调优前 | 调优后 | 额外纠正请求 前→后 | 中位耗时秒 前→后 |
| --- | --- | --- | --- | --- | --- |
| deepseek | all | 26/36 | 32/36 | 10→8 | 0.46→0.349 |
| deepseek | continuation | 8/8 | 8/8 | 1→0 | 0.552→0.415 |
| deepseek | execution | 0/4 | 4/4 | 8→8 | 1.674→3.286 |
| deepseek | irrelevance | 4/6 | 4/6 | 1→0 | 1.38→0.571 |
| deepseek | multiple | 6/6 | 6/6 | 0→0 | 0.374→0.267 |
| deepseek | parallel | 3/6 | 4/6 | 0→0 | 0.416→0.364 |
| deepseek | simple_python | 5/6 | 6/6 | 0→0 | 0.335→0.269 |
| glm | all | 21/36 | 31/36 | 24→5 | 1.42→1.061 |
| glm | continuation | 6/8 | 8/8 | 5→0 | 1.848→1.182 |
| glm | execution | 0/4 | 4/4 | 7→3 | 8.262→5.294 |
| glm | irrelevance | 3/6 | 4/6 | 2→2 | 2.112→1.825 |
| glm | multiple | 6/6 | 6/6 | 2→0 | 0.616→0.488 |
| glm | parallel | 2/6 | 5/6 | 4→0 | 1.572→1.018 |
| glm | simple_python | 4/6 | 4/6 | 4→0 | 1.229→1.061 |

## 开发集

| 模型 | 类别 | 调优前 | 调优后 | 额外纠正请求 前→后 | 中位耗时秒 前→后 |
| --- | --- | --- | --- | --- | --- |
| deepseek | all | 33/36 | 35/36 | 8→7 | 0.373→0.374 |
| deepseek | continuation | 8/8 | 8/8 | 0→0 | 0.342→0.279 |
| deepseek | execution | 3/4 | 4/4 | 8→7 | 2.06→2.915 |
| deepseek | irrelevance | 4/6 | 5/6 | 0→0 | 0.905→0.574 |
| deepseek | multiple | 6/6 | 6/6 | 0→0 | 0.32→0.357 |
| deepseek | parallel | 6/6 | 6/6 | 0→0 | 0.306→0.405 |
| deepseek | simple_python | 6/6 | 6/6 | 0→0 | 0.357→0.305 |
| glm | all | 33/36 | 36/36 | 26→3 | 1.187→0.85 |
| glm | continuation | 8/8 | 8/8 | 2→0 | 0.914→0.699 |
| glm | execution | 2/4 | 4/4 | 12→1 | 7.818→3.688 |
| glm | irrelevance | 6/6 | 6/6 | 2→2 | 2.23→4.067 |
| glm | multiple | 5/6 | 6/6 | 4→0 | 1.005→0.913 |
| glm | parallel | 6/6 | 6/6 | 3→0 | 0.936→0.768 |
| glm | simple_python | 6/6 | 6/6 | 3→0 | 0.855→0.688 |

## 全部题目

| 模型 | 类别 | 调优前 | 调优后 | 额外纠正请求 前→后 | 中位耗时秒 前→后 |
| --- | --- | --- | --- | --- | --- |
| deepseek | all | 59/72 | 67/72 | 18→15 | 0.412→0.367 |
| deepseek | continuation | 16/16 | 16/16 | 1→0 | 0.389→0.281 |
| deepseek | execution | 3/8 | 8/8 | 16→15 | 2.06→3.271 |
| deepseek | irrelevance | 8/12 | 9/12 | 1→0 | 0.905→0.574 |
| deepseek | multiple | 12/12 | 12/12 | 0→0 | 0.324→0.307 |
| deepseek | parallel | 9/12 | 10/12 | 0→0 | 0.392→0.384 |
| deepseek | simple_python | 11/12 | 12/12 | 0→0 | 0.357→0.288 |
| glm | all | 54/72 | 67/72 | 50→8 | 1.252→0.867 |
| glm | continuation | 14/16 | 16/16 | 7→0 | 1.18→0.814 |
| glm | execution | 2/8 | 8/8 | 19→4 | 8.262→4.311 |
| glm | irrelevance | 9/12 | 10/12 | 4→4 | 2.23→2.941 |
| glm | multiple | 11/12 | 12/12 | 6→0 | 0.792→0.622 |
| glm | parallel | 8/12 | 11/12 | 7→0 | 1.245→0.812 |
| glm | simple_python | 10/12 | 10/12 | 7→0 | 1.041→0.822 |

## 剩余失败

完整调用参数和错误见同名 JSON 报告；没有删除失败题或在 holdout 结果上继续调参。

- deepseek / bfcl/irrelevance_183 / repeat=1 / irrelevant_call
- deepseek / bfcl/irrelevance_65 / repeat=0 / irrelevant_call
- glm / bfcl/simple_python_234 / repeat=1 / arguments_or_final_mismatch
- deepseek / bfcl/irrelevance_65 / repeat=1 / irrelevant_call
- glm / bfcl/irrelevance_65 / repeat=0 / irrelevant_call
- deepseek / bfcl/parallel_108 / repeat=1 / arguments_or_final_mismatch
- deepseek / bfcl/parallel_108 / repeat=0 / arguments_or_final_mismatch
- glm / bfcl/irrelevance_65 / repeat=1 / irrelevant_call
- glm / bfcl/simple_python_234 / repeat=0 / arguments_or_final_mismatch
- glm / bfcl/parallel_108 / repeat=0 / arguments_or_final_mismatch
