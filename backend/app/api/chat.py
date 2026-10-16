import asyncio
import json
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.models.database import get_db, ChatSession, ChatMessage, KnowledgeBase, Document, beijing_now
from app.services.embedding_service import embed_query
from app.services.vector_service import VectorService
from app.services.bm25_service import hybrid_search
from app.services.llm_service import stream_answer, NO_CONTEXT_NOTICE
from app.services.agent_service import stream_agent_answer
from app.core.config import TOP_K, MIN_RELEVANCE_SCORE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])
SUMMARY_HINT_KEYWORDS = (
    "总结", "概括", "概述", "摘要", "主要内容", "主要讲了什么", "主要讲述", "核心内容", "主要信息"
)
DOCUMENT_HINT_KEYWORDS = ("文档", "文件", "资料", "文章", "本文", "这份", "该")

# SSE 响应头：禁用各级代理/网关的响应缓冲，保证服务端一有数据就能推给浏览器
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",   # Nginx 等网关：关闭缓冲
    "Connection": "keep-alive",
}

# 工具名 -> 中文展示名（用于状态提示）
TOOL_DISPLAY_NAMES = {
    "search_knowledge_base": "知识库检索",
    "query_business_data": "业务数据查询",
    "calculate": "数学计算",
    "get_current_date": "获取当前日期",
}


def sse_json(payload: dict) -> str:
    """把结构化事件编码为一条 SSE 数据帧。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_status(stage: str, message: str, **extra) -> str:
    """阶段状态事件：前端用它显示“正在检索/正在生成”等实时进度。"""
    payload = {"type": "status", "stage": stage, "message": message}
    payload.update(extra)
    return sse_json(payload)


class SessionCreate(BaseModel):
    kb_id: int
    title: Optional[str] = "新对话"


class SessionResponse(BaseModel):
    id: int
    kb_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    sources: str
    tool_steps: str = "[]"
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[int] = None
    kb_id: int
    selected_doc_ids: Optional[List[int]] = None
    agent_mode: bool = False


def build_retrieval_query(question: str, history: List[dict]) -> str:
    latest_user_question = ""
    for message in reversed(history):
        if message.get("role") == "user":
            latest_user_question = (message.get("content") or "").strip()
            if latest_user_question:
                break

    if not latest_user_question:
        return question

    return f"上一轮问题：{latest_user_question}\n当前追问：{question}"


def filter_relevant_hits(hits: List[dict]) -> List[dict]:
    content_hits = [hit for hit in hits if hit.get("content")]
    if not content_hits:
        return []

    content_hits.sort(key=lambda hit: hit.get("score", 0), reverse=True)
    threshold_hits = [
        hit for hit in content_hits
        if hit.get("score", 0) >= MIN_RELEVANCE_SCORE
    ]
    if threshold_hits:
        return threshold_hits[:8]

    return content_hits[:5]


def is_document_summary_question(question: str) -> bool:
    normalized = (question or "").strip()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in SUMMARY_HINT_KEYWORDS) and any(
        keyword in normalized for keyword in DOCUMENT_HINT_KEYWORDS
    )


def select_summary_fallback_hits(raw_hits: List[dict]) -> List[dict]:
    fallback_hits = [hit for hit in raw_hits if hit.get("content")]
    fallback_hits.sort(key=lambda hit: hit.get("score", 0), reverse=True)
    return fallback_hits[: min(8, len(fallback_hits))]


def select_dominant_doc_id(raw_hits: List[dict]) -> Optional[int]:
    best_doc_id: Optional[int] = None
    best_doc_score = float("-inf")
    grouped_scores: dict[int, float] = {}

    for hit in raw_hits:
        metadata = hit.get("metadata") or {}
        doc_id = metadata.get("doc_id")
        score = hit.get("score", 0)
        if doc_id is None:
            continue
        grouped_scores[doc_id] = grouped_scores.get(doc_id, 0.0) + score

    for doc_id, score in grouped_scores.items():
        if score > best_doc_score:
            best_doc_id = doc_id
            best_doc_score = score

    return best_doc_id


def build_summary_context_hits(raw_hits: List[dict]) -> List[dict]:
    dominant_doc_id = select_dominant_doc_id(raw_hits)
    if dominant_doc_id is None:
        return select_summary_fallback_hits(raw_hits)

    same_doc_hits = [
        hit for hit in raw_hits
        if (hit.get("metadata") or {}).get("doc_id") == dominant_doc_id and hit.get("content")
    ]
    if same_doc_hits:
        same_doc_hits.sort(key=lambda hit: hit.get("score", 0), reverse=True)
        return same_doc_hits[:8]

    return select_summary_fallback_hits(raw_hits)


def resolve_context_hits(question: str, raw_hits: List[dict], has_explicit_doc_scope: bool = False) -> List[dict]:
    if is_document_summary_question(question):
        return build_summary_context_hits(raw_hits)
    if has_explicit_doc_scope:
        return select_summary_fallback_hits(raw_hits)
    return filter_relevant_hits(raw_hits)


def summarize_hits_for_log(hits: List[dict], limit: int = 5) -> List[dict]:
    summary: List[dict] = []
    for hit in hits[:limit]:
        metadata = hit.get("metadata") or {}
        summary.append({
            "score": round(hit.get("score", 0), 4),
            "doc_id": metadata.get("doc_id"),
            "filename": metadata.get("filename", ""),
            "chunk_index": metadata.get("chunk_index")
        })
    return summary


def get_summary_target_document_name(db: Session, kb_id: int, hits: List[dict]) -> Optional[str]:
    filenames = [((hit.get("metadata") or {}).get("filename") or "").strip() for hit in hits]
    unique_filenames = [filename for filename in dict.fromkeys(filenames) if filename]
    if len(unique_filenames) == 1:
        return unique_filenames[0]

    ready_docs = db.query(Document).filter(
        Document.kb_id == kb_id,
        Document.status == "ready"
    ).all()
    if len(ready_docs) == 1:
        return ready_docs[0].original_name or ready_docs[0].filename

    return unique_filenames[0] if unique_filenames else None


def get_effective_selected_doc_ids(db: Session, kb_id: int, selected_doc_ids: Optional[List[int]]) -> List[int]:
    ready_docs = db.query(Document).filter(
        Document.kb_id == kb_id,
        Document.status == "ready"
    ).order_by(Document.created_at.desc()).all()
    ready_doc_ids = {doc.id for doc in ready_docs}

    if selected_doc_ids:
        return [doc_id for doc_id in selected_doc_ids if doc_id in ready_doc_ids]

    if len(ready_docs) == 1:
        return [ready_docs[0].id]

    return []


def get_selected_document_names(db: Session, kb_id: int, doc_ids: List[int]) -> List[str]:
    if not doc_ids:
        return []

    docs = db.query(Document).filter(
        Document.kb_id == kb_id,
        Document.id.in_(doc_ids)
    ).all()
    docs_by_id = {doc.id: (doc.original_name or doc.filename) for doc in docs}
    return [docs_by_id[doc_id] for doc_id in doc_ids if doc_id in docs_by_id]


@router.get("/diag-stream")
async def diag_stream():
    """流式自检端点：服务端每 100ms 推送一块，共 30 块（约 3 秒）。

    与 LLM 无关、节奏确定，用于判断浏览器 / 代理 / 网关是否把 SSE 缓冲成一次性返回：
    - 客户端应在约 3 秒内陆续收到 30 块（逐块到达 = 传输层正常）
    - 若 30 块在几十毫秒内一次性到齐 = 中间层存在缓冲
    """
    async def generate():
        for i in range(30):
            yield sse_json({"seq": i + 1, "total": 30, "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3]})
            await asyncio.sleep(0.1)
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(kb_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(ChatSession)
    if kb_id:
        q = q.filter(ChatSession.kb_id == kb_id)
    return q.order_by(ChatSession.updated_at.desc()).all()


@router.post("/sessions", response_model=SessionResponse)
def create_session(data: SessionCreate, db: Session = Depends(get_db)):
    session = ChatSession(kb_id=data.kb_id, title=data.title or "新对话")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"message": "Session deleted"}


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages(session_id: int, db: Session = Depends(get_db)):
    return db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()


@router.post("/stream")
async def chat_stream(req: ChatRequest, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == req.kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if req.session_id:
        session = db.query(ChatSession).filter(ChatSession.id == req.session_id).first()
        if not session:
            session = ChatSession(kb_id=req.kb_id, title=req.question[:30])
            db.add(session)
            db.commit()
            db.refresh(session)
    else:
        session = ChatSession(kb_id=req.kb_id, title=req.question[:30])
        db.add(session)
        db.commit()
        db.refresh(session)

    history_messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session.id
    ).order_by(ChatMessage.created_at.asc()).all()
    history = [
        {"role": message.role, "content": message.content}
        for message in history_messages
        if message.role in {"user", "assistant"} and (message.content or "").strip()
    ]

    user_msg = ChatMessage(session_id=session.id, role="user", content=req.question, sources="[]")
    db.add(user_msg)
    db.commit()

    logger.info(
        "Chat request | kb_id=%s session_id=%s agent_mode=%s question=%r",
        req.kb_id,
        session.id,
        req.agent_mode,
        req.question,
    )

    effective_selected_doc_ids = get_effective_selected_doc_ids(db, req.kb_id, req.selected_doc_ids)

    # ---------------- Agent 模式：由 LLM 自主决策调用工具 ----------------
    if req.agent_mode:
        agent_session_id = session.id

        async def generate_agent():
            full_answer = ""
            final_sources: list = []
            tool_steps: list = []
            meta = json.dumps(
                {"session_id": agent_session_id, "sources": [], "agent_mode": True},
                ensure_ascii=False,
            )
            yield f"data: [META]{meta}\n\n"
            yield sse_status("thinking", "正在分析问题，规划要调用的工具…")

            async for event in stream_agent_answer(
                req.question,
                kb_id=req.kb_id,
                history=history,
                selected_doc_ids=effective_selected_doc_ids,
            ):
                event_type = event.get("type")
                if event_type == "content":
                    full_answer += event["content"]
                    yield f"data: {json.dumps(event['content'], ensure_ascii=False)}\n\n"
                elif event_type == "tool_call":
                    tool_name = event.get("name", "")
                    tool_steps.append(
                        {
                            "name": tool_name,
                            "arguments": event.get("arguments", ""),
                            "result": "",
                            "status": "running",
                        }
                    )
                    yield sse_json(event)
                    yield sse_status(
                        "tool",
                        f"正在调用「{TOOL_DISPLAY_NAMES.get(tool_name, tool_name)}」…",
                    )
                elif event_type == "tool_result":
                    for step in reversed(tool_steps):
                        if step["name"] == event.get("name") and step["status"] == "running":
                            step["result"] = event.get("result", "")
                            step["status"] = "done"
                            break
                    yield sse_json(event)
                    yield sse_status("generating", "已获取工具结果，正在生成回答…")
                elif event_type == "sources":
                    final_sources = event.get("sources", [])
                    yield sse_json({"type": "sources", "sources": final_sources})

            assistant_msg = ChatMessage(
                session_id=agent_session_id,
                role="assistant",
                content=full_answer,
                sources=json.dumps(final_sources, ensure_ascii=False),
                tool_steps=json.dumps(tool_steps, ensure_ascii=False),
            )
            db.add(assistant_msg)
            db.query(ChatSession).filter(ChatSession.id == agent_session_id).update(
                {"updated_at": beijing_now()}
            )
            db.commit()
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate_agent(), media_type="text/event-stream", headers=SSE_HEADERS)

    # ---------------- 经典 RAG 模式：先建流推状态，再在流内检索 + 生成 ----------------
    session_id = session.id
    is_summary_question = is_document_summary_question(req.question)
    has_explicit_doc_scope = bool(effective_selected_doc_ids)
    retrieval_query = req.question if (is_summary_question or has_explicit_doc_scope) else build_retrieval_query(req.question, history)
    selected_document_names = get_selected_document_names(db, req.kb_id, effective_selected_doc_ids)

    async def generate():
        full_answer = ""

        # 1) 立即建立 SSE 流并推送首个状态，前端马上就能显示“正在检索知识库…”
        meta = json.dumps(
            {"session_id": session_id, "sources": [], "no_context": False, "notice": "", "stage": "retrieving"},
            ensure_ascii=False,
        )
        yield f"data: [META]{meta}\n\n"
        yield sse_status("retrieving", "正在检索知识库…")

        logger.info(
            "Chat retrieval start | kb_id=%s session_id=%s summary_mode=%s question=%r retrieval_query=%r history_count=%s selected_doc_ids=%s explicit_doc_scope=%s",
            req.kb_id,
            session_id,
            is_summary_question,
            req.question,
            retrieval_query,
            len(history),
            effective_selected_doc_ids,
            has_explicit_doc_scope,
        )

        # 2) 执行检索：向量化与混合检索是 CPU 密集操作，放入线程池避免阻塞事件循环
        def _retrieve():
            query_emb = embed_query(retrieval_query)
            raw = hybrid_search(
                kb_id=req.kb_id,
                query=retrieval_query,
                query_embedding=query_emb,
                top_k=TOP_K,
                doc_ids=effective_selected_doc_ids or None,
            )
            resolved = resolve_context_hits(
                req.question,
                raw,
                has_explicit_doc_scope=has_explicit_doc_scope,
            )
            return raw, resolved

        try:
            raw_hits, hits = await run_in_threadpool(_retrieve)
        except Exception as retrieval_error:  # noqa: BLE001
            logger.error(
                "Chat retrieval failed | kb_id=%s session_id=%s error=%s",
                req.kb_id,
                session_id,
                retrieval_error,
            )
            raw_hits, hits = [], []
            yield sse_status("retrieving", "检索异常，正在尝试直接回答…")

        logger.info(
            "Chat retrieval raw hits (hybrid) | kb_id=%s session_id=%s raw_hit_count=%s raw_hit_preview=%s",
            req.kb_id,
            session_id,
            len(raw_hits),
            json.dumps(summarize_hits_for_log(raw_hits), ensure_ascii=False),
        )
        logger.info(
            "Chat retrieval resolved hits | kb_id=%s session_id=%s resolved_hit_count=%s resolved_hit_preview=%s explicit_doc_scope=%s fallback_to_top_hits=%s",
            req.kb_id,
            session_id,
            len(hits),
            json.dumps(summarize_hits_for_log(hits), ensure_ascii=False),
            has_explicit_doc_scope,
            bool(hits) and all(hit.get("score", 0) < MIN_RELEVANCE_SCORE for hit in hits),
        )
        if hits and is_summary_question:
            logger.info("Using summary-oriented retrieval strategy for question: %s", req.question)

        contexts = [h["content"] for h in hits]
        sources = [
            {"content": h["content"][:200], "filename": h["metadata"].get("filename", ""), "score": round(h["score"], 4)}
            for h in hits
        ]
        summary_target_document = get_summary_target_document_name(db, req.kb_id, hits) if is_summary_question else None
        if not summary_target_document and len(selected_document_names) == 1:
            summary_target_document = selected_document_names[0]
        if summary_target_document:
            logger.info(
                "Chat summary target document | kb_id=%s session_id=%s document=%r",
                req.kb_id,
                session_id,
                summary_target_document,
            )
        no_context = len(contexts) == 0
        if no_context:
            logger.warning(
                "Chat retrieval no context | kb_id=%s session_id=%s summary_mode=%s raw_hit_count=%s question=%r",
                req.kb_id,
                session_id,
                is_summary_question,
                len(raw_hits),
                req.question,
            )
        else:
            logger.info(
                "Chat retrieval contexts ready | kb_id=%s session_id=%s context_count=%s source_count=%s",
                req.kb_id,
                session_id,
                len(contexts),
                len(sources),
            )

        # 3) 检索完成：更新 META（带来源/未命中提示）并推送“正在生成”
        meta_update = json.dumps(
            {
                "session_id": session_id,
                "sources": sources,
                "no_context": no_context,
                "notice": NO_CONTEXT_NOTICE if no_context else "",
                "stage": "generating",
            },
            ensure_ascii=False,
        )
        yield f"data: [META]{meta_update}\n\n"
        if no_context:
            yield sse_status("generating", "未检索到相关内容，正在基于通用知识生成回答…")
        else:
            yield sse_status(
                "generating",
                f"已检索到 {len(sources)} 段相关内容，正在生成回答…",
                hit_count=len(sources),
            )

        # 4) 生成回答（真实流式，逐 token 推送）
        async for token in stream_answer(
            req.question,
            contexts,
            history,
            summary_mode=is_summary_question,
            primary_document_name=summary_target_document,
            selected_document_names=selected_document_names,
            explicit_doc_scope=has_explicit_doc_scope,
        ):
            full_answer += token
            yield f"data: {json.dumps(token, ensure_ascii=False)}\n\n"

        # 5) 落库并结束
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=full_answer,
            sources=json.dumps(sources, ensure_ascii=False)
        )
        db.add(assistant_msg)
        db.query(ChatSession).filter(ChatSession.id == session_id).update({"updated_at": beijing_now()})
        db.commit()
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream", headers=SSE_HEADERS)
