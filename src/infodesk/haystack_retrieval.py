"""Lexical BM25 retrieval over already-captured live document versions.

Haystack ranks passages only. It does not write the SQLite ledger, approve
drafts, or call a model. Captures are flat paragraph windows, so this module
does not invent hierarchy metadata or use AutoMergingRetriever.
"""
import os

# Keep CI and local tests offline; BM25 does not need provider credentials.
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")

from haystack import Document, Pipeline
from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
from haystack.document_stores.in_memory import InMemoryDocumentStore

# GUESS: six passages bound CPU-model context. Relevance is not calibrated.
PASSAGE_LIMIT = 6


def documents_from_captures(rows):
    """Map ledger chunks to Haystack Documents. Title is searchable; body stays exact."""
    documents = []
    for row in rows:
        title = row["title"] or ""
        body = row["body"]
        content = f"{title}\n{body}".strip() if title and title != body else body
        documents.append(Document(
            id=str(row["chunk_id"]),
            content=content,
            meta={
                "chunk_id": row["chunk_id"],
                "body": body,
                "version_id": row["version_id"],
                "document_id": row["document_id"],
                "source_id": row["source_id"],
                "url": row["url"],
                "title": row["title"],
                "received_at": row["received_at"],
                "published_at": row["published_at"],
                "text_hash": row["text_hash"],
                "coverage": row["coverage"],
            },
        ))
    return documents


def retrieve_passages(question, rows, top_k=PASSAGE_LIMIT):
    """Run a Haystack 2.x BM25 Pipeline and return the existing passage dicts."""
    if not rows:
        return []
    store = InMemoryDocumentStore()
    store.write_documents(documents_from_captures(rows))
    pipeline = Pipeline()
    pipeline.add_component(
        "retriever",
        InMemoryBM25Retriever(document_store=store, top_k=top_k),
    )
    result = pipeline.run({"retriever": {"query": question}})
    passages = []
    for document in result["retriever"]["documents"]:
        if document.score is None or document.score <= 0:
            continue
        meta = document.meta
        passages.append({
            "chunk_id": meta["chunk_id"],
            "body": meta["body"],
            "version_id": meta["version_id"],
            "document_id": meta["document_id"],
            "source_id": meta["source_id"],
            "url": meta["url"],
            "title": meta["title"],
            "received_at": meta["received_at"],
            "published_at": meta["published_at"],
            "text_hash": meta["text_hash"],
            "coverage": meta["coverage"],
            "rank": document.score,
        })
    return passages
