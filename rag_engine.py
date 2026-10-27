"""RAG Engine for Study Buddy application.

Provides vector storage, embedding generation, semantic retrieval, and
prompt synthesis using ChromaDB and sentence-transformers 'all-MiniLM-L6-v2'.
Integrates with ConfigManager for persistent configuration and FileProcessor
for multi-format document ingestion and chunking.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from config import ConfigManager
from file_processor import FileProcessor

logger = logging.getLogger(__name__)

DEFAULT_PERSIST_DIRECTORY = "~/.studybuddy/vector_stores/"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful study assistant. Answer questions based on the provided context. "
    "If the answer is not in the context, say so clearly."
)


class RAGEngine:
    """RAG engine managing vector collections, retrieval, and prompt augmentation."""

    DEFAULT_SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT

    # Class-level client and embedding function caches for thread-safe reuse
    _client_lock = threading.Lock()
    _client_cache: dict[str, chromadb.ClientAPI] = {}

    _ef_lock = threading.Lock()
    _ef_cache: dict[str, Any] = {}

    def __init__(
        self,
        conversation_id: str,
        persist_directory: str = DEFAULT_PERSIST_DIRECTORY,
        embedding_function: Any | None = None,
    ) -> None:
        """Initialize RAG Engine for a given conversation.

        Args:
            conversation_id: Unique identifier for the conversation session.
            persist_directory: Local filesystem directory for ChromaDB vector storage.
                Defaults to ~/.studybuddy/vector_stores/.
            embedding_function: Optional ChromaDB embedding function override.
        """
        if not conversation_id or not str(conversation_id).strip():
            raise ValueError("conversation_id must be a non-empty string.")

        self.conversation_id = str(conversation_id).strip()
        self.persist_directory = os.path.abspath(os.path.expanduser(persist_directory))
        os.makedirs(self.persist_directory, exist_ok=True)

        self.collection_name = self.sanitize_collection_name(self.conversation_id)
        self._lock = threading.RLock()

        # Initialize or retrieve cached persistent client
        self.client = self._get_client(self.persist_directory)

        # Initialize or retrieve cached sentence-transformers embedding function
        if embedding_function is not None:
            self.embedding_function = embedding_function
        else:
            self.embedding_function = self._get_embedding_function(DEFAULT_EMBEDDING_MODEL)

        self._collection: chromadb.Collection | None = None

    @classmethod
    def _get_client(cls, persist_dir: str) -> chromadb.ClientAPI:
        """Retrieve or initialize a persistent ChromaDB client for the given directory."""
        with cls._client_lock:
            if persist_dir not in cls._client_cache:
                cls._client_cache[persist_dir] = chromadb.PersistentClient(path=persist_dir)
            return cls._client_cache[persist_dir]

    @classmethod
    def _get_embedding_function(cls, model_name: str = DEFAULT_EMBEDDING_MODEL) -> Any:
        """Retrieve or initialize a SentenceTransformerEmbeddingFunction."""
        with cls._ef_lock:
            if model_name not in cls._ef_cache:
                try:
                    cls._ef_cache[model_name] = (
                        embedding_functions.SentenceTransformerEmbeddingFunction(
                            model_name=model_name
                        )
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to initialize sentence-transformers embedding function '{model_name}': {e}. "
                        "Falling back to Chroma DefaultEmbeddingFunction."
                    )
                    cls._ef_cache[model_name] = embedding_functions.DefaultEmbeddingFunction()
            return cls._ef_cache[model_name]

    @staticmethod
    def sanitize_collection_name(conv_id: str) -> str:
        """Sanitize conversation_id into a valid ChromaDB collection name.

        ChromaDB collections require 3-63 characters, must start and end with
        alphanumeric characters, and contain only [a-zA-Z0-9._-].
        """
        name = str(conv_id).strip()
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
        sanitized = re.sub(r"\.\.+", ".", sanitized)
        sanitized = re.sub(r"^[^a-zA-Z0-9]+", "", sanitized)
        sanitized = re.sub(r"[^a-zA-Z0-9]+$", "", sanitized)

        if not sanitized:
            sanitized = "conv_default"
        elif len(sanitized) < 3:
            sanitized = f"conv_{sanitized}"
        elif len(sanitized) > 63:
            sanitized = sanitized[:63].rstrip("._-")
        return sanitized

    def _get_collection(self, create: bool = False) -> chromadb.Collection | None:
        """Retrieve the ChromaDB collection, optionally creating it if missing."""
        with self._lock:
            if self._collection is not None:
                return self._collection

            try:
                if create:
                    self._collection = self.client.get_or_create_collection(
                        name=self.collection_name,
                        embedding_function=self.embedding_function,
                        metadata={"conversation_id": self.conversation_id},
                    )
                else:
                    self._collection = self.client.get_collection(
                        name=self.collection_name,
                        embedding_function=self.embedding_function,
                    )
                return self._collection
            except Exception:
                # Collection does not exist yet or could not be loaded
                return None

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add documents and embeddings to the ChromaDB collection.

        Uses sentence-transformers 'all-MiniLM-L6-v2' for embeddings and stores
        chunks in a persistent ChromaDB collection named after conversation_id.

        Args:
            texts: List of text strings to embed and store.
            metadatas: Optional list of metadata dictionaries corresponding to texts.
        """
        if not texts:
            return

        clean_texts: list[str] = []
        clean_metas: list[dict[str, Any]] = []

        for idx, text in enumerate(texts):
            if not text or not str(text).strip():
                continue
            clean_text = str(text).strip()
            clean_texts.append(clean_text)

            meta: dict[str, Any] = {}
            if metadatas and idx < len(metadatas) and isinstance(metadatas[idx], dict):
                for k, v in metadatas[idx].items():
                    if v is None:
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        meta[str(k)] = v
                    else:
                        meta[str(k)] = str(v)

            meta.setdefault("conversation_id", self.conversation_id)
            clean_metas.append(meta)

        if not clean_texts:
            return

        ids = [
            f"{self.collection_name}_{uuid.uuid4().hex[:8]}_{i}"
            for i in range(len(clean_texts))
        ]

        with self._lock:
            coll = self._get_collection(create=True)
            if coll is None:
                raise RuntimeError(
                    f"Failed to create or access collection '{self.collection_name}'."
                )

            # Insert in chunks of 200 to adhere to SQLite batch thresholds
            batch_size = 200
            for start in range(0, len(clean_texts), batch_size):
                end = start + batch_size
                coll.add(
                    documents=clean_texts[start:end],
                    metadatas=clean_metas[start:end],
                    ids=ids[start:end],
                )

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query the vector store for documents similar to the query text.

        Args:
            query_text: Natural language search string.
            n_results: Maximum number of relevant chunks to retrieve (default: 5).
            where: Optional ChromaDB metadata filter dictionary.

        Returns:
            List of dictionaries formatted as:
            [{"text": str, "metadata": dict, "distance": float}, ...]
        """
        if not query_text or not query_text.strip():
            return []

        with self._lock:
            coll = self._get_collection(create=False)
            if coll is None:
                return []

            try:
                count = coll.count()
            except Exception:
                return []

            if count == 0:
                return []

            actual_n = min(n_results, count)
            if actual_n <= 0:
                return []

            query_kwargs: dict[str, Any] = {
                "query_texts": [query_text],
                "n_results": actual_n,
            }
            if where:
                query_kwargs["where"] = where

            try:
                results = coll.query(**query_kwargs)
            except Exception as e:
                logger.error(f"Error querying collection '{self.collection_name}': {e}")
                return []

            documents = (
                results.get("documents", [[]])[0] if results.get("documents") else []
            )
            metadatas = (
                results.get("metadatas", [[]])[0] if results.get("metadatas") else []
            )
            distances = (
                results.get("distances", [[]])[0] if results.get("distances") else []
            )

            output: list[dict[str, Any]] = []
            for i, doc in enumerate(documents):
                meta = (
                    metadatas[i]
                    if i < len(metadatas) and metadatas[i] is not None
                    else {}
                )
                dist = (
                    distances[i]
                    if i < len(distances) and distances[i] is not None
                    else 0.0
                )
                output.append({
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                })

            return output

    def get_context_for_query(
        self,
        query_text: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> str:
        """Retrieve relevant context chunks and format them into a single string.

        Args:
            query_text: User question or search topic.
            n_results: Number of chunks to retrieve (default: 5).
            where: Optional metadata filter.

        Returns:
            Formatted context string from retrieved documents.
        """
        results = self.query(query_text=query_text, n_results=n_results, where=where)
        if not results:
            return ""

        context_chunks: list[str] = []
        for item in results:
            text = item.get("text", "")
            if isinstance(text, str) and text.strip():
                context_chunks.append(text.strip())

        return "\n\n".join(context_chunks)

    def build_rag_prompt(
        self,
        user_query: str,
        context: str,
        system_prompt: str | None = None,
    ) -> tuple[str, str]:
        """Construct the system prompt and augmented user prompt for RAG inference.

        Args:
            user_query: The question from the user.
            context: Context text retrieved from vector store.
            system_prompt: Optional override for system prompt.

        Returns:
            A tuple of (system_prompt, user_prompt).
        """
        sys_prompt = (
            system_prompt
            if system_prompt is not None and system_prompt.strip()
            else self.DEFAULT_SYSTEM_PROMPT
        )
        user_prompt = f"Context:\n{context}\n\nQuestion: {user_query}"
        return (sys_prompt, user_prompt)

    def delete_collection(self) -> None:
        """Remove the ChromaDB collection for cleanup."""
        with self._lock:
            try:
                self.client.delete_collection(name=self.collection_name)
            except Exception as e:
                logger.debug(
                    f"Collection '{self.collection_name}' already deleted or missing: {e}"
                )
            finally:
                self._collection = None

    def get_document_count(self) -> int:
        """Return the number of documents in the collection."""
        with self._lock:
            coll = self._get_collection(create=False)
            if coll is None:
                return 0
            try:
                return coll.count()
            except Exception:
                return 0

    def add_file(
        self,
        file_path: str | Path,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Process a file using FileProcessor, chunk its content, and store in ChromaDB.

        Args:
            file_path: Absolute or relative path to the file.
            chunk_size: Target size of each chunk in characters (default: 1000).
            chunk_overlap: Overlapping character count (default: 200).
            metadata: Optional base metadata dict attached to each chunk.

        Returns:
            Total number of chunks added.
        """
        processor = FileProcessor()
        text = processor.process_file(file_path)
        chunks = processor.chunk_text(
            text, chunk_size=chunk_size, overlap=chunk_overlap
        )
        if not chunks:
            return 0

        base_meta = dict(metadata or {})
        source_name = Path(file_path).name
        base_meta.setdefault("source", source_name)
        base_meta.setdefault("file_name", source_name)
        base_meta.setdefault("file_path", str(file_path))

        metadatas: list[dict[str, Any]] = []
        for idx in range(len(chunks)):
            chunk_meta = dict(base_meta)
            chunk_meta["chunk_index"] = idx
            chunk_meta["total_chunks"] = len(chunks)
            metadatas.append(chunk_meta)

        self.add_documents(texts=chunks, metadatas=metadatas)
        return len(chunks)
