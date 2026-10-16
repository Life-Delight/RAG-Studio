"""验证：检索到的内容是否真的被拼进提示词、交给 DeepSeek 回答。

证据链（全部使用项目自身代码，不做任何修改）：
  1) app.services.embedding_service.embed_query  → 问题向量化
  2) app.services.bm25_service.hybrid_search     → 混合检索拿回文档片段
  3) app.services.llm_service.build_rag_messages → 项目真实使用的「组装发给大模型的 messages」函数
  4) app.services.llm_service.get_async_client   → 项目真实的 DeepSeek 客户端
  5) 真实调用 → 检查回答里出现只存在于知识库文档中的事实（canary 校验）
"""
import asyncio
import re
import sys

sys.path.insert(0, "backend")

from app.core.config import OLLAMA_MODEL, TOP_K
from app.services.bm25_service import hybrid_search
from app.services.embedding_service import embed_query
from app.services.llm_service import build_rag_messages, get_async_client

QUESTION = "年假有多少天？最多能结转到什么时候？差旅住宿标准是多少？"

# ---------- 1. 检索 ----------
query_emb = embed_query(QUESTION)
hits = hybrid_search(kb_id=1, query=QUESTION, query_embedding=query_emb, top_k=TOP_K, doc_ids=None)
hits = [h for h in hits if h.get("content")]
files = sorted({(h.get("metadata") or {}).get("filename", "?") for h in hits})
print(f"[1] 混合检索命中 {len(hits)} 段，来自文档：{files}")

contexts = [h["content"] for h in hits[:5]]
print(f"[2] 取前 {len(contexts)} 段作为上下文，总长度 {sum(len(c) for c in contexts)} 字")

# ---------- 2. 用项目自身函数组装 messages ----------
messages = build_rag_messages(QUESTION, contexts)
roles = [m["role"] for m in messages]
print(f"[3] 组装完成：共 {len(messages)} 条消息，角色序列 = {roles}")

system_prompt = messages[0]["content"]
print(f"[4] system prompt 长度 {len(system_prompt)} 字")
print(f"    包含「参考文档：」小节 = {'参考文档：' in system_prompt}")
print(f"    包含【参考文档 N】标记 = {bool(re.search(r'\\[参考文档 \\d+\\]', system_prompt))}")
found_markers = re.findall(r"\[参考文档 (\d+)\]:", system_prompt)
print(f"    注入的文档片段编号 = {found_markers}")

print("\n    ---- 提示词里实际注入的文档内容（每段前 90 字）----")
for m in re.finditer(r"\[参考文档 \d+\]:\n(.+?)(?=\n\n\[参考文档 |\Z)", system_prompt, re.S):
    snippet = re.sub(r"\s+", " ", m.group(1).strip())[:90]
    print(f"    • {snippet} ...")

with open("verify_prompt_dump.txt", "w", encoding="utf-8") as f:
    f.write(f"=== 用户问题 ===\n{QUESTION}\n\n=== 实际发给 DeepSeek 的完整 messages ===\n")
    for msg in messages:
        f.write(f"\n---------- role: {msg['role']} ----------\n{msg['content']}\n")
print("\n[5] 完整提示词已导出到 verify_prompt_dump.txt（可直接打开查看）")

# ---------- 3. 动态提取 canary：只可能来自文档的细节 ----------
canaries = set()
joined = "\n".join(contexts)
for token in re.findall(r"[0-9A-Z]{10,}", joined):      # 如纳税人识别号
    canaries.add(token)
for pattern in (r"满\s*\d+\s*年[^，。；\n]{0,12}", r"\d+\s*天", r"\d+\s*月\s*\d+\s*日", r"\d+\s*元"):
    for token in re.findall(pattern, joined)[:4]:
        canaries.add(token.strip())
canaries = sorted(canaries)[:10]

# ---------- 4. 真实调用 DeepSeek ----------
async def main():
    client = get_async_client()
    resp = await client.chat.completions.create(
        model=OLLAMA_MODEL, messages=messages, stream=False, temperature=0.2, max_tokens=800
    )
    answer = (resp.choices[0].message.content or "").strip()
    print("\n[6] DeepSeek 返回的回答：")
    print("-" * 56)
    print(answer[:700])
    print("-" * 56)
    print(f"\n[7] canary 校验（这些细节只存在于知识库文档里，模型不可能凭空知道）：")
    hit = 0
    for c in canaries:
        ok = c.replace(" ", "") in answer.replace(" ", "")
        hit += ok
        print(f"    {'✅' if ok else '·'} {c}")
    print(f"\n    命中 {hit}/{len(canaries)} —— 命中即为「检索内容确实喂给了大模型」的直接证据")
    print(f"    本次调用 token 用量：prompt={resp.usage.prompt_tokens}, completion={resp.usage.completion_tokens}")


asyncio.run(main())
