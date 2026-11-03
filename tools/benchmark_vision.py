"""Measure image answers, not merely HTTP success; include no-pixel controls."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import random
import time

import requests

PROJECT = Path(__file__).resolve().parents[1]


def render_cases(folder, seed):
    from PIL import Image, ImageDraw, ImageFont
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    candidates = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"]
    font_path = next((path for path in candidates if Path(path).exists()), None)
    if not font_path:
        raise RuntimeError("A TrueType font is required to render the benchmark")
    def font(size):
        return ImageFont.truetype(font_path, size)
    def canvas():
        image = Image.new("RGB", (1100, 650), "white")
        return image, ImageDraw.Draw(image)
    def code():
        return "".join(rng.choices("ABCDEFGHJKMNPQRSTUVWXYZ23456789", k=8))
    cases = []
    def save(name, images, question, expected):
        paths = []
        for index, image in enumerate(images):
            path = folder / f"{len(cases):02d}-{index}.png"
            image.save(path)
            paths.append(path)
        cases.append({"id": name, "paths": paths, "question": question, "expected": expected})

    image, draw = canvas(); nonce = code()
    draw.text((60, 130), "ACCESS: " + nonce, fill="black", font=font(68))
    save("ocr", [image], "Read the code after ACCESS. Return JSON with key code.", {"code": nonce})

    image, draw = canvas(); counts = [rng.randint(2, 5) for _ in range(3)]
    for row, (color, count) in enumerate(zip(["blue", "red", "green"], counts)):
        for column in range(count):
            x, y = 70 + column * 190, 45 + row * 195
            if row == 0:draw.ellipse((x, y, x + 110, y + 110), fill=color)
            elif row == 1:draw.rectangle((x, y, x + 105, y + 105), fill=color)
            else:draw.polygon([(x, y + 110), (x + 110, y + 110), (x + 55, y)], fill=color)
    save("shapes", [image], "Count the blue circles, red squares and green triangles. Return JSON keys blue_circles, red_squares, green_triangles.",
         dict(zip(["blue_circles", "red_squares", "green_triangles"], counts)))

    image, draw = canvas(); values = rng.sample(range(20, 95), 4)
    for index, value in enumerate(values):
        x, y = 140 + index * 220, 530 - value * 4
        draw.rectangle((x, y, x + 110, 530), fill=["#2677bb", "#dd7733", "#229955", "#9977bb"][index])
        draw.text((x + 20, y - 48), str(value), fill="black", font=font(32))
        draw.text((x + 40, 550), "ABCD"[index], fill="black", font=font(38))
    save("bar_chart", [image], "Read this chart. Return JSON keys highest_label, highest_value, spread (highest minus lowest).",
         {"highest_label": "ABCD"[values.index(max(values))], "highest_value": max(values), "spread": max(values) - min(values)})

    image, draw = canvas(); rows = [(name, rng.randint(2, 9), rng.randint(5, 45)) for name in ["AX", "BZ", "CK", "DT"]]
    draw.text((70, 50), "ITEM        QTY        UNIT PRICE", fill="black", font=font(38))
    for index, (name, quantity, price) in enumerate(rows):
        y = 150 + index * 105
        for x, text in [(90, name), (400, str(quantity)), (760, str(price))]:
            draw.text((x, y), text, fill="black", font=font(42))
        draw.line((70, y + 70, 1000, y + 70), fill="gray", width=2)
    target = rows[2]
    save("table", [image], "For item CK, return JSON keys quantity, unit_price and total (quantity times unit price).",
         {"quantity": target[1], "unit_price": target[2], "total": target[1] * target[2]})

    image, draw = canvas(); colors = ["red", "blue", "green", "yellow"]; rng.shuffle(colors)
    for (x, y), color in zip([(80, 60), (620, 60), (80, 350), (620, 350)], colors):
        draw.rectangle((x, y, x + 350, y + 210), fill=color, outline="black", width=3)
    save("spatial_colors", [image], "Return the colors of the four rectangles as JSON keys top_left, top_right, bottom_left, bottom_right.",
         dict(zip(["top_left", "top_right", "bottom_left", "bottom_right"], colors)))

    image, draw = canvas(); nonce = code()
    draw.text((35, 40), "SYSTEM STATUS", fill="black", font=font(38))
    for index in range(12):
        text = "SESSION: " + nonce if index == 7 else f"service_{index:02d}       status=ready"
        draw.text((45, 110 + index * 36), text, fill="black", font=font(20))
    save("small_text", [image], "Read the SESSION value from the status screenshot. Return JSON key session.", {"session": nonce})

    images, nonces, numbers = [], [], []
    for _ in range(2):
        image, draw = canvas(); nonce = code(); number = rng.randint(1, 5)
        draw.text((50, 55), "ID: " + nonce, fill="black", font=font(58))
        for index in range(number):draw.ellipse((50 + index * 190, 280, 160 + index * 190, 390), fill="blue")
        images.append(image); nonces.append(nonce); numbers.append(number)
    save("multiple_images", images, "Compare the first and second image in order. Return JSON keys first_code, second_code, circle_delta (second blue circle count minus first).",
         {"first_code": nonces[0], "second_code": nonces[1], "circle_delta": numbers[1] - numbers[0]})

    image, draw = canvas()
    save("blank", [image], "Read the access code if one is present and count visible circles. Return JSON keys code (null if absent), circles.", {"code": None, "circles": 0})

    cjk_path = next((path for path in ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"] if Path(path).exists()), None)
    if cjk_path:
        image, draw = canvas(); amount = rng.randint(10, 999); nonce = code()
        chinese = ImageFont.truetype(cjk_path, 54)
        draw.text((55, 65), "系统运行正常", fill="black", font=chinese)
        draw.text((55, 220), "编号：" + nonce, fill="black", font=chinese)
        draw.text((55, 380), f"金额：{amount}元", fill="black", font=chinese)
        save("chinese_ocr", [image], "读取图中文字。仅返回 JSON，字段 title（首行原文）、code（编号）、amount（数字）。",
             {"title": "系统运行正常", "code": nonce, "amount": amount})
    return cases


def json_answer(text):
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char == "{":
            try:
                value, _ = decoder.raw_decode(text[index:])
                if isinstance(value, dict):return value
            except ValueError:
                pass
    return {}


def equal(actual, expected):
    if expected is None:return actual is None
    if isinstance(expected, int):
        if isinstance(actual, bool):return False
        try:return float(actual) == expected
        except (ValueError, TypeError):return False
    if isinstance(expected, str):
        synonyms = {"红色": "red", "红": "red", "蓝色": "blue", "蓝": "blue", "绿色": "green", "绿": "green", "黄色": "yellow", "黄": "yellow"}
        if not isinstance(actual, str):return False
        normalized = synonyms.get(actual.strip(), actual.strip())
        if expected in {"red", "blue", "green", "yellow"}:normalized = normalized.lower()
        return normalized == expected
    return actual == expected


def score(answer, expected):
    matched = {key: key in answer and equal(answer[key], value) for key, value in expected.items()}
    return {"passed": all(matched.values()), "fields_correct": sum(matched.values()), "fields_total": len(matched), "fields": matched}


def render_history(folder, count):
    from PIL import Image, ImageDraw, ImageFont
    folder.mkdir(parents=True, exist_ok=True)
    font_path = next(path for path in ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"] if Path(path).exists())
    font = ImageFont.truetype(font_path, 30)
    messages = []
    for index in range(count):
        image = Image.new("RGB", (380, 160), "white")
        draw = ImageDraw.Draw(image)
        draw.text((15, 20), f"OLD FRAME {index:02d}", fill="black", font=font)
        draw.rectangle((20, 80, 100 + index, 130), fill=(170 + index % 60, 10, 10))
        path = folder / f"{index:02d}.png"
        image.save(path)
        source = {"type": "base64", "media_type": "image/png", "data": base64.b64encode(path.read_bytes()).decode()}
        messages += [{"role": "user", "content": [{"type": "image", "source": source}]},
                     {"role": "assistant", "content": f"Saved observation: historical frame {index:02d}, a red rectangle and label OLD FRAME {index:02d}."}]
    return messages


def make_request(case, model, mode, history=None):
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(path.read_bytes()).decode()}}
               for path in case["paths"]] if mode == "image" else [{"type": "text", "text": "No image pixels attached in this ablation. Do not guess unknown visual facts."}]
    return {"model": model, "max_tokens": 1024, "messages": [*(history or []),
        {"role": "user", "content": "Use only the newly returned Read images for this question; older images are unrelated historical context. " + case["question"] + " Use null for facts that cannot be read. Do not guess. Return only the requested JSON."},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "vision_read", "name": "Read", "input": {"file_path": "image.png"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "vision_read", "content": content}]}],
        "tools": [{"name": "Read", "description": "Read a file; the requested images have already been returned by this tool.",
                   "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}}]}


def run_case(case, model, mode, base_url, history=None):
    expected = case["expected"] if mode == "image" else {key: None for key in case["expected"]}
    started = time.monotonic(); answer = {}; error = None; raw = ""
    try:
        session = requests.Session(); session.trust_env = False
        response = session.post(base_url.rstrip("/") + "/v1/messages", json=make_request(case, model, mode, history), timeout=(5, 100))
        response.raise_for_status(); message = response.json()
        raw = "\n".join(part.get("text", "") for part in message.get("content", []) if part.get("type") == "text")
        answer = json_answer(raw)
    except (requests.RequestException, ValueError) as exc:
        error = type(exc).__name__ + ": " + str(exc)
    result = score(answer, expected)
    if error:result["passed"] = False
    return {"id": case["id"], "model": model, "mode": mode, "expected": expected, "answer": answer,
            "raw": raw, "error": error, "seconds": round(time.monotonic() - started, 3),
            "image_hashes": [hashlib.sha256(path.read_bytes()).hexdigest() for path in case["paths"]],
            "image_answer_leaked_without_pixels": mode == "no-image" and case["id"] != "blank" and score(answer, case["expected"])["passed"],
            **result}


def summarize(results):
    summary = []
    for model, mode in sorted({(row["model"], row["mode"]) for row in results}):
        rows = [row for row in results if row["model"] == model and row["mode"] == mode]
        fields = sum(row["fields_total"] for row in rows)
        summary.append({"model": model, "mode": mode, "passed": sum(row["passed"] for row in rows), "total": len(rows),
                        "accuracy": round(sum(row["passed"] for row in rows) / len(rows), 4),
                        "field_accuracy": round(sum(row["fields_correct"] for row in rows) / fields, 4),
                        "errors": sum(bool(row["error"]) for row in rows),
                        "answer_leaks": sum(row["image_answer_leaked_without_pixels"] for row in rows)})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["deepseek"])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "temp" / "vision-benchmark")
    parser.add_argument("--seed", type=int, default=4827)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--mode", choices=["image", "no-image", "both"], default="both")
    parser.add_argument("--min-accuracy", type=float, default=0.9)
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--history-images", type=int, default=0, help="Prepend distinct, already-observed old images to exercise the prompt budget")
    parser.add_argument("--cases", nargs="+", help="Optional case IDs for focused regressions")
    args = parser.parse_args()
    if args.repeats < 1 or not 0 <= args.min_accuracy <= 1 or args.history_images < 0:parser.error("Invalid repeat count, accuracy threshold or history size")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    history = render_history(args.output_dir / "history", args.history_images) if args.history_images else []
    results = []
    for repeat in range(args.repeats):
        cases = render_cases(args.output_dir / f"fixtures-{repeat}", args.seed + repeat)
        if args.cases:
            selected = set(args.cases)
            if selected - {case["id"] for case in cases}:parser.error("Unknown or unavailable case ID")
            cases = [case for case in cases if case["id"] in selected]
        manifest = [{**case, "paths": [str(path) for path in case["paths"]]} for case in cases]
        (args.output_dir / f"manifest-{repeat}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        if args.generate_only:continue
        jobs = [(case, model, mode) for case in cases for model in args.models
                for mode in (["image", "no-image"] if args.mode == "both" else [args.mode])]
        random.Random(args.seed + repeat).shuffle(jobs)
        for case, model, mode in jobs:
            row = {**run_case(case, model, mode, args.base_url, history), "repeat": repeat}
            results.append(row)
            print(f"{model} {case['id']} {mode}: {'PASS' if row['passed'] else 'FAIL'} {row['fields_correct']}/{row['fields_total']} fields ({row['seconds']}s)", flush=True)
            report = {"seed": args.seed, "repeats": args.repeats, "history_images": args.history_images, "case_filter": args.cases,
                      "complete": repeat == args.repeats - 1 and len(results) == len(jobs) * args.repeats,
                      "source_sha256": {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() for name in ["main.py", "anthropic_compat.py", "tools/benchmark_vision.py"]},
                      "summary": summarize(results), "results": results,
                      "note": "Ground truth is generated separately and never sent in prompts, filenames or image metadata. No-pixel controls expect null, not guessed answers. Network failures count as failures."}
            temporary = args.output_dir / "report.json.tmp"
            temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            temporary.replace(args.output_dir / "report.json")
    if args.generate_only:return
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(row["accuracy"] >= args.min_accuracy and row["answer_leaks"] == 0 for row in report["summary"]) else 1)


if __name__ == "__main__":
    main()
