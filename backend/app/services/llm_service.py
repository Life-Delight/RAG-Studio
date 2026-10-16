import logging
import asyncio
import httpx
from typing import List, AsyncGenerator, Dict, Optional
from openai import AsyncOpenAI
from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL, LLM_API_KEY

logger = logging.getLogger(__name__)
MAX_HISTORY_TURNS = 3
NO_CONTEXT_NOTICE = "当前知识库未检索到足够相关的参考内容，以下回答基于通用知识生成，仅供参考。"
# 模型响应超时保护：read 超时表示“两个数据块之间”的最长等待，
# 防止上游（代理 / 模型服务）静默中断时前后端无限等待
LLM_TIMEOUT = httpx.Timeout(connect=10.0, read=45.0, write=15.0, pool=15.0)


def sanitize_response_text(text: str, strip_edges: bool = True) -> str:
    sanitized = (text or "").replace("\r", "")
    sanitized = sanitized.replace("$$", "")

    compact_chars: List[str] = []
    newline_count = 0
    for ch in sanitized:
        if ch == "\n":
            newline_count += 1
            if newline_count <= 2:
                compact_chars.append(ch)
        else:
            newline_count = 0
            compact_chars.append(ch)

    normalized = "".join(compact_chars)
    return normalized.strip() if strip_edges else normalized


def get_async_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key=LLM_API_KEY,
        timeout=LLM_TIMEOUT,
        max_retries=0,
    )


async def warmup_llm() -> None:
    try:
        client = get_async_client()
        await client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": "你好"}],
            stream=False,
            temperature=0.0,
            max_tokens=8,
        )
        logger.info("LLM warmup completed")
    except Exception as e:
        logger.warning(f"LLM warmup skipped: {e}")


def select_recent_history_turns(history: List[Dict[str, str]], max_turns: int = MAX_HISTORY_TURNS) -> List[Dict[str, str]]:
    turns: List[List[Dict[str, str]]] = []
    current_turn: List[Dict[str, str]] = []

    for item in history:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue

        if role == "user" and current_turn:
            turns.append(current_turn)
            current_turn = []

        current_turn.append({"role": role, "content": content})

    if current_turn:
        turns.append(current_turn)

    selected_turns = turns[-max_turns:]
    flattened: List[Dict[str, str]] = []
    for turn in selected_turns:
        flattened.extend(turn)
    return flattened


def build_rag_messages(
    question: str,
    contexts: List[str],
    history: List[Dict[str, str]] | None = None,
    summary_mode: bool = False,
    primary_document_name: Optional[str] = None,
    selected_document_names: Optional[List[str]] = None,
    explicit_doc_scope: bool = False,
) -> List[Dict[str, str]]:
    history = [] if explicit_doc_scope else select_recent_history_turns(history or [])

    if contexts:
        context_text = "\n\n".join(
            [f"[参考文档 {i+1}]:\n{ctx}" for i, ctx in enumerate(contexts)]
        )
        summary_instruction = ""
        selected_docs_instruction = ""
        if selected_document_names:
            joined_names = "、".join(f"《{name}》" for name in selected_document_names)
            selected_docs_instruction = f"""
本轮问答限定的目标文档为：{joined_names}。
请优先依据这些文档片段作答，不要脱离文档内容泛化为通用常识列表。
如果文档片段里没有明确写到某个细节，请直接说明“根据当前检索到的文档片段，未明确提到该细节”。
"""
        if summary_mode:
            target_doc_text = f"《{primary_document_name}》" if primary_document_name else "当前命中的文档"
            summary_instruction = f"""
当前问题属于文档总结请求，且知识库已检索到可用参考片段。
请直接基于这些片段总结 {target_doc_text} 的主要内容、核心主题、关键要求或结论。{selected_docs_instruction}
不要再回答“当前知识库未检索到足够相关的参考内容”或类似表述。
如果片段信息不完整，可以明确说明“根据当前检索到的片段”，但仍需继续完成总结。
"""
        elif explicit_doc_scope:
            summary_instruction = f"""
当前问题已经限定在指定文档范围内，且知识库已检索到可用参考片段。
请直接基于文档片段回答当前问题，不要输出脱离文档依据的通用写作建议或常识性模板。{selected_docs_instruction}
只能陈述当前片段中明确出现或可以直接概括出的要求；不要补充字体字号、页边距、引用格式等未在片段中出现的具体细节。
如果文档片段中能提炼出要求，请按要点列出；如果没有明确要求，就明确说明文档未明确写出。
"""
        system_prompt = f"""你是一个面向企业员工使用的管理知识库问答助手，服务于企业管理制度问答场景（员工手册、考勤请假、报销流程、人事制度、行政规范等）。
你需要结合参考文档和历史对话，回答用户当前问题。
如果用户当前问题出现“它、他、这个、上述内容、上一点”等指代，请优先结合历史对话理解其含义。
优先基于参考文档回答：只要参考文档中存在与该问题相关的内容（文档主题可以是企业制度，也可以是中药、技术、产品等任何主题），就必须依据参考文档作答，并注明来源文档名。
如果参考文档中没有足够信息，请明确说明无法从文档中找到答案，不要编造事实。
只有当参考文档与当前问题确实完全无关时（例如文档里只有企业制度与中药资料，用户问的却是游戏、影视，或要求写文案），才在第一句标注“以下为通用知识，不来自企业知识库：”，再用通用知识简要、审慎地作答——禁止对参考文档中已有的内容加这个标注。
回答请使用中文，先直接回答问题，再给出简短解释或办理步骤；不要使用 Markdown 标题，不要输出 ##、###。
涉及流程类问题（如报销、请假、入职办理）时，优先按步骤列出：第1步、第2步……并注明需要的材料、负责部门和注意事项。
如果用户问“有哪些、怎么分类、需要什么条件”，优先分点概括，控制在 3 到 6 点，每点 1 到 2 句话。{summary_instruction}

参考文档：
{context_text}
"""
    else:
        system_prompt = f"""你是一个面向企业员工使用的管理知识问答助手，服务于企业管理制度问答场景（员工手册、考勤请假、报销流程、人事制度、行政规范等）。
当前知识库未检索到足够相关的参考内容。
你可以基于通用知识给出简洁、审慎的回答，但必须先在第一句标注“以下为通用知识，不来自企业知识库：”，且不要伪造“参考文档”或“文档依据”。
如果用户的问题依赖当前知识库中的具体制度、流程或数据，请直接说明当前知识库未命中，并建议用户换一种问法或补充相关制度文档。
回答请使用中文，先直接回答问题，再给出简短解释；不要使用 Markdown 标题，不要输出 ##、###。
涉及流程类问题（如报销、请假、入职办理）时，优先按步骤列出：第1步、第2步……并注明需要的材料、负责部门和注意事项。
如果用户问“有哪些、怎么分类、需要什么条件”，优先分点概括，控制在 3 到 6 点，每点 1 到 2 句话。
"""

    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})
    return messages


async def stream_answer(
    question: str,
    contexts: List[str],
    history: List[Dict[str, str]] | None = None,
    summary_mode: bool = False,
    primary_document_name: Optional[str] = None,
    selected_document_names: Optional[List[str]] = None,
    explicit_doc_scope: bool = False,
) -> AsyncGenerator[str, None]:
    client = get_async_client()
    messages = build_rag_messages(
        question,
        contexts,
        history,
        summary_mode=summary_mode,
        primary_document_name=primary_document_name,
        selected_document_names=selected_document_names,
        explicit_doc_scope=explicit_doc_scope,
    )
    try:
        if not contexts:
            yield NO_CONTEXT_NOTICE + "\n"
        stream = await client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=True,
            temperature=0.2 if explicit_doc_scope else 0.5,
            max_tokens=1536,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except Exception as e:
        logger.error(f"LLM stream error: {e}")
        text = str(e).lower()
        if "timeout" in text or "timed out" in text:
            yield "\n\n[本次回答中断：模型响应超时（长时间没有数据返回），已保留已生成的内容。请重新提问或稍后重试。]"
        else:
            yield f"\n[错误：调用模型失败 - {str(e)}]"


async def get_answer(
    question: str,
    contexts: List[str],
    history: List[Dict[str, str]] | None = None,
    summary_mode: bool = False,
    primary_document_name: Optional[str] = None,
    selected_document_names: Optional[List[str]] = None,
    explicit_doc_scope: bool = False,
) -> str:
    client = get_async_client()
    messages = build_rag_messages(
        question,
        contexts,
        history,
        summary_mode=summary_mode,
        primary_document_name=primary_document_name,
        selected_document_names=selected_document_names,
        explicit_doc_scope=explicit_doc_scope,
    )
    try:
        resp = await client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=False,
            temperature=0.2 if explicit_doc_scope else 0.5,
            max_tokens=1536,
        )
        return sanitize_response_text(resp.choices[0].message.content or "")
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise
