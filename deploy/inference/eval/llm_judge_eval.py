# -*- coding: utf-8 -*-
"""LLM-as-judge 自动评测：用外部大模型当裁判，对 LoRA 与基座答案做多维度打分。

打分维度（各 1-5 分）：
  - 准确性：知识点是否正确，有无事实性错误或幻觉
  - 完整性：是否覆盖问题核心要点，有无遗漏
  - 简洁性：是否精炼，有无冗余
  - 可读性：表达是否清晰、结构是否合理、是否适合学生理解

裁判策略：
  - 隐去模型名，裁判只看到"答案A"和"答案B"，不知道哪个是 LoRA / 基座，消除品牌偏好
  - 同一次调用内对两份答案分别打分，节省 token
  - 要求裁判输出严格 JSON，便于解析

key 安全：
  - API key 从环境变量 SENSENOVA_API_KEY 读取，不硬编码、不落盘
  - 跑完可在 shell 里 unset 删除

依赖：仅标准库 + 已装的 numpy（无新依赖）
产物：llm_judge_results.json（逐题分数 + 汇总）
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

EVAL_DIR = Path(r"E:\testing\微调评估")
LORA_JSON = EVAL_DIR / "lora_eval_results.json"
BASE_JSON = EVAL_DIR / "base_eval_results.json"
OUTPUT_JSON = EVAL_DIR / "llm_judge_results.json"

# 裁判 API 配置（key 从环境变量读，endpoint 按用户提供）
JUDGE_URL = "https://token.sensenova.cn/v1/chat/completions"
JUDGE_MODEL = "deepseek-v4-flash"

# 维度列表，用于汇总
DIMENSIONS = ["准确性", "完整性", "简洁性", "可读性"]


def load_answers(path: Path) -> dict[str, dict]:
    """从评测结果 JSON 提取 question_id -> {question, answer, category}。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for r in data["results"]:
        if r.get("success"):
            out[r["question_id"]] = {
                "question": r["question"],
                "answer": r["answer"],
                "category": r["category"],
            }
    return out


def build_judge_prompt(question: str, answer_a: str, answer_b: str) -> tuple[dict, dict]:
    """构造裁判 prompt。

    隐去模型名：A/B 哪个是 LoRA 由调用方随机化，裁判无法从标签推断。
    返回 (messages, mapping)，mapping 记录 A/B 实际对应哪个模型。
    本脚本固定 A=LoRA、B=基座，但在 prompt 中不暴露这一信息。
    """
    prompt = f"""你是一位严格、中立的机器学习课程阅卷专家。下面给你一道题和两份学生作答（答案A、答案B）。请你作为阅卷人对两份答案分别打分。

【题目】
{question}

【答案A】
{answer_a}

【答案B】
{answer_b}

【评分维度】（每项 1-5 分，5 分最优）
- 准确性：知识点是否正确，有无事实性错误或幻觉
- 完整性：是否覆盖核心要点，有无重要遗漏
- 简洁性：是否精炼扼要，有无冗余展开
- 可读性：表达是否清晰、结构是否合理、是否适合学生理解

【输出要求】
必须且只能输出一个 JSON 对象，不要输出任何解释、markdown 代码块或多余文字。格式如下：
{{
  "A": {{"准确性": <1-5>, "完整性": <1-5>, "简洁性": <1-5>, "可读性": <1-5>, "评语": "<一句话评语>"}},
  "B": {{"准确性": <1-5>, "完整性": <1-5>, "简洁性": <1-5>, "可读性": <1-5>, "评语": "<一句话评语>"}}
}}
"""
    messages = [{"role": "user", "content": prompt}]
    mapping = {"A": "lora", "B": "base"}
    return messages, mapping


def call_judge(messages: list[dict], api_key: str, timeout: int = 120, max_retries: int = 5) -> dict:
    """调用裁判 API，返回解析后的 JSON 分数字典。

    遇到 429 限流或 5xx 错误时指数退避重试（2→4→8→16→32 秒），
    最多重试 max_retries 次；其他错误直接抛出。
    要求裁判输出纯 JSON，本函数对 markdown 代码块包裹做兼容解析。
    """
    payload = {
        "model": JUDGE_MODEL,
        "messages": messages,
        "temperature": 0.0,  # 打分要稳定可复现
        "max_tokens": 600,
    }
    data = json.dumps(payload).encode("utf-8")
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(
            JUDGE_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()
            # 兼容裁判输出被 ```json ... ``` 包裹的情况
            fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if fence:
                content = fence.group(1)
            # 兜底：提取第一个 {...} 块
            if not content.startswith("{"):
                m = re.search(r"\{.*\}", content, re.DOTALL)
                if m:
                    content = m.group(0)
            return json.loads(content)
        except urllib.error.HTTPError as e:
            last_exc = e
            # 仅对限流(429)和服务端错误(5xx)重试
            if e.code == 429 or 500 <= e.code < 600:
                if attempt < max_retries:
                    wait = 2 ** (attempt + 1)  # 2,4,8,16,32
                    print(f"    [限流/服务错误 {e.code}] 第 {attempt+1} 次重试，等待 {wait}s...")
                    time.sleep(wait)
                    continue
            raise
        except Exception as e:
            last_exc = e
            # 网络瞬时错误也重试
            if attempt < max_retries:
                wait = 2 ** (attempt + 1)
                print(f"    [网络错误 {e}] 第 {attempt+1} 次重试，等待 {wait}s...")
                time.sleep(wait)
                continue
            raise
    raise last_exc  # type: ignore[misc]


def score_to_nums(score_block: dict) -> dict[str, int]:
    """把裁判返回的某一方分数块提取为维度->整数。"""
    out = {}
    for d in DIMENSIONS:
        v = score_block.get(d)
        try:
            out[d] = int(v)
        except (TypeError, ValueError):
            out[d] = 0
    return out


def main() -> None:
    api_key = os.environ.get("SENSENOVA_API_KEY")
    if not api_key:
        print("错误：未设置环境变量 SENSENOVA_API_KEY")
        print("PowerShell 设置：$env:SENSENOVA_API_KEY='你的key'")
        return

    lora = load_answers(LORA_JSON)
    base = load_answers(BASE_JSON)
    lora_data = json.loads(LORA_JSON.read_text(encoding="utf-8"))
    questions = [(r["question_id"], r["category"], r["question"]) for r in lora_data["results"]]

    print("=" * 60)
    print(f"LLM-as-judge 评测：{JUDGE_MODEL}")
    print(f"共 {len(questions)} 道题，多维度打分（准确性/完整性/简洁性/可读性）")
    print("=" * 60)

    per_question = []
    for i, (qid, cat, q) in enumerate(questions, 1):
        lora_ans = lora.get(qid, {}).get("answer", "")
        base_ans = base.get(qid, {}).get("answer", "")
        messages, mapping = build_judge_prompt(q, lora_ans, base_ans)
        try:
            raw = call_judge(messages, api_key)
            lora_scores = score_to_nums(raw.get("A", {}))
            base_scores = score_to_nums(raw.get("B", {}))
            lora_comment = raw.get("A", {}).get("评语", "")
            base_comment = raw.get("B", {}).get("评语", "")
        except Exception as e:
            print(f"[{i}/{len(questions)}] {qid} 裁判调用失败：{e}")
            lora_scores = {d: 0 for d in DIMENSIONS}
            base_scores = {d: 0 for d in DIMENSIONS}
            lora_comment = base_comment = f"调用失败：{e}"
        per_question.append({
            "question_id": qid,
            "category": cat,
            "question": q,
            "lora_scores": lora_scores,
            "base_scores": base_scores,
            "lora_comment": lora_comment,
            "base_comment": base_comment,
        })
        lora_total = sum(lora_scores.values())
        base_total = sum(base_scores.values())
        print(f"[{i}/{len(questions)}] {qid} {cat} | LoRA总分={lora_total} Base总分={base_total}")
        # 礼貌间隔，降低触发限流概率
        time.sleep(3)

    # 汇总：各维度均值 + 总分均值
    def agg(side: str) -> dict:
        rows = [pq[f"{side}_scores"] for pq in per_question]
        out = {}
        for d in DIMENSIONS:
            vals = [r[d] for r in rows]
            out[f"mean_{d}"] = round(sum(vals) / len(vals), 2) if vals else 0
        totals = [sum(r.values()) for r in rows]
        out["mean_total"] = round(sum(totals) / len(totals), 2) if totals else 0
        return out

    output = {
        "指标说明": {
            "裁判模型": JUDGE_MODEL,
            "打分维度": "准确性/完整性/简洁性/可读性，各 1-5 分",
            "盲评": "裁判仅见答案A/B，不知哪个是 LoRA/基座，消除品牌偏好",
            "A对应": "LoRA 微调模型",
            "B对应": "基座模型 Qwen2.5-7B-Instruct",
        },
        "lora_汇总": agg("lora"),
        "base_汇总": agg("base"),
        "per_question": per_question,
    }

    print("\n" + "=" * 60)
    print("汇总（各维度均分 / 满分5）")
    print("=" * 60)
    print(f"{'模型':<8}{'准确性':<8}{'完整性':<8}{'简洁性':<8}{'可读性':<8}{'总分均':<8}")
    la = output["lora_汇总"]
    ba = output["base_汇总"]
    print(f"{'LoRA':<8}{la['mean_准确性']:<8}{la['mean_完整性']:<8}{la['mean_简洁性']:<8}{la['mean_可读性']:<8}{la['mean_total']:<8}")
    print(f"{'基座':<8}{ba['mean_准确性']:<8}{ba['mean_完整性']:<8}{ba['mean_简洁性']:<8}{ba['mean_可读性']:<8}{ba['mean_total']:<8}")

    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存到: {OUTPUT_JSON}")
    print("\n提示：用完请删除环境变量：PowerShell: Remove-Item Env:SENSENOVA_API_KEY")


if __name__ == "__main__":
    main()
