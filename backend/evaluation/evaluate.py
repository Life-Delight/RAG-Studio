"""
RAG 系统评估脚本

评估指标：
1. 检索评估：Hit Rate@K, MRR (Mean Reciprocal Rank)
2. 生成评估：关键词覆盖率, ROUGE-L, 忠实度（LLM 打分）
3. 对比实验：纯向量检索 vs 混合检索
"""

import json
import sys
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import TOP_K, MIN_RELEVANCE_SCORE
from app.services.embedding_service import embed_query
from app.services.vector_service import VectorService
from app.services.bm25_service import hybrid_search, get_bm25_index
from app.services.llm_service import get_answer


def load_test_dataset(path: str = None) -> List[Dict[str, Any]]:
    if path is None:
        path = str(Path(__file__).parent / "test_dataset.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


# ============ 检索评估指标 ============

def evaluate_hit_rate(hits: List[Dict], expected_keywords: List[str], k: int = 5) -> float:
    """Hit Rate@K: 前K个结果中是否包含至少一个期望关键词"""
    top_k_content = " ".join(h["content"] for h in hits[:k])
    for keyword in expected_keywords:
        if keyword in top_k_content:
            return 1.0
    return 0.0


def evaluate_mrr(hits: List[Dict], expected_keywords: List[str]) -> float:
    """MRR: 第一个包含期望关键词的结果的排名倒数"""
    for i, hit in enumerate(hits):
        content = hit.get("content", "")
        for keyword in expected_keywords:
            if keyword in content:
                return 1.0 / (i + 1)
    return 0.0


def evaluate_keyword_hit_count(hits: List[Dict], expected_keywords: List[str], k: int = 5) -> float:
    """关键词命中率：前K个结果中命中了多少比例的期望关键词"""
    top_k_content = " ".join(h["content"] for h in hits[:k])
    hit_count = sum(1 for kw in expected_keywords if kw in top_k_content)
    return hit_count / len(expected_keywords) if expected_keywords else 0.0


# ============ 生成评估指标 ============

def evaluate_keyword_coverage(answer: str, expected_keywords: List[str]) -> float:
    """关键词覆盖率：回答中包含了多少比例的期望关键词"""
    if not expected_keywords:
        return 0.0
    hit_count = sum(1 for kw in expected_keywords if kw in answer)
    return hit_count / len(expected_keywords)


def evaluate_rouge_l(answer: str, reference: str) -> float:
    """ROUGE-L: 基于最长公共子序列的文本相似度"""
    try:
        from rouge_chinese import Rouge
        import jieba

        answer_seg = " ".join(jieba.lcut(answer))
        reference_seg = " ".join(jieba.lcut(reference))

        if not answer_seg.strip() or not reference_seg.strip():
            return 0.0

        rouge = Rouge()
        scores = rouge.get_scores(answer_seg, reference_seg)
        return scores[0]["rouge-l"]["f"]
    except Exception:
        return _simple_rouge_l(answer, reference)


def _simple_rouge_l(answer: str, reference: str) -> float:
    """简易 ROUGE-L 实现（不依赖外部库）"""
    if not answer or not reference:
        return 0.0

    def lcs_length(x: str, y: str) -> int:
        m, n = len(x), len(y)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if x[i - 1] == y[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                else:
                    dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
        return dp[m][n]

    lcs = lcs_length(answer, reference)
    precision = lcs / len(answer) if answer else 0
    recall = lcs / len(reference) if reference else 0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


async def evaluate_faithfulness_llm(
    answer: str, contexts: List[str], question: str
) -> float:
    """忠实度评估：用 LLM 判断回答是否基于检索到的上下文（0-1分）"""
    if not contexts or not answer.strip():
        return 0.0

    context_text = "\n".join(contexts[:5])
    eval_prompt = f"""请评估以下回答是否忠实于给定的参考文档内容。

参考文档：
{context_text}

问题：{question}
回答：{answer}

评分标准（只输出一个0到10的整数）：
- 10分：回答完全基于参考文档，没有编造信息
- 7-9分：回答主要基于参考文档，有少量合理推断
- 4-6分：回答部分基于参考文档，有一些未在文档中出现的信息
- 1-3分：回答大部分内容不在参考文档中
- 0分：回答完全与参考文档无关

请只输出一个整数分数："""

    try:
        result = await get_answer(eval_prompt, [], None)
        score_text = result.strip()
        for char in score_text:
            if char.isdigit():
                score = int(char)
                if score_text.startswith("10"):
                    score = 10
                return min(score, 10) / 10.0
        return 0.5
    except Exception:
        return -1.0


# ============ 检索方式对比 ============

def retrieval_vector_only(kb_id: int, query: str, top_k: int = 20, doc_ids=None) -> List[Dict]:
    query_emb = embed_query(query)
    vs = VectorService(kb_id)
    return vs.search(query_emb, top_k=top_k, doc_ids=doc_ids)


def retrieval_hybrid(kb_id: int, query: str, top_k: int = 20, doc_ids=None) -> List[Dict]:
    query_emb = embed_query(query)
    return hybrid_search(
        kb_id=kb_id,
        query=query,
        query_embedding=query_emb,
        top_k=top_k,
        doc_ids=doc_ids,
    )


# ============ 主评估流程 ============

async def run_evaluation(
    kb_id: int,
    test_cases: List[Dict[str, Any]],
    top_k: int = 5,
    run_generation: bool = True,
    run_faithfulness: bool = False,
) -> Dict[str, Any]:
    """
    运行完整评估流程

    Args:
        kb_id: 知识库 ID
        test_cases: 测试用例列表
        top_k: 检索评估时取前 K 个结果
        run_generation: 是否运行生成评估（较慢）
        run_faithfulness: 是否运行忠实度评估（需要 LLM，最慢）
    """
    results = {
        "kb_id": kb_id,
        "total_cases": len(test_cases),
        "top_k": top_k,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "retrieval_metrics": {
            "vector_only": {"hit_rate": [], "mrr": [], "keyword_hit": []},
            "hybrid": {"hit_rate": [], "mrr": [], "keyword_hit": []},
        },
        "generation_metrics": {
            "keyword_coverage": [],
            "rouge_l": [],
            "faithfulness": [],
        },
        "details": [],
    }

    print(f"\n{'='*60}")
    print(f"RAG 系统评估 | 知识库 ID: {kb_id} | 测试用例: {len(test_cases)}")
    print(f"{'='*60}\n")

    for i, case in enumerate(test_cases):
        question = case["question"]
        expected_keywords = case.get("expected_keywords", [])
        reference_answer = case.get("reference_answer", "")

        print(f"[{i+1}/{len(test_cases)}] {question}")

        detail = {
            "id": case.get("id", f"case_{i}"),
            "question": question,
            "topic": case.get("topic", ""),
        }

        # --- 纯向量检索评估 ---
        vector_hits = retrieval_vector_only(kb_id, question, top_k=top_k)
        v_hit_rate = evaluate_hit_rate(vector_hits, expected_keywords, k=top_k)
        v_mrr = evaluate_mrr(vector_hits, expected_keywords)
        v_kw_hit = evaluate_keyword_hit_count(vector_hits, expected_keywords, k=top_k)

        results["retrieval_metrics"]["vector_only"]["hit_rate"].append(v_hit_rate)
        results["retrieval_metrics"]["vector_only"]["mrr"].append(v_mrr)
        results["retrieval_metrics"]["vector_only"]["keyword_hit"].append(v_kw_hit)

        # --- 混合检索评估 ---
        hybrid_hits = retrieval_hybrid(kb_id, question, top_k=top_k)
        h_hit_rate = evaluate_hit_rate(hybrid_hits, expected_keywords, k=top_k)
        h_mrr = evaluate_mrr(hybrid_hits, expected_keywords)
        h_kw_hit = evaluate_keyword_hit_count(hybrid_hits, expected_keywords, k=top_k)

        results["retrieval_metrics"]["hybrid"]["hit_rate"].append(h_hit_rate)
        results["retrieval_metrics"]["hybrid"]["mrr"].append(h_mrr)
        results["retrieval_metrics"]["hybrid"]["keyword_hit"].append(h_kw_hit)

        detail["retrieval"] = {
            "vector_only": {"hit_rate": v_hit_rate, "mrr": v_mrr, "keyword_hit": v_kw_hit},
            "hybrid": {"hit_rate": h_hit_rate, "mrr": h_mrr, "keyword_hit": h_kw_hit},
        }

        print(f"  检索 | 向量: HR={v_hit_rate:.1f} MRR={v_mrr:.2f} | 混合: HR={h_hit_rate:.1f} MRR={h_mrr:.2f}")

        # --- 生成评估 ---
        if run_generation:
            contexts = [h["content"] for h in hybrid_hits[:8]]
            try:
                answer = await get_answer(question, contexts, None)
                kw_coverage = evaluate_keyword_coverage(answer, expected_keywords)
                rouge_l = evaluate_rouge_l(answer, reference_answer)

                results["generation_metrics"]["keyword_coverage"].append(kw_coverage)
                results["generation_metrics"]["rouge_l"].append(rouge_l)

                detail["generation"] = {
                    "answer_preview": answer[:200],
                    "keyword_coverage": kw_coverage,
                    "rouge_l": rouge_l,
                }

                print(f"  生成 | 关键词覆盖: {kw_coverage:.2f} | ROUGE-L: {rouge_l:.3f}")

                if run_faithfulness:
                    faithfulness = await evaluate_faithfulness_llm(answer, contexts, question)
                    results["generation_metrics"]["faithfulness"].append(faithfulness)
                    detail["generation"]["faithfulness"] = faithfulness
                    print(f"  忠实度: {faithfulness:.2f}")

            except Exception as e:
                print(f"  生成评估失败: {e}")
                results["generation_metrics"]["keyword_coverage"].append(0)
                results["generation_metrics"]["rouge_l"].append(0)

        results["details"].append(detail)

    # --- 汇总统计 ---
    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    summary = {
        "retrieval": {
            "vector_only": {
                "avg_hit_rate": avg(results["retrieval_metrics"]["vector_only"]["hit_rate"]),
                "avg_mrr": avg(results["retrieval_metrics"]["vector_only"]["mrr"]),
                "avg_keyword_hit": avg(results["retrieval_metrics"]["vector_only"]["keyword_hit"]),
            },
            "hybrid": {
                "avg_hit_rate": avg(results["retrieval_metrics"]["hybrid"]["hit_rate"]),
                "avg_mrr": avg(results["retrieval_metrics"]["hybrid"]["mrr"]),
                "avg_keyword_hit": avg(results["retrieval_metrics"]["hybrid"]["keyword_hit"]),
            },
        },
    }

    if run_generation:
        summary["generation"] = {
            "avg_keyword_coverage": avg(results["generation_metrics"]["keyword_coverage"]),
            "avg_rouge_l": avg(results["generation_metrics"]["rouge_l"]),
        }
        if run_faithfulness:
            valid_scores = [s for s in results["generation_metrics"]["faithfulness"] if s >= 0]
            summary["generation"]["avg_faithfulness"] = avg(valid_scores)

    results["summary"] = summary

    # --- 打印汇总 ---
    print(f"\n{'='*60}")
    print("评估结果汇总")
    print(f"{'='*60}")
    print(f"\n检索评估 (Top-{top_k}):")
    print(f"  {'指标':<16} {'纯向量':>10} {'混合检索':>10} {'提升':>10}")
    print(f"  {'-'*46}")

    for metric_name, display_name in [("avg_hit_rate", "Hit Rate"), ("avg_mrr", "MRR"), ("avg_keyword_hit", "关键词命中")]:
        v_val = summary["retrieval"]["vector_only"][metric_name]
        h_val = summary["retrieval"]["hybrid"][metric_name]
        improvement = h_val - v_val
        sign = "+" if improvement >= 0 else ""
        print(f"  {display_name:<16} {v_val:>10.3f} {h_val:>10.3f} {sign}{improvement:>9.3f}")

    if run_generation:
        print(f"\n生成评估:")
        print(f"  平均关键词覆盖率: {summary['generation']['avg_keyword_coverage']:.3f}")
        print(f"  平均 ROUGE-L:     {summary['generation']['avg_rouge_l']:.3f}")
        if run_faithfulness and "avg_faithfulness" in summary["generation"]:
            print(f"  平均忠实度:       {summary['generation']['avg_faithfulness']:.3f}")

    print(f"\n{'='*60}\n")

    return results


def save_results(results: Dict[str, Any], output_path: str = None):
    if output_path is None:
        output_path = str(Path(__file__).parent / "evaluation_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"评估结果已保存到: {output_path}")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG 系统评估脚本")
    parser.add_argument("--kb-id", type=int, required=True, help="知识库 ID")
    parser.add_argument("--top-k", type=int, default=5, help="检索评估 Top-K (默认 5)")
    parser.add_argument("--no-generation", action="store_true", help="跳过生成评估")
    parser.add_argument("--faithfulness", action="store_true", help="启用忠实度评估（较慢）")
    parser.add_argument("--dataset", type=str, default=None, help="测试数据集路径")
    parser.add_argument("--output", type=str, default=None, help="结果输出路径")

    args = parser.parse_args()

    test_cases = load_test_dataset(args.dataset)
    print(f"加载测试数据集: {len(test_cases)} 条用例")

    results = await run_evaluation(
        kb_id=args.kb_id,
        test_cases=test_cases,
        top_k=args.top_k,
        run_generation=not args.no_generation,
        run_faithfulness=args.faithfulness,
    )

    save_results(results, args.output)


if __name__ == "__main__":
    asyncio.run(main())
