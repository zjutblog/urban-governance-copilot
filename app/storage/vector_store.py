"""向量存储：chromadb 持久化封装。"""
from __future__ import annotations

import os
from typing import Any, Optional

import chromadb

from app.domain.document import Document

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "chroma",
)


class VectorStore:
    def __init__(self, collection_name: str = "governance_cases"):
        os.makedirs(_DB_PATH, exist_ok=True)
        self.client = chromadb.PersistentClient(path=_DB_PATH)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def count(self) -> int:
        return self.collection.count()

    def add_documents(self, documents: list[Document], embeddings: Any):
        self.collection.upsert(
            ids=[d.doc_id for d in documents],
            documents=[d.content for d in documents],
            embeddings=embeddings.tolist(),
            metadatas=[d.metadata for d in documents],
        )

    def search(self, query_embedding: Any, top_k: int = 5, where: Optional[dict] = None):
        return self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
