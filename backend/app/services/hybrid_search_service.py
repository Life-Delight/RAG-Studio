import logging
from typing import List, Dict, Any, Optional

from app.services.vector_service import VectorService
from app.services.bm25_service import BM25Index
from app.services.embedding_service import embed_query
from app.core.config import TOP_K

logger = logging.getLogger(__name__)

RRF_K = 60  # standard RRF constant


def reciprocal_rank_fusion(
    vector_hits: List[Dict[str, Any]],
    bm25_hits: List[Dict[str, Any]],
    k: int = RRF_K,
) -> List[Dict[str, Any]]:
    """Merge two ranked lists using Reciprocal Rank Fusion (RRF).

    RRF score = sum( 1 / (k + rank_i) ) for each list where the doc appears.
    """
    score_map: Dict[str, float] = {}
    doc_map: Dict[str, Dict[str, Any]] = {}

    def _doc_key(hit: Dict[str, Any]) -> str:
        meta = hit.get("metadata") or {}
        return f"{meta.get('doc_id', '?')}_{meta.get('chunk_index', '?')}"

    for rank, hit in enumerate(vector_hits):
        key = _doc_key(hit)
        score_map[key] = score_map.get(key, 0.0) + 1.0 / (k + rank + 1)
        if key not in doc_map:
            doc_map[key] = hit.copy()
            doc_map[key]["vector_rank"] = rank + 1
            doc_map[key]["bm25_rank"] = None
        else:
            doc_map[key]["vector_rank"] = rank + 1

    for rank, hit in enumerate(bm25_hits):
        key = _doc_key(hit)
        score_map[key] = score_map.get(key, 0.0) + 1.0 / (k + rank + 1)
        if key not in doc_map:
            doc_map[key] = hit.copy()
            doc_map[key]["bm25_rank"] = rank + 1
            doc_map[key]["vector_rank"] = None
        else:
            doc_map[key]["bm25_rank"] = rank + 1

    sorted_keys = sorted(score_map.keys(), key=lambda x: score_map[x], reverse=True)

    results = []
    for key in sorted_keys:
        item = doc_map[key]
        item["score"] = score_map[key]
        results.append(item)

    return results


def hybrid_search(
    kb_id: int,
    query: str,
    top_k: int = TOP_K,
    doc_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """Perform hybrid search combining vector similarity and BM25 keyword matching."""

    query_embedding = embed_query(query)
    vs = VectorService(kb_id)
    vector_hits = vs.search(query_embedding, top_k=top_k, doc_ids=doc_ids)

    bm25_index = BM25Index(kb_id)
    bm25_index.build(doc_ids=doc_ids)
    bm25_hits = bm25_index.search(query, top_k=top_k)

    if not vector_hits and not bm25_hits:
        return []

    if not bm25_hits:
        logger.info("BM25 returned no results, using vector-only for kb_%s", kb_id)
        return vector_hits

    if not vector_hits:
        logger.info("Vector search returned no results, using BM25-only for kb_%s", kb_id)
        return bm25_hits

    fused = reciprocal_rank_fusion(vector_hits, bm25_hits)

    logger.info(
        "Hybrid search for kb_%s: vector=%d, bm25=%d, fused=%d",
        kb_id, len(vector_hits), len(bm25_hits), len(fused),
    )

    return fused[:top_k]
