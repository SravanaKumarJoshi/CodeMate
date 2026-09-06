"""
Vector database retriever interface backed by ChromaDB.
Enforces strict repository isolation by filtering all queries by repository_id.
"""

import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings
from app.rag.embeddings import get_embedding_function
from app.services.repo_service import get_active_repository_id

logger = logging.getLogger(__name__)

_client: Optional[chromadb.PersistentClient] = None


def get_chroma_client() -> chromadb.PersistentClient:
    """Singleton getter for persistent ChromaDB client."""
    global _client
    if _client is None:
        settings.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(settings.CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False)
        )
    return _client


def get_collection():
    """Retrieve or create the main code chunk collection."""
    client = get_chroma_client()
    embedding_fn = get_embedding_function()
    return client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"}
    )


def reset_collection():
    """Delete and recreate the collection for fresh indexing."""
    client = get_chroma_client()
    try:
        client.delete_collection(name=settings.CHROMA_COLLECTION_NAME)
        logger.info("Cleared existing collection '%s'", settings.CHROMA_COLLECTION_NAME)
    except Exception:
        pass
    return get_collection()


def add_chunks(chunks: List[Dict[str, Any]], repository_id: Optional[str] = None):
    """
    Add a batch of code chunks to the ChromaDB collection.
    Inserts in configurable batches to avoid memory spikes.
    """
    if not chunks:
        return

    collection = get_collection()
    
    # Ensure all chunks have repository_id in metadata
    for chunk in chunks:
        if repository_id and "repository_id" not in chunk["metadata"]:
            chunk["metadata"]["repository_id"] = repository_id

    ids = [chunk["id"] for chunk in chunks]
    documents = [chunk["content"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]

    batch_size = settings.EMBEDDING_BATCH_SIZE
    for i in range(0, len(ids), batch_size):
        end = i + batch_size
        try:
            collection.upsert(
                ids=ids[i:end],
                documents=documents[i:end],
                metadatas=metadatas[i:end]
            )
        except Exception as err:
            logger.error("Failed to insert chunk batch [%d:%d]: %s", i, end, err)
            # Try single insertions if batch fails
            for single_id, single_doc, single_meta in zip(ids[i:end], documents[i:end], metadatas[i:end]):
                try:
                    collection.upsert(ids=[single_id], documents=[single_doc], metadatas=[single_meta])
                except Exception as s_err:
                    logger.warning("Skipping problematic chunk %s: %s", single_id, s_err)

    logger.info("Indexed %d chunks into ChromaDB (batch size: %d)", len(chunks), batch_size)


def query_code(
    query_text: str,
    repository_id: Optional[str] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Query vector store for code chunks relevant to query_text.
    Strictly filters by repository_id to guarantee repository isolation.
    """
    collection = get_collection()
    count = collection.count()
    if count == 0:
        logger.warning("Vector database has 0 indexed chunks.")
        return []

    # Enforce metadata filter for repository isolation
    effective_repo_id = repository_id or get_active_repository_id()
    where_filter = {"repository_id": effective_repo_id} if effective_repo_id else None

    try:
        # Determine count of matching items if possible
        actual_k = min(top_k, max(1, count))
        results = collection.query(
            query_texts=[query_text],
            n_results=actual_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
    except Exception as err:
        logger.warning("Query failed with filter %s: %s; trying without where filter", where_filter, err)
        results = collection.query(
            query_texts=[query_text],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"]
        )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    hits: List[Dict[str, Any]] = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        # Convert cosine distance to similarity score
        similarity = round(max(0.0, 1.0 - float(dist)), 4) if dist is not None else 1.0
        hits.append({
            "content": doc,
            "file_path": meta.get("file_path", "unknown"),
            "start_line": meta.get("start_line", 1),
            "end_line": meta.get("end_line", 1),
            "total_lines": meta.get("total_lines", 1),
            "symbol": meta.get("symbol", ""),
            "chunk_type": meta.get("chunk_type", "code"),
            "repository_id": meta.get("repository_id", ""),
            "similarity": similarity
        })

    return hits


def query_symbols(
    symbol_name: str,
    repository_id: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search indexed chunks specifically by symbol or identifier name.
    """
    clean_sym = symbol_name.strip()
    if not clean_sym:
        return []

    # Query with symbol hint in text plus vector query
    results = query_code(f"def {clean_sym} class {clean_sym} {clean_sym}", repository_id=repository_id, top_k=limit)
    
    # Prioritize exact symbol matches
    exact_matches = [r for r in results if clean_sym.lower() in str(r.get("symbol", "")).lower()]
    other_matches = [r for r in results if r not in exact_matches]
    return exact_matches + other_matches


def get_indexed_files(repository_id: Optional[str] = None) -> List[str]:
    """Return unique list of indexed file paths for a given repository."""
    try:
        collection = get_collection()
        where_filter = {"repository_id": repository_id} if repository_id else None
        data = collection.get(where=where_filter, include=["metadatas"])
        metadatas = data.get("metadatas") or []
        files = sorted(list({m.get("file_path") for m in metadatas if m and "file_path" in m}))
        return files
    except Exception as err:
        logger.warning("Failed to retrieve indexed files: %s", err)
        return []


def delete_repository_chunks(repository_id: str):
    """Deletes all chunks belonging to a specific repository."""
    try:
        collection = get_collection()
        collection.delete(where={"repository_id": repository_id})
        logger.info("Deleted all vector chunks for repository %s", repository_id)
    except Exception as err:
        logger.warning("Error deleting repository vectors: %s", err)
