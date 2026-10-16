import logging
from typing import List, Dict, Any, Optional
from threading import Lock

import jieba
from rank_bm25 import BM25Okapi

from app.models.database import SessionLocal, Document
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)

_bm25_cache: Dict[int, "BM25Index"] = {}
_cache_lock = Lock()


class BM25Index:
    """Per-knowledge-base BM25 index built from ChromaDB stored chunks."""

    def __init__(self, kb_id: int):
        self.kb_id = kb_id
        self.corpus_tokens: List[List[str]] = []
        self.corpus_docs: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None
        self._build_index()

    def _tokenize(self, text: str) -> List[str]:
        return [w for w in jieba.lcut(text) if w.strip() and len(w.strip()) > 1]

    def _build_index(self):
        vs = VectorService(self.kb_id)
        collection = vs._get_or_create_collection()
        total = collection.count()
        if total == 0:
            return

        batch_size = 500
        offset = 0
        while offset < total:
            results = collection.get(
                limit=batch_size,
                offset=offset,
                include=["documents", "metadatas"],
            )
            if not results or not results["documents"]:
                break
            for doc_text, meta in zip(results["documents"], results["metadatas"]):
                if not doc_text:
                    continue
                tokens = self._tokenize(doc_text)
                self.corpus_tokens.append(tokens)
                self.corpus_docs.append({
                    "content": doc_text,
                    "metadata": meta or {},
                })
            offset += batch_size

        if self.corpus_tokens:
            self.bm25 = BM25Okapi(self.corpus_tokens)
            logger.info("BM25 index built for kb_%s: %d documents", self.kb_id, len(self.corpus_tokens))

    def search(self, query: str, top_k: int = 20, doc_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        if not self.bm25 or not self.corpus_docs:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self.bm25.get_scores(query_tokens)

        scored_docs = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
            doc_meta = self.corpus_docs[idx]
            if doc_ids:
                meta_doc_id = doc_meta["metadata"].get("doc_id")
                if meta_doc_id not in doc_ids:
                    continue
            scored_docs.append({
                "content": doc_meta["content"],
                "metadata": doc_meta["metadata"],
                "score": float(score),
                "rank": 0,
            })

        scored_docs.sort(key=lambda x: x["score"], reverse=True)
        for i, doc in enumerate(scored_docs[:top_k]):
            doc["rank"] = i + 1

        return scored_docs[:top_k]


def get_bm25_index(kb_id: int) -> BM25Index:
    with _cache_lock:
        if kb_id not in _bm25_cache:
            _bm25_cache[kb_id] = BM25Index(kb_id)
        return _bm25_cache[kb_id]


def invalidate_bm25_cache(kb_id: int):
    with _cache_lock:
        _bm25_cache.pop(kb_id, None)


def rebuild_bm25_index(kb_id: int):
    with _cache_lock:
        _bm25_cache[kb_id] = BM25Index(kb_id)


def hybrid_search(
    kb_id: int,
    query: str,
    query_embedding: List[float],
    top_k: int = 20,
    doc_ids: Optional[List[int]] = None,
    rrf_k: int = 60,
    vector_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Hybrid search combining vector similarity and BM25 using
    Reciprocal Rank Fusion (RRF).

    RRF score = sum( weight / (k + rank_i) ) for each retrieval method
    """
    vs = VectorService(kb_id)
    vector_hits = vs.search(query_embedding, top_k=top_k, doc_ids=doc_ids)

    bm25_index = get_bm25_index(kb_id)
    bm25_hits = bm25_index.search(query, top_k=top_k, doc_ids=doc_ids)

    fusion_scores: Dict[str, Dict[str, Any]] = {}

    for rank, hit in enumerate(vector_hits, start=1):
        key = f"{hit['metadata'].get('doc_id', '')}_{hit['metadata'].get('chunk_index', '')}_{hash(hit['content'][:50])}"
        rrf_score = vector_weight / (rrf_k + rank)
        if key not in fusion_scores:
            fusion_scores[key] = {
                "content": hit["content"],
                "metadata": hit["metadata"],
                "vector_score": hit.get("score", 0),
                "bm25_score": 0,
                "rrf_score": 0,
            }
        fusion_scores[key]["rrf_score"] += rrf_score
        fusion_scores[key]["vector_score"] = hit.get("score", 0)

    for rank, hit in enumerate(bm25_hits, start=1):
        key = f"{hit['metadata'].get('doc_id', '')}_{hit['metadata'].get('chunk_index', '')}_{hash(hit['content'][:50])}"
        rrf_score = bm25_weight / (rrf_k + rank)
        if key not in fusion_scores:
            fusion_scores[key] = {
                "content": hit["content"],
                "metadata": hit["metadata"],
                "vector_score": 0,
                "bm25_score": 0,
                "rrf_score": 0,
            }
        fusion_scores[key]["rrf_score"] += rrf_score
        fusion_scores[key]["bm25_score"] = hit.get("score", 0)

    results = sorted(fusion_scores.values(), key=lambda x: x["rrf_score"], reverse=True)

    final_hits = []
    for item in results[:top_k]:
        final_hits.append({
            "content": item["content"],
            "metadata": item["metadata"],
            "score": item["vector_score"] if item["vector_score"] > 0 else item["rrf_score"],
            "rrf_score": item["rrf_score"],
            "vector_score": item["vector_score"],
            "bm25_score": item["bm25_score"],
        })

    logger.info(
        "Hybrid search | kb_id=%s vector_hits=%d bm25_hits=%d fused=%d",
        kb_id, len(vector_hits), len(bm25_hits), len(final_hits),
    )

    return final_hits
