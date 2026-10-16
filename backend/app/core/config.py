import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploaded_files")))
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(BASE_DIR / "chroma_data")))
DATABASE_DIR = Path(os.getenv("DATABASE_DIR", str(BASE_DIR / "database")))

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_URL = f"sqlite:///{DATABASE_DIR}/rag.db"

# LLM settings (OpenAI-compatible: Ollama / DeepSeek / Zhipu etc.)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-chat")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")

# Embedding settings
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# ChromaDB
CHROMA_COLLECTION_PREFIX = "kb_"

# Chunking
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
TOP_K = int(os.getenv("TOP_K", "20"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.55"))
HIGH_CONFIDENCE_SCORE = float(os.getenv("HIGH_CONFIDENCE_SCORE", "0.72"))
MIN_SOURCE_HITS = int(os.getenv("MIN_SOURCE_HITS", "3"))
MIN_SOURCE_GROUPS = int(os.getenv("MIN_SOURCE_GROUPS", "1"))

# Hybrid search
ENABLE_HYBRID_SEARCH = os.getenv("ENABLE_HYBRID_SEARCH", "true").lower() in ("true", "1", "yes")
RRF_K = int(os.getenv("RRF_K", "60"))

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
