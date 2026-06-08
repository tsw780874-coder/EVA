"""
Split documents into overlapping chunks for embedding.
Uses recursive character-based splitting with configurable size/overlap.
"""
import re


class RecursiveTextSplitter:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = ["\n\n", "\n", "。", ".", " ", ""]

    def split(self, text: str) -> list[str]:
        return self._split_recursive(text, self.separators)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if not separators:
            return [text[i:i + self.chunk_size] for i in range(0, len(text), self.chunk_size - self.chunk_overlap)]

        sep = separators[0]
        remaining = separators[1:]

        if sep == "":
            return self._split_recursive(text, remaining)

        parts = text.split(sep)
        chunks = []
        current = ""

        for part in parts:
            if len(current) + len(part) + len(sep) <= self.chunk_size:
                current = (current + sep + part) if current else part
            else:
                if current:
                    if len(current) > self.chunk_size:
                        chunks.extend(self._split_recursive(current, remaining))
                    else:
                        chunks.append(current)
                current = part

        if current:
            if len(current) > self.chunk_size:
                chunks.extend(self._split_recursive(current, remaining))
            else:
                chunks.append(current)

        return chunks


def chunk_documents(
    documents: list[dict],
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[dict]:
    splitter = RecursiveTextSplitter(chunk_size, chunk_overlap)
    chunks = []

    for doc in documents:
        text_chunks = splitter.split(doc["content"])
        for i, chunk_text in enumerate(text_chunks):
            chunks.append({
                "content": chunk_text,
                "metadata": {
                    **doc.get("metadata", {}),
                    "chunk_index": i,
                    "total_chunks": len(text_chunks),
                },
            })

    return chunks
