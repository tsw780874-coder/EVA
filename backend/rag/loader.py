"""
Load documents from various sources for RAG ingestion.
Supports JSON, CSV, TXT files and directory traversal.
"""
import json
import csv
from pathlib import Path


def load_json(file_path: str) -> list[dict]:
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else [data]


def load_csv(file_path: str, content_column: str = "content") -> list[dict]:
    rows = []
    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({"content": row.get(content_column, ""), "metadata": row})
    return rows


def load_text(file_path: str) -> list[dict]:
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    return [{"content": content, "metadata": {"source": file_path}}]


def load_directory(directory: str, glob_pattern: str = "*.txt") -> list[dict]:
    docs = []
    for path in Path(directory).glob(glob_pattern):
        ext = path.suffix.lower()
        if ext == ".json":
            docs.extend(load_json(str(path)))
        elif ext == ".csv":
            docs.extend(load_csv(str(path)))
        else:
            docs.extend(load_text(str(path)))
    return docs
