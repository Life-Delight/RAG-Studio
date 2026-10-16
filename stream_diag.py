"""SSE 流式输出诊断：记录每个数据块到达的时间，判断是否真流式、或被中间层缓冲。"""
import json
import sys
import time

import httpx

url = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else url
agent_mode = len(sys.argv) > 3 and sys.argv[3] == "agent"
payload = {
    "kb_id": 1,
    "question": "请完整介绍一下公司的年假制度、请假审批流程和差旅报销住宿标准，尽量详细。",
    "agent_mode": agent_mode,
}
start = time.time()
marks = []
first_meta = None
statuses = []
try:
    # trust_env=False：绕过系统代理（否则 localhost 请求会被代理拦截导致测量失真）
    with httpx.stream("POST", url, json=payload, timeout=180, trust_env=False) as resp:
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            p = line[6:]
            if p == "[DONE]":
                continue
            if p.startswith("[META]"):
                if first_meta is None:
                    first_meta = round(time.time() - start, 2)
                continue
            try:
                obj = json.loads(p)
            except Exception:
                continue
            if isinstance(obj, str):
                marks.append((round(time.time() - start, 2), obj))
            elif isinstance(obj, dict) and obj.get("type") == "status":
                statuses.append((round(time.time() - start, 2), obj.get("message", "")))
except Exception as e:
    print(f"[{label}] 请求失败: {e}")
    sys.exit(1)

print(f"[{label}]")
print(f"  首个响应(META)到达: +{first_meta}s   <- 前端从这一刻就能显示状态")
print("  阶段状态推送:")
for t, m in statuses:
    print(f"    +{t:>6.2f}s  {m}")
print(f"  总数据块: {len(marks)}")
txt = "".join(m[1] for m in marks)
print(f"  回答总长: {len(txt)} 字")
if marks:
    print(f"  首块文字: +{marks[0][0]}s")
    print(f"  末块文字: +{marks[-1][0]}s")
    burst = sum(1 for i, (t, _) in enumerate(marks) if i > 0 and t - marks[i - 1][0] < 0.005)
    print(f"  瞬时并发块数(间隔<5ms): {burst} / {max(len(marks) - 1, 1)}")
