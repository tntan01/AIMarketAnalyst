from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
