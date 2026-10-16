import logging
import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.core.config import CORS_ORIGINS
from app.models.database import init_db
from app.api import knowledge_base, chat
from app.services.embedding_service import get_embedding_model
from app.services.llm_service import warmup_llm

# 静态资源目录（前端构建产物），存在时同时提供页面与 API（单端口模式）
BACKEND_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(os.getenv("STATIC_DIR", str(BACKEND_ROOT / "static")))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# index.html 禁止缓存：避免用户浏览器沿用旧版本前端资源（导致界面更新不生效）
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

app = FastAPI(
    title="RAG问答系统 API",
    description="基于RAG技术的智能问答系统，使用本地Ollama模型",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(knowledge_base.router)
app.include_router(chat.router)


@app.on_event("startup")
async def startup_event():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized.")

    logger.info("Warming up embedding model in background...")
    asyncio.create_task(asyncio.to_thread(get_embedding_model))

    logger.info("Warming up LLM in background...")
    asyncio.create_task(warmup_llm())

    logger.info("RAG Q&A System started successfully!")


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "RAG问答系统运行正常"}


@app.get("/")
def root():
    if (STATIC_DIR / "index.html").is_file():
        return FileResponse(STATIC_DIR / "index.html", headers=NO_CACHE_HEADERS)
    return {"message": "RAG问答系统 API", "docs": "/docs"}


# ---- 单端口模式：托管前端构建产物 + SPA fallback（必须在 API 路由之后注册）----
_spa_registered = False

# 带哈希的构建产物可长期缓存（文件名变了自然会重新下载）
ASSET_CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}

def _register_spa():
    global _spa_registered
    if _spa_registered:
        return
    _spa_registered = True

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("docs"):
            return {"detail": "Not Found"}
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            if full_path.startswith("assets/"):
                return FileResponse(candidate, headers=ASSET_CACHE_HEADERS)
            return FileResponse(candidate, headers=NO_CACHE_HEADERS)
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index, headers=NO_CACHE_HEADERS)
        return {"detail": "Not Found"}

if (STATIC_DIR / "index.html").is_file():
    _register_spa()
    logger.info(f"Serving frontend static files from {STATIC_DIR}")
