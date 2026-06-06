"""JSON parser — flattens JSON structures into searchable text."""
import json
from pathlib import Path
from app.core.rag.parsers.base import BaseParser


class JsonParser(BaseParser):
    supported_extensions = [".json"]

    def parse(self, file_path: str) -> str:
        data = json.loads(Path(file_path).read_text(encoding="utf-8"))
        return self._flatten(data)

    def _flatten(self, obj, prefix: str = "") -> str:
        """Recursively flatten JSON to key: value text lines."""
        lines = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                lines.append(self._flatten(v, key))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                key = f"{prefix}[{i}]"
                lines.append(self._flatten(v, key))
        else:
            return f"{prefix}: {obj}"
        return "\n".join(lines)
