import logging
from threading import Lock
from typing import List
from sentence_transformers import SentenceTransformer
from app.core.config import EMBED_MODEL_NAME

logger = logging.getLogger(__name__)

_model = None
_model_lock = Lock()


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info(f"Loading embedding model: {EMBED_MODEL_NAME}")
                _model = SentenceTransformer(EMBED_MODEL_NAME)
                logger.info("Embedding model loaded successfully")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


def embed_query(query: str) -> List[float]:
    model = get_embedding_model()
    embedding = model.encode([query], show_progress_bar=False)
    return embedding[0].tolist()
