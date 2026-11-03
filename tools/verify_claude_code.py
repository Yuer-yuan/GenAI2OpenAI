"""Opt-in live coding check: Claude must create AND execute a quicksort program."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]


def verify(model, directory, timeout):
    if not shutil.which("claude"):
        raise RuntimeError("Claude Code is missing from PATH")
    parent = PROJECT / "temp"
    parent.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="claude-quicksort-", dir=parent))
    program = folder / "quicksort.py"
    prompt = (
        f"帮我写一个 quicksort 的 Python 程序并运行。只在 {folder} 中创建 quicksort.py，"
        "定义 quicksort(values) 函数。用 python3 实际运行，检查空列表、重复元素、负数和随机输入，"
        "成功时只打印 QUICKSORT_OK。请实际完成，不要只说明计划。"
    )
    argv = ["claude", "-p", "--model", model, "--no-session-persistence",
            "--permission-mode", "bypassPermissions",
            "--setting-sources", "project,local", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--disallowedTools", "Agent",
            "--max-turns", "12", "--output-format", "stream-json", "--verbose", prompt]
    started = time.monotonic()
    completed = subprocess.run(argv, cwd=directory, capture_output=True, text=True, timeout=timeout)
    tool_names = {}
    executed = False
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
                tool_names[block["id"]] = block.get("name")
            if (block.get("type") == "tool_result" and not block.get("is_error")
                    and tool_names.get(block.get("tool_use_id")) == "Bash"
                    and "QUICKSORT_OK" in str(block.get("content", ""))):
                executed = True
    summary = {"model": model, "exit_code": completed.returncode, "file": str(program),
               "file_created": program.exists(), "claude_executed_program": executed,
               "tools_called": list(tool_names.values()), "turns": final.get("num_turns"),
               "result": final.get("result"), "seconds": round(time.monotonic() - started, 2)}
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if completed.returncode or not program.exists() or not executed:
        raise RuntimeError("Live check failed: a text promise or a generated file alone is not a completed coding task")
    check = (
        "import contextlib,io,random,runpy,sys; "
        "ns=runpy.run_path(sys.argv[1],run_name='verification'); f=ns['quicksort']; "
        "rng=random.Random(4827); cases=[[],[1],[3,3,1],[-2,0,-5,2]]+"
        "[[rng.randrange(-100,101) for _ in range(rng.randrange(100))] for _ in range(100)]; "
        "assert all(f(values.copy())==sorted(values) for values in cases); print('104 cases passed')"
    )
    checked = subprocess.run([sys.executable, "-c", check, str(program)], capture_output=True, text=True, timeout=20)
    if checked.returncode:
        raise RuntimeError(checked.stderr[-1500:])
    print("PASS: Claude wrote and ran the program; independent sorting checks passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["glm", "deepseek"], default="deepseek")
    parser.add_argument("--directory", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    try:
        verify(args.model, args.directory.resolve(), args.timeout)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc)) from None
