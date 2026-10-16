"""Agent 模式：基于 LLM Function Calling 的工具调用智能体。

与经典 RAG 模式（先检索后生成）不同，Agent 模式把检索、数据库查询、计算等能力
封装为工具（Tools），由大模型自主决策调用顺序与参数，可多轮迭代后给出最终答案。

SSE 事件协议（chat 接口转发给前端）：
- {"type": "tool_call",  "name": ..., "arguments": ...}   模型发起了工具调用
- {"type": "tool_result","name": ..., "result": ...}      工具执行完成，返回结果摘要
- {"type": "sources",    "sources": [...]}                 检索命中片段更新（用于参考来源展示）
- {"type": "content",    "content": ...}                   最终回答的增量文本
"""
import ast
import json
import logging
import operator
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.config import DATABASE_URL, MIN_RELEVANCE_SCORE, OLLAMA_MODEL, TOP_K
from app.models.database import beijing_now
from app.services.bm25_service import hybrid_search
from app.services.embedding_service import embed_query
from app.services.llm_service import get_async_client, select_recent_history_turns

logger = logging.getLogger(__name__)

# 最大工具调用轮数（防止死循环）
AGENT_MAX_ITERATIONS = 6


# ---------------------------------------------------------------------------
# 工具 Schema（OpenAI Function Calling 格式，DeepSeek 兼容）
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "检索企业制度知识库（员工手册、考勤请假、报销流程、人事制度等文档）。"
                           "用于回答公司制度、流程、规定类问题。建议用核心关键词作为 query。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题核心内容"},
                    "top_k": {"type": "integer", "description": "返回片段数量，默认8，范围1-15"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_business_data",
            "description": (
                "查询企业业务数据库（只读 SQLite）。表结构：\n"
                "employees(id, emp_no 工号, name 姓名, gender 性别, department 部门, position 职位, "
                "hire_date 入职日期, status 在职状态)\n"
                "leave_records(id, emp_id 员工id, leave_type 请假类型, start_date, end_date, days 天数, "
                "reason 事由, status 审批状态)\n"
                "reimbursements(id, emp_id 员工id, expense_type 费用类型, amount 金额, "
                "submit_date 提交日期, status 报销状态)\n"
                "emp_id 关联 employees.id。日期格式 YYYY-MM-DD。"
                "用于回答员工、部门、请假、报销等具体数据或统计问题。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQLite SELECT 查询语句（只读）"},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "精确数学计算器，支持加减乘除、幂、取模、括号。涉及金额、天数等计算时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，例如 450*3+100"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "获取今天的日期、星期与时间。涉及“今天/本月/截止/还剩几天”等时间基准时先调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_calculate(expression: str) -> str:
    """基于 AST 白名单的安全计算器，仅允许数值与四则运算。"""
    expression = (expression or "").strip()
    if not expression:
        return "计算失败：表达式为空"

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            left = _eval(node.left)
            right = _eval(node.right)
            result = _ALLOWED_BINOPS[type(node.op)](left, right)
            if abs(result) > 1e15:
                raise ValueError("结果超出可计算范围")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
            return _ALLOWED_UNARYOPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"不支持的表达式元素: {type(node).__name__}")

    try:
        result = _eval(ast.parse(expression, mode="eval"))
        return f"{expression} = {result:g}"
    except Exception as e:  # noqa: BLE001
        return f"计算失败：{e}"


_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|vacuum|"
    r"replace|reindex|grant|revoke)\b",
    re.IGNORECASE,
)
MAX_SQL_ROWS = 50


def query_business_data(sql: str) -> str:
    """只读 SQL 查询业务数据表（员工/请假/报销），返回 JSON 行。"""
    cleaned = (sql or "").strip().rstrip(";").strip()
    if not cleaned:
        return "查询失败：SQL 为空"
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        return "查询失败：仅支持 SELECT 查询"
    if _SQL_FORBIDDEN.search(cleaned):
        return "查询失败：检测到非只读操作，仅支持 SELECT"
    if ";" in cleaned:
        return "查询失败：不允许执行多条语句"

    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(cleaned)
            rows = cursor.fetchmany(MAX_SQL_ROWS)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
        finally:
            conn.close()
    except sqlite3.Error as e:
        return f"SQL 执行错误：{e}"

    if not rows:
        return (
            "查询成功：没有匹配的数据（0 行）。\n"
            "（提示：数据库中确实不存在该数据，请如实告知用户未查到，"
            "不要编造任何信息，也不要罗列其他无关记录来填充回答。）"
        )
    data = [dict(zip(columns, tuple(row))) for row in rows]
    return f"查询成功，返回 {len(data)} 行（上限 {MAX_SQL_ROWS} 行）：\n" + json.dumps(
        data, ensure_ascii=False, default=str
    )


def get_current_date() -> str:
    now = beijing_now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    return (
        f"今天是 {now.strftime('%Y-%m-%d')} {weekdays[now.weekday()]},"
        f"当前时间 {now.strftime('%H:%M')}"
    )


def search_knowledge_base_tool(
    query: str,
    top_k: Optional[int],
    kb_id: int,
    doc_ids: Optional[List[int]],
    hits_collector: List[dict],
) -> str:
    """检索知识库（复用混合检索），并把命中片段同步到参考来源收集器。"""
    query = (query or "").strip()
    if not query:
        return "检索失败：query 为空"
    try:
        top_k = max(1, min(int(top_k or 8), 15))
    except (TypeError, ValueError):
        top_k = 8

    query_emb = embed_query(query)
    raw_hits = hybrid_search(
        kb_id=kb_id,
        query=query,
        query_embedding=query_emb,
        top_k=max(top_k, TOP_K),
        doc_ids=doc_ids or None,
    )
    hits = [hit for hit in raw_hits if hit.get("content")]
    above_threshold = [hit for hit in hits if hit.get("score", 0) >= MIN_RELEVANCE_SCORE]
    picked = (above_threshold or hits)[:top_k]

    if not picked:
        return (
            "知识库中未检索到相关内容。\n"
            "（提示：请如实告知用户知识库中没有找到该信息，不要编造；"
            "可以尝试更换关键词后重试一次。）"
        )

    # 去重合并到参考来源（供前端展示）
    existing_keys = {
        ((hit.get("metadata") or {}).get("filename"), (hit.get("metadata") or {}).get("chunk_index"))
        for hit in hits_collector
    }
    for hit in picked:
        metadata = hit.get("metadata") or {}
        key = (metadata.get("filename"), metadata.get("chunk_index"))
        if key not in existing_keys:
            existing_keys.add(key)
            hits_collector.append(
                {
                    "content": hit["content"][:200],
                    "filename": metadata.get("filename", ""),
                    "score": round(hit.get("score", 0), 4),
                }
            )

    parts = []
    for i, hit in enumerate(picked, 1):
        metadata = hit.get("metadata") or {}
        parts.append(
            f"[片段{i} | 来源: {metadata.get('filename', '未知文档')} | 相关度: {round(hit.get('score', 0), 3)}]\n"
            f"{hit['content'][:600]}"
        )
    return "\n\n".join(parts)


def execute_tool(
    name: str,
    raw_arguments: str,
    kb_id: int,
    doc_ids: Optional[List[int]],
    hits_collector: List[dict],
) -> Dict[str, Any]:
    """执行一次工具调用，返回 {'output': 文本结果, 'sources_updated': bool}。"""
    try:
        arguments = json.loads(raw_arguments) if raw_arguments and raw_arguments.strip() else {}
    except json.JSONDecodeError:
        return {"output": "工具参数 JSON 解析失败", "sources_updated": False}

    sources_updated = False
    if name == "search_knowledge_base":
        output = search_knowledge_base_tool(
            arguments.get("query", ""), arguments.get("top_k"), kb_id, doc_ids, hits_collector
        )
        sources_updated = True
    elif name == "query_business_data":
        output = query_business_data(arguments.get("sql", ""))
    elif name == "calculate":
        output = safe_calculate(arguments.get("expression", ""))
    elif name == "get_current_date":
        output = get_current_date()
    else:
        output = f"错误：未知工具 {name}"

    logger.info(
        "Agent tool executed | name=%s arguments=%r output_len=%s",
        name,
        raw_arguments[:200] if raw_arguments else "",
        len(output),
    )
    return {"output": str(output), "sources_updated": sources_updated}


# ---------------------------------------------------------------------------
# 流式英文过渡语过滤（模型偶尔会在调用工具前输出英文，如 "I'll search the knowledge base..."）
# ---------------------------------------------------------------------------
CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
PREAMBLE_HOLD_LIMIT = 80   # 缓存上限：超过仍未出现中文则原样输出，避免误伤正常内容
PREAMBLE_MIN_DROP = 8      # 中文前的前缀长度达到该值才判定为英文过渡语并丢弃


class LeadingEnglishFilter:
    """抑制回复开头的英文过渡语。

    先缓存开头内容，遇到首个中文字符时判断：若前面是一段明显英文（长度 ≥ 8），丢弃该前缀；
    若缓存超过上限仍无中文，则原样输出（避免误伤 "OA 系统" 这类含少量拉丁字符的正常回答）。
    """

    def __init__(self):
        self._buffer = ""
        self._settled = False

    def feed(self, text: str) -> str:
        if self._settled or not text:
            return text
        self._buffer += text
        match = CJK_PATTERN.search(self._buffer)
        if match:
            prefix = self._buffer[: match.start()]
            rest = self._buffer[match.start():]
            self._buffer = ""
            self._settled = True
            return rest if match.start() >= PREAMBLE_MIN_DROP else prefix + rest
        if len(self._buffer) >= PREAMBLE_HOLD_LIMIT:
            out = self._buffer
            self._buffer = ""
            self._settled = True
            return out
        return ""

    def flush(self) -> str:
        """轮次结束时输出缓存内容（适用于最终答案）。"""
        out = self._buffer
        self._buffer = ""
        self._settled = True
        return out

    def drop(self) -> None:
        """轮次结束时丢弃缓存内容（适用于带工具调用的轮次，其文本只是过渡语）。"""
        self._buffer = ""
        self._settled = True


# ---------------------------------------------------------------------------
# Agent 主循环（流式）
# ---------------------------------------------------------------------------
def _llm_error_text(exc: Exception) -> str:
    """统一的大模型调用失败提示（区分超时，便于前端展示友好文案）。"""
    text = str(exc).lower()
    if "timeout" in text or "timed out" in text:
        return "\n\n[本次回答中断：模型响应超时（长时间没有数据返回），已保留已生成的内容。请重新提问或稍后重试。]"
    return f"\n[错误：调用模型失败 - {exc}]"


def build_agent_messages(question: str, history: Optional[List[dict]] = None) -> List[dict]:
    system_prompt = f"""你是一个企业智能管理助手，当前运行在智能体（Agent）模式，可以调用工具完成任务。

【知识边界：先检索，再由检索结果决定怎么答】
1. 知识类问题（问某个概念、事物、人物“是什么 / 为什么 / 怎么办”，无论话题是公司制度，还是中药、游戏、历史、技术等）：
   → 一律先调用 search_knowledge_base 检索知识库。
   → 只要知识库检索到相关内容，就必须基于文档作答并注明来源文档名，**绝对不可以标注“通用知识”**。知识库里有，就说明它属于本系统的知识范围，与话题是否和公司业务有关无关。
   → 只有知识库确实检索不到相关内容时，才可以用通用知识回答，并按第 6 条加标注。
2. 涉及本公司人员、部门、报销、请假等数据或事实 → 除检索知识库外还必须调用 query_business_data 核实；工具查不到就如实说明，严禁编造。
3. 任务型或闲聊型请求（写文案、翻译、润色、打招呼、计算、问日期）→ 不必检索知识库，直接处理；输出的是通用内容时按第 6 条加标注。
4. 判断不准时，一律按“先检索知识库”处理。检索成本很低，而“该答的没答”或“错误标注”的代价更大。

【企业范围事实的硬性约束】
4.1 回答中出现的任何公司相关事实（人名、身份、部门、数字、金额、日期、制度条款）都必须能在工具返回结果中找到出处。
4.2 工具没有返回的公司信息一律不得输出：严禁补充、推测或联想任何背景（例如某个人的学校、职业、头衔、评价）。宁可回答查不到，也不要编造。
4.3 工具返回 0 条结果时，简短说明“知识库与业务数据库中都没有相关记录”，并指出可提供的帮助方向（例如“如需核实公司人员，请提供工号或部门”）。

【通用问题的标注要求】
6. 只有在“已经检索过知识库、并确认知识库中没有相关内容”之后，才允许在第一句标注“以下为通用知识，不来自企业知识库：”。
   任何时候都不允许对知识库中已有的内容加这个标注；也不要用“这不是企业相关知识”作为理由给文档内容加标注。
   通用问题的回答要简洁、审慎；不确定的内容直接说明不确定，不要编造细节。

【工具选择】
7. 查知识、概念、制度、流程、规定 → search_knowledge_base（知识类问题第一步都要先查它）
8. 员工、部门、请假记录、报销记录等具体数据或统计 → query_business_data
9. 需要精确计算金额、天数 → 调用 calculate；涉及“今天、本月、截止、还剩几天”等时间基准 → 先调用 get_current_date
10. 一个问题可以按需组合多个工具；结果不足时允许调整关键词或 SQL 重试，但最多 {AGENT_MAX_ITERATIONS} 轮，之后必须给出最终答案

【其他约束】
11. 严禁在回答中罗列与问题无关的数据（例如把全部员工名单列一遍）；也不要描述内部查询过程（例如“我用模糊查询返回了 0 条记录”“命中的都是无关文档”）。
12. 同一问题被反复提问且没有新信息时，必须保持与之前一致的结论，不得改口，更不得编造新内容来“满足”提问。

【回答结构：让人读起来有逻辑】
13. 默认按“结论 → 依据 → 补充”三段式组织，没有相应内容的部分就省略：
    第一段给结论：一句话直接回答问题，带上关键数字或判定；
    第二段给依据：分点列出，每点写清来源（文档名 / 数据表）与具体数字、单位；
    第三段给补充：只写对用户有实际影响的注意事项（时限、例外、所需材料、办理入口）。
14. 分点统一用「1. 2. 3.」或「一是 / 二是」，每个点独立成行；不同部分之间空一行分隔。
15. 篇幅随问题复杂度自适应：简单问题 2~4 行；涉及制度流程、多个条件或多项数据时可以写完整一些（一般不超过 12 行），不要为了简短而漏掉关键条件或步骤。
16. 同一段回答内的口径要一致（单位、称谓、统计范围前后统一），所有数字必须与工具返回结果完全一致。

【表达要求】
17. 全程使用简体中文，严禁出现任何英文单词或句子（例如 "Let me...", "I'll query...", "Sure"）。
18. 调用工具前不要输出任何过渡语或说明文字（系统界面已自动展示“正在调用工具”状态），直接调用工具即可；最终回答直接给结论。
19. 不要使用 Markdown 符号（##、**、---），用纯文本的分点和空行表达层次。"""
    messages: List[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(select_recent_history_turns(history or []))
    messages.append({"role": "user", "content": question})
    return messages


async def stream_agent_answer(
    question: str,
    kb_id: int,
    history: Optional[List[dict]] = None,
    selected_doc_ids: Optional[List[int]] = None,
):
    """Agent 主循环：流式输出事件，工具调用最多 AGENT_MAX_ITERATIONS 轮。"""
    client = get_async_client()
    messages = build_agent_messages(question, history)
    hits_collector: List[dict] = []

    for iteration in range(AGENT_MAX_ITERATIONS):
        try:
            stream = await client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                stream=True,
                temperature=0.2,
                max_tokens=1536,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Agent LLM stream error: {e}")
            yield {"type": "content", "content": _llm_error_text(e)}
            return

        content_delta = ""
        tool_calls_acc: Dict[int, dict] = {}
        answer_filter = LeadingEnglishFilter()

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta and delta.content:
                content_delta += delta.content
                visible = answer_filter.feed(delta.content)
                if visible:
                    yield {"type": "content", "content": visible}
            if delta and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    acc = tool_calls_acc.setdefault(
                        tool_call.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if tool_call.id:
                        acc["id"] = tool_call.id
                    if tool_call.function:
                        if tool_call.function.name:
                            acc["name"] += tool_call.function.name
                        if tool_call.function.arguments:
                            acc["arguments"] += tool_call.function.arguments
            if choice.finish_reason:
                # finish_reason == "tool_calls" 表示模型请求调用工具
                pass

        if not tool_calls_acc:
            # 没有工具调用 → 本轮内容即最终答案（已流式输出，这里补发被缓存的尾部）
            tail = answer_filter.flush()
            if tail:
                yield {"type": "content", "content": tail}
            if not content_delta.strip():
                yield {"type": "content", "content": "（模型未返回内容，请重试）"}
            return

        # 本轮请求了工具调用：轮内文本只是过渡语（可能是英文），直接丢弃不展示
        answer_filter.drop()

        # 组装 assistant 消息（带 tool_calls）并依次执行工具
        calls = []
        for index in sorted(tool_calls_acc):
            acc = tool_calls_acc[index]
            calls.append(
                {
                    "id": acc["id"] or f"call_{iteration}_{index}",
                    "type": "function",
                    "function": {"name": acc["name"], "arguments": acc["arguments"]},
                }
            )
        messages.append(
            {"role": "assistant", "content": content_delta or None, "tool_calls": calls}
        )

        for call in calls:
            function_name = call["function"]["name"]
            raw_arguments = call["function"]["arguments"]
            yield {"type": "tool_call", "name": function_name, "arguments": raw_arguments}

            result = execute_tool(function_name, raw_arguments, kb_id, selected_doc_ids, hits_collector)
            if result["sources_updated"] and hits_collector:
                yield {"type": "sources", "sources": list(hits_collector)}

            result_text = result["output"]
            yield {"type": "tool_result", "name": function_name, "result": result_text[:400]}

            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": result_text}
            )

    # 超过最大轮数：强制不携带工具，直接生成最终答案
    logger.warning("Agent reached max iterations, forcing final answer without tools")
    try:
        stream = await client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=True,
            temperature=0.2,
            max_tokens=1536,
        )
        final_filter = LeadingEnglishFilter()
        async for chunk in stream:
            if not chunk.choices:
                continue
            if chunk.choices[0].delta and chunk.choices[0].delta.content:
                visible = final_filter.feed(chunk.choices[0].delta.content)
                if visible:
                    yield {"type": "content", "content": visible}
        tail = final_filter.flush()
        if tail:
            yield {"type": "content", "content": tail}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Agent final stream error: {e}")
        yield {"type": "content", "content": _llm_error_text(e)}
