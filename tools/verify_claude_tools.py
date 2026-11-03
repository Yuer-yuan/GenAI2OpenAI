"""Live Claude Code checks for public networking, file tools and task tracking."""

import argparse
import concurrent.futures
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]


def test_case(name, directory, timeout, model="deepseek"):
    parent = PROJECT / "temp"
    parent.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f"claude-{name}-", dir=parent))
    if name == "webfetch":
        tools = ["WebFetch"]
        prompt = "实际调用 WebFetch 打开 https://example.com，返回页面的 h1 主标题；不要凭记忆回答。"
        marker = "Example Domain"
    elif name == "websearch":
        tools = ["WebSearch"]
        prompt = "实际调用 WebSearch 搜索 Python official documentation，返回实际结果中的官方文档标题与链接；不要凭记忆回答。"
        marker = "python.org"
    elif name == "files":
        tools = ["Glob", "Grep", "Read", "Edit", "Write", "Bash"]
        (folder / "a_marker.txt").write_text("phase=before\nGENAI_TOOL_4827\n")
        (folder / "b_other.txt").write_text("unrelated\n")
        prompt = (
            f"只操作 {folder}。必须实际依次使用六种工具完成验证："
            "1.Glob 查找 *.txt；2.Grep 找到 GENAI_TOOL_4827；3.Read 读取匹配文件；"
            "4.Edit 将 phase=before 改成 phase=after；5.Write 新建 result.txt，写入 GENAI_TOOL_4827；"
            "6.Bash 使用 python3 断言 a_marker.txt 包含 phase=after 且 result.txt 包含 GENAI_TOOL_4827，"
            "检查通过打印 TOOL_CHAIN_OK。每一步使用指定的工具，不要用 Bash 替代其他工具。"
        )
        marker = "TOOL_CHAIN_OK"
    elif name == "workflow":
        tools = ["WebSearch", "WebFetch", "Read", "Write", "Edit", "Bash", "Glob", "Grep"]
        prompt = (
            "search the web and find the quickest sort algorithm, then write and run it\n"
            f"Work only in {folder}. Use Python 3, save a runnable comparison as benchmark.py, "
            "compare a sorting implementation against sorted() on defined inputs, assert correctness, "
            "and print SORT_BENCH_OK after successful checks. Cite actual search sources and report measured times."
        )
        marker = "SORT_BENCH_OK"
    else:
        tools = ["TaskCreate", "TaskUpdate", "TaskList"]
        prompt = (
            "实际调用 TaskCreate 新建一个标题为 GENAI_TASK_4827 的测试任务，"
            "接着调用 TaskUpdate 将刚创建任务的状态设为 completed，最后调用 TaskList 检查状态。不要修改项目文件。"
        )
        marker = "GENAI_TASK_4827"
    argv = [str(PROJECT / "claude.command"), "--directory", str(directory), "--model", model, "--",
            "-p", "--no-session-persistence", "--setting-sources", "project,local", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--tools", ",".join(tools), "--max-turns", "18",
            "--output-format", "stream-json", "--verbose", prompt]
    started = time.monotonic()
    completed = subprocess.run(argv, cwd=directory, capture_output=True, text=True, timeout=timeout)
    (folder / "events.jsonl").write_text(completed.stdout)
    (folder / "stderr.txt").write_text(completed.stderr)
    calls = {}
    details = []
    results = []
    final = {}
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            final = event
        message = event.get("message", {})
        blocks = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                calls[block["id"]] = block.get("name")
                details.append(block)
            elif block.get("type") == "tool_result":
                results.append({"tool": calls.get(block.get("tool_use_id")), "error": bool(block.get("is_error")),
                                "content": str(block.get("content", ""))})
    successful = {result["tool"] for result in results if not result["error"]}
    required = {"WebSearch", "Write", "Bash"} if name == "workflow" else set(tools)
    passed = completed.returncode == 0 and not final.get("is_error", True) and required.issubset(successful)
    if name in {"webfetch", "websearch", "files", "workflow"}:
        expected_tool = "Bash" if name in {"files", "workflow"} else tools[0]
        passed = passed and any(result["tool"] == expected_tool and not result["error"] and marker in result["content"] for result in results)
    if name == "files":
        passed = passed and "phase=after" in (folder / "a_marker.txt").read_text()
        passed = passed and (folder / "result.txt").exists() and "GENAI_TOOL_4827" in (folder / "result.txt").read_text()
    if name == "tasks":
        passed = passed and any(b.get("name") == "TaskCreate" and marker in b.get("input", {}).get("subject", "") for b in details)
        passed = passed and any(b.get("name") == "TaskUpdate" and b.get("input", {}).get("status") == "completed" for b in details)
        passed = passed and any(r["tool"] == "TaskList" and not r["error"]
                                and marker in r["content"] and "completed" in r["content"] for r in results)
    if name == "workflow":
        passed = passed and any(r["tool"] == "WebSearch" and not r["error"]
                                and re.search(r"https?://", r["content"])
                                and re.search(r"sort|algorithm", r["content"], re.I) for r in results)
        program = folder / "benchmark.py"
        passed = passed and program.exists()
        if program.exists():
            checked = subprocess.run([sys.executable, str(program)], cwd=folder, capture_output=True, text=True, timeout=45)
            passed = passed and checked.returncode == 0 and marker in checked.stdout
    return {"case": name, "model": model, "passed": passed, "tools_called": list(calls.values()),
            "errors": [{"tool": r["tool"], "message": r["content"][:500]} for r in results if r["error"]],
            "answer": final.get("result", completed.stderr[-500:]),
            "seconds": round(time.monotonic() - started, 2), "artifacts": str(folder)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path.cwd())
    parser.add_argument("--model", choices=["deepseek", "glm"], default="deepseek")
    parser.add_argument("--case", choices=["all", "webfetch", "websearch", "files", "tasks", "workflow"], default="all")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--report", type=Path, help="Write all case results as a JSON array")
    args = parser.parse_args()
    cases = ["webfetch", "websearch", "files", "tasks", "workflow"] if args.case == "all" else [args.case]
    passed = True
    reports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(test_case, case, args.directory.resolve(), args.timeout, args.model): case for case in cases}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
                result = {"case": futures[future], "model": args.model, "passed": False, "error": str(exc)}
            reports.append(result)
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            passed = passed and result["passed"]
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    raise SystemExit(0 if passed else 1)
