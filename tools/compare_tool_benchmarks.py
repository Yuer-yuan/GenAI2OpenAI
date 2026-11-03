"""Compare complete, matched tool-benchmark runs; never compare different tasks."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

if __package__:
    from .benchmark_tools import DATA, local_cases, summary
else:
    from benchmark_tools import DATA, local_cases, summary


def load_reports(paths):
    rows, metadata = {}, []
    known_cases = local_cases() + json.loads((DATA / "bfcl_sample.json").read_text())["cases"]
    for path in paths:
        report = json.loads(path.read_text())
        if not report.get("complete"):
            raise ValueError(f"Incomplete benchmark: {path}")
        cases = [case for case in known_cases
                 if (report["suite"] == "all" or case["suite"] == report["suite"])
                 and (report["split"] == "all" or case["split"] == report["split"])]
        fingerprint = hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()
        if report.get("dataset_sha256") != fingerprint:
            raise ValueError(f"Dataset fingerprint differs from the checked-in cases: {path}")
        models = {row["model"] for row in report["results"]}
        expected_keys = {(model, case["id"], repeat) for model in models for case in cases
                         for repeat in range(report["repeats"])}
        actual_keys = {(row["model"], row["id"], row["repeat"]) for row in report["results"]}
        if not models or actual_keys != expected_keys:
            raise ValueError(f"Incomplete model/case/repeat coverage: {path}")
        for row in report["results"]:
            key = (row["model"], row["id"], row["repeat"])
            if key in rows:
                raise ValueError(f"Duplicate model/case/repeat: {key}")
            rows[key] = row
        metadata.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "label": report["label"], "backend_sha256": report.get("backend_sha256")})
    return rows, metadata


def compare(before, after):
    if set(before) != set(after):
        raise ValueError("Before/after runs must cover exactly the same models, case IDs and repeats")
    tables = {}
    for split in ("all", "dev", "holdout"):
        left = summary([row for row in before.values() if split == "all" or row["split"] == split])
        right = {(row["model"], row["category"]): row for row in
                 summary([row for row in after.values() if split == "all" or row["split"] == split])}
        tables[split] = [{"model": row["model"], "category": row["category"], "before": row,
                          "after": right[(row["model"], row["category"])]} for row in left]
    changed = [{"model": key[0], "id": key[1], "repeat": key[2], "before": before[key]["passed"],
                "after": after[key]["passed"]} for key in sorted(before) if before[key]["passed"] != after[key]["passed"]]
    failures = [{key: row.get(key) for key in ("model", "id", "repeat", "split", "failure_type", "error", "calls", "final")}
                for row in after.values() if not row["passed"]]
    for failure in failures:
        if not failure["failure_type"]:
            failure["failure_type"] = "irrelevant_call" if "/irrelevance_" in failure["id"] and failure["calls"] else "unclassified_mismatch"
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "matched_attempts": len(before),
            "tables": tables, "changed_outcomes": changed, "remaining_failures": failures,
            "note": "Small sampled regression benchmark, not an official BFCL leaderboard score. Dev data was used for tuning; holdout data was evaluated after freezing the candidate. Latency includes network variability."}


def markdown(report):
    lines = ["# 工具调用调优实测", "", report["note"], "",
             "分母为尝试次数，包含重复运行；题目、重复次数、版本指纹及原始输出保存在输入报告中。", ""]
    for split, title in [("holdout", "未参与调参的测试"), ("dev", "开发集"), ("all", "全部题目")]:
        lines += [f"## {title}", "", "| 模型 | 类别 | 调优前 | 调优后 | 额外纠正请求 前→后 | 中位耗时秒 前→后 |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for row in report["tables"][split]:
            a, b = row["before"], row["after"]
            lines.append(f"| {row['model']} | {row['category']} | {a['passed']}/{a['total']} | {b['passed']}/{b['total']} | {a['repair_requests']}→{b['repair_requests']} | {a['median_seconds']}→{b['median_seconds']} |")
        lines.append("")
    lines += ["## 剩余失败", "", "完整调用参数和错误见同名 JSON 报告；没有删除失败题或在 holdout 结果上继续调参。", ""]
    for row in report["remaining_failures"]:
        lines.append(f"- {row['model']} / {row['id']} / repeat={row['repeat']} / {row['failure_type'] or row['error'] or 'strict argument mismatch'}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, nargs="+", required=True)
    parser.add_argument("--after", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True, help="Report path without .json/.md suffix")
    args = parser.parse_args()
    before, before_meta = load_reports(args.before)
    after, after_meta = load_reports(args.after)
    report = compare(before, after)
    report.update({"before_reports": before_meta, "after_reports": after_meta})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    for row in report["tables"]["holdout"]:
        if row["category"] == "all":
            print(f"{row['model']} holdout: {row['before']['passed']}/{row['before']['total']} -> {row['after']['passed']}/{row['after']['total']}")


if __name__ == "__main__":
    main()
