# -*- coding: utf-8 -*-
"""自动指标评测脚本：对 LoRA 微调模型 vs 基座模型的 17 道题答案计算自动评分。

指标：
  - BLEU-4：字面 n-gram 精度（中文字符级分词），衡量与参考答案的表面重合度
  - ROUGE-L：基于最长公共子序列的召回型指标，衡量关键内容覆盖
  - TF-IDF 余弦相似度：基于词频-逆文档频率向量余弦，衡量词汇分布与关键词覆盖接近度

参考答案策略：
  以基座模型答案作为 LoRA 的参考、以 LoRA 答案作为基座的参考，双向各评一遍，
  避免单方面偏向任一模型。两个模型的答案已存于 lora_eval_results.json / base_eval_results.json。

依赖：仅使用已安装的 sklearn、numpy，无需联网下载、无外部模型。
产物：metrics_results.json（所有逐题分数 + 汇总统计）。
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Sequence

# ===== 路径与常量 =====
EVAL_DIR = Path(r"E:\testing\微调评估")
LORA_JSON = EVAL_DIR / "lora_eval_results.json"
BASE_JSON = EVAL_DIR / "base_eval_results.json"
OUTPUT_JSON = EVAL_DIR / "metrics_results.json"

# 用于 BLEU 的 n-gram 最大阶数
BLEU_MAX_N = 4


# ===== 文本预处理与分词 =====
def tokenize_zh(text: str) -> list[str]:
    """中文按字符切分（去除空白），适配无分词器的场景。

    BLEU/ROUGE 对中文常用字符级或词级；此处统一用字符级，
    既不引入分词依赖，又能稳定反映字面重合度。
    """
    return [ch for ch in text if not ch.isspace()]


# ===== BLEU-4 实现 =====
def _ngram_counts(tokens: Sequence[str], n: int) -> Counter:
    return Counter(tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1))


def bleu_score(candidate: str, reference: str, max_n: int = BLEU_MAX_N) -> float:
    """计算 BLEU-n（默认 BLEU-4），含 brevity penalty。

    若候选或参考过短无法构成 n-gram，对应阶精度记 0 并按平滑处理：
    对 0 计数取极小值 epsilon，避免几何均值直接归零。
    """
    cand = tokenize_zh(candidate)
    ref = tokenize_zh(reference)

    # 过短文本无法支撑 4-gram，直接返回字符级 1-gram 精度作为保守估计
    if len(cand) < max_n or len(ref) < max_n:
        if not cand or not ref:
            return 0.0
        common = Counter(cand) & Counter(ref)
        hits = sum(common.values())
        return hits / len(cand) if cand else 0.0

    precisions: list[float] = []
    for n in range(1, max_n + 1):
        cand_n = _ngram_counts(cand, n)
        ref_n = _ngram_counts(ref, n)
        # 命中数 = 每个候选 n-gram 与参考取最小计数后求和（clip）
        hits = sum(min(c, ref_n.get(ng, 0)) for ng, c in cand_n.items())
        total = sum(cand_n.values())
        # 平滑：避免某阶 0 命中导致几何均值直接为 0
        p = hits / total if total else 0.0
        precisions.append(p if p > 0 else 1e-7)

    # brevity penalty：候选比参考短时惩罚
    bp = 1.0 if len(cand) >= len(ref) else math.exp(1 - len(ref) / len(cand))
    # 几何均值
    log_sum = sum(math.log(p) for p in precisions)
    geo_mean = math.exp(log_sum / max_n)
    return bp * geo_mean


# ===== ROUGE-L 实现 =====
def _lcs_length(a: Sequence[str], b: Sequence[str]) -> int:
    """最长公共子序列长度（动态规划）。"""
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0
    # 滚动数组优化空间
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev = curr
    return prev[n]


def rouge_l_score(candidate: str, reference: str) -> float:
    """计算 ROUGE-L F1（基于最长公共子序列）。

    F1 = 2*P*R/(P+R)，P=LCS/len(cand), R=LCS/len(ref)。
    对短文本评测更稳定，是开放式问答常用配置。
    """
    cand = tokenize_zh(candidate)
    ref = tokenize_zh(reference)
    if not cand or not ref:
        return 0.0
    lcs = _lcs_length(cand, ref)
    p = lcs / len(cand)
    r = lcs / len(ref)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


# ===== TF-IDF 余弦相似度（轻量语义指标，零外部依赖） =====
def semantic_similarity(candidate: str, reference: str) -> float:
    """基于 TF-IDF 字符 n-gram 向量余弦相似度，作为语义接近度的轻量近似。

    与 BLEU/ROUGE 互补：BLEU 看精确 n-gram 命中，TF-IDF 余弦看整体词汇分布
    的相对方向，对同义不同字、关键词重叠但不连续的场景更敏感。
    返回 [0,1] 区间，1 表示词汇分布高度接近。
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    if not candidate.strip() or not reference.strip():
        return 0.0
    # 用字符 2-gram 作为最小语义单元，对中文短文本更稳健
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3))
    try:
        matrix = vec.fit_transform([candidate, reference])
    except ValueError:
        # 极端短文本无有效 2-gram 时退回 1-gram
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 1))
        matrix = vec.fit_transform([candidate, reference])
    cos = cosine_similarity(matrix[0], matrix[1])[0, 0]
    return float(max(0.0, cos))


# ===== 评测主流程 =====
def load_answers(path: Path) -> dict[str, str]:
    """从评测结果 JSON 中提取 question_id -> answer 映射。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["question_id"]: r["answer"] for r in data["results"] if r.get("success")}


def evaluate_pair(candidate: str, reference: str) -> dict[str, float]:
    """对一对（候选，参考）计算全部指标。"""
    return {
        "bleu4": round(bleu_score(candidate, reference), 4),
        "rouge_l": round(rouge_l_score(candidate, reference), 4),
        "semantic_sim": round(semantic_similarity(candidate, reference), 4),
    }


def aggregate(metrics: list[dict[str, float]]) -> dict[str, float]:
    """对逐题指标取均值与标准差，产出汇总。"""
    import numpy as np
    keys = ["bleu4", "rouge_l", "semantic_sim"]
    agg = {}
    for k in keys:
        vals = [m[k] for m in metrics]
        agg[f"mean_{k}"] = round(float(np.mean(vals)), 4)
        agg[f"std_{k}"] = round(float(np.std(vals)), 4)
    return agg


def main() -> None:
    print("=" * 60)
    print("自动指标评测：BLEU-4 / ROUGE-L / 语义相似度")
    print("=" * 60)

    lora_ans = load_answers(LORA_JSON)
    base_ans = load_answers(BASE_JSON)
    # 题目顺序以 LoRA 文件为准
    lora_data = json.loads(LORA_JSON.read_text(encoding="utf-8"))
    questions = [(r["question_id"], r["category"], r["question"]) for r in lora_data["results"]]

    # 双向评测：LoRA 以 base 为参考，base 以 lora 为参考
    lora_metrics: list[dict] = []
    base_metrics: list[dict] = []
    per_question = []

    print(f"\n共 {len(questions)} 道题，开始计算自动指标...\n")

    for i, (qid, cat, q) in enumerate(questions, 1):
        lora_a = lora_ans.get(qid, "")
        base_a = base_ans.get(qid, "")
        # LoRA 答案 vs 基座参考
        m_lora = evaluate_pair(lora_a, base_a)
        # 基座答案 vs LoRA 参考
        m_base = evaluate_pair(base_a, lora_a)
        lora_metrics.append(m_lora)
        base_metrics.append(m_base)
        per_question.append({
            "question_id": qid,
            "category": cat,
            "question": q,
            "lora_vs_base_ref": m_lora,
            "base_vs_lora_ref": m_base,
        })
        print(f"[{i}/{len(questions)}] {qid} {cat}")
        print(f"   LoRA : BLEU={m_lora['bleu4']:.3f} ROUGE-L={m_lora['rouge_l']:.3f} 语义={m_lora['semantic_sim']:.3f}")
        print(f"   Base : BLEU={m_base['bleu4']:.3f} ROUGE-L={m_base['rouge_l']:.3f} 语义={m_base['semantic_sim']:.3f}")

    lora_agg = aggregate(lora_metrics)
    base_agg = aggregate(base_metrics)

    output = {
        "指标说明": {
            "bleu4": "BLEU-4 字面 n-gram 精度，含 brevity penalty；越高越接近参考答案措辞",
            "rouge_l": "ROUGE-L F1，基于最长公共子序列；越高越覆盖参考答案关键内容",
            "semantic_sim": "TF-IDF 字符 n-gram 余弦相似度 [0,1]，衡量词汇分布接近度；越高关键词覆盖越一致",
            "参考方向": "lora_vs_base_ref=以基座答案为参考评 LoRA；base_vs_lora_ref=以 LoRA 答案为参考评基座，双向对称",
        },
        "lora_vs_base_ref_汇总": lora_agg,
        "base_vs_lora_ref_汇总": base_agg,
        "per_question": per_question,
    }

    print("\n" + "=" * 60)
    print("汇总（均值）")
    print("=" * 60)
    print(f"{'模型':<12}{'BLEU-4':<12}{'ROUGE-L':<12}{'语义相似':<12}")
    print(f"{'LoRA':<12}{lora_agg['mean_bleu4']:<12}{lora_agg['mean_rouge_l']:<12}{lora_agg['mean_semantic_sim']:<12}")
    print(f"{'基座':<12}{base_agg['mean_bleu4']:<12}{base_agg['mean_rouge_l']:<12}{base_agg['mean_semantic_sim']:<12}")

    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存到: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
