"""验证（智能体模式）：工具（知识库检索）的返回结果是否被回灌给大模型。

做法：在不修改项目代码的前提下，用录制式客户端包裹项目真实的 DeepSeek 客户端，
把 agent 循环里每一次真实请求的 messages 抓下来打印，直接看 role=tool 的消息是否存在。
"""
import asyncio
import json
import sys

sys.path.insert(0, "backend")

import app.services.agent_service as agent_svc
from app.services.agent_service import stream_agent_answer

captured = []


class RecordingClient:
    """包装真实客户端，记录每次请求的 messages，再原样转发。"""

    def __init__(self, inner):
        self._inner = inner

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    async def create(self, **kwargs):
        captured.append(kwargs.get("messages") or [])
        return await self._inner.chat.completions.create(**kwargs)


_real_get_async_client = agent_svc.get_async_client
agent_svc.get_async_client = lambda: RecordingClient(_real_get_async_client())

QUESTION = "公司研发部有多少名员工？另外差旅住宿标准是多少？"


async def main():
    answer = ""
    events = []
    async for ev in stream_agent_answer(QUESTION, kb_id=1, history=[], selected_doc_ids=None):
        if ev.get("type") == "content":
            answer += ev["content"]
        elif ev.get("type") in {"tool_call", "tool_result"}:
            events.append(ev)

    print(f"[1] 大模型被调用次数 = {len(captured)}（每轮工具决策 / 最终作答各一次）")
    print(f"[2] 工具调用事件 = {[e.get('name') for e in events if e.get('type') == 'tool_call']}")

    print("\n[3] 逐次请求的 messages 构成：")
    for i, msgs in enumerate(captured, 1):
        roles = [m.get("role") for m in msgs]
        print(f"    第 {i} 次请求：{len(msgs)} 条消息，角色序列 = {roles}")
        for m in msgs:
            if m.get("role") == "tool":
                body = (m.get("content") or "").replace("\n", " ")[:110]
                print(f"        └─ role=tool 回灌内容（前 110 字）：{body} ...")
            if m.get("role") == "assistant" and m.get("tool_calls"):
                calls = [c["function"]["name"] for c in m["tool_calls"]]
                print(f"        └─ role=assistant 发起的工具调用：{calls}")

    print("\n[4] 最终回答：")
    print("-" * 56)
    print(answer.strip()[:600])
    print("-" * 56)

    tool_msgs = [m for msgs in captured for m in msgs if m.get("role") == "tool"]
    print(f"\n[5] 结论：抓取到 {len(tool_msgs)} 条 role=tool 消息 —— "
          f"{'✅ 工具/检索结果确实被回灌给大模型' if tool_msgs else '❌ 未回灌'}")


asyncio.run(main())
