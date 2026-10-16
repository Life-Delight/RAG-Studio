import logging
import threading
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from app.core.config import CHROMA_DIR, CHROMA_COLLECTION_PREFIX

logger = logging.getLogger(__name__)

_client: Optional[chromadb.PersistentClient] = None
_client_lock = threading.Lock()


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.PersistentClient(
                    path=str(CHROMA_DIR),
                    settings=Settings(anonymized_telemetry=False)
                )
    return _client


class VectorService:
    def __init__(self, kb_id: int):
        self.kb_id = kb_id
        self.collection_name = f"{CHROMA_COLLECTION_PREFIX}{kb_id}"
        self.client = get_chroma_client()
        self._collection = None

    def _get_or_create_collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"kb_id": self.kb_id}
            )
        return self._collection

    def add_documents(
        self,
        doc_id: int,
        filename: str,
        chunks: List[str],
        embeddings: List[List[float]]
    ):
        collection = self._get_or_create_collection()
        
        ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"doc_id": doc_id, "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ]
        
        # Add in batches to avoid memory issues
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch_ids = ids[i:i+batch_size]
            batch_docs = chunks[i:i+batch_size]
            batch_embeds = embeddings[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]
            
            collection.add(
                ids=batch_ids,
                documents=batch_docs,
                embeddings=batch_embeds,
                metadatas=batch_meta
            )
        
        logger.info(f"Added {len(chunks)} chunks to collection {self.collection_name}")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        doc_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        collection = self._get_or_create_collection()
        
        where_filter = None
        if doc_ids:
            if len(doc_ids) == 1:
                where_filter = {"doc_id": {"$eq": doc_ids[0]}}
            else:
                where_filter = {"doc_id": {"$in": doc_ids}}
        
        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, collection.count() or 1),
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.warning(f"Search error: {e}")
            return []
        
        hits = []
        if results and results["documents"] and results["documents"][0]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            ):
                hits.append({
                    "content": doc,
                    "metadata": meta,
                    "score": 1 - dist  # Convert distance to similarity
                })
        
        return hits

    def delete_document(self, doc_id: int):
        collection = self._get_or_create_collection()
        try:
            collection.delete(where={"doc_id": {"$eq": doc_id}})
            logger.info(f"Deleted document {doc_id} from collection {self.collection_name}")
        except Exception as e:
            logger.warning(f"Error deleting document {doc_id}: {e}")

    def delete_collection(self):
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection {self.collection_name}")
        except Exception as e:
            logger.warning(f"Error deleting collection {self.collection_name}: {e}")

    def count(self) -> int:
        try:
            collection = self._get_or_create_collection()
            return collection.count()
        except Exception:
            return 0
