"""
快速评估脚本 - 简化版

使用方法：
1. 确保已有知识库并上传了高等数学相关文档
2. 运行: python run_eval.py --kb-id <知识库ID>

示例：
    python run_eval.py --kb-id 1
    python run_eval.py --kb-id 1 --quick  # 快速模式，只评估检索
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluate import load_test_dataset, run_evaluation, save_results


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG 系统快速评估")
    parser.add_argument("--kb-id", type=int, required=True, help="知识库 ID")
    parser.add_argument("--quick", action="store_true", help="快速模式（只评估检索，跳过生成）")
    parser.add_argument("--full", action="store_true", help="完整模式（包含忠实度评估）")

    args = parser.parse_args()

    test_cases = load_test_dataset()
    print(f"\n已加载 {len(test_cases)} 条高等数学测试用例\n")

    results = await run_evaluation(
        kb_id=args.kb_id,
        test_cases=test_cases,
        top_k=5,
        run_generation=not args.quick,
        run_faithfulness=args.full,
    )

    save_results(results)

    print("\n评估完成！结果已保存到 evaluation_results.json")
    print("\n关键指标说明：")
    print("  - Hit Rate: 检索结果中是否包含相关内容（越高越好）")
    print("  - MRR: 相关内容排名的倒数（越高越好，1.0 表示排第一）")
    print("  - 关键词命中: 检索到的内容覆盖了多少期望关键词")
    print("  - ROUGE-L: 生成答案与参考答案的文本相似度")
    print("  - 混合检索提升: 混合检索相比纯向量检索的改进幅度")


if __name__ == "__main__":
    asyncio.run(main())
