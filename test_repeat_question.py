"""复现用户场景：同一会话中连续多次追问同一问题，检查是否会出现编造/罗列无关数据。"""
import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
QUESTION = sys.argv[3] if len(sys.argv) > 3 else "罗义灶是谁？"

client = httpx.Client(trust_env=False, timeout=180)
session_id = None

for i in range(1, ROUNDS + 1):
    payload = {"kb_id": 1, "question": QUESTION, "agent_mode": True}
    if session_id:
        payload["session_id"] = session_id

    text = ""
    tools = []
    with client.stream("POST", f"{BASE}/api/chat/stream", json=payload) as resp:
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            p = line[6:]
            if p == "[DONE]":
                continue
            if p.startswith("[META]"):
                try:
                    meta = json.loads(p[6:])
                    if meta.get("session_id"):
                        session_id = meta["session_id"]
                except Exception:
                    pass
                continue
            try:
                obj = json.loads(p)
            except Exception:
                continue
            if isinstance(obj, str):
                text += obj
            elif isinstance(obj, dict) and obj.get("type") == "tool_call":
                tools.append(obj.get("name"))

    print(f"--- 第 {i} 次提问 ---")
    print(f"  调用工具: {', '.join(tools) or '（未调用任何工具）'}")
    print(f"  回答: {text.strip()[:400]}")
    print()

client.close()
