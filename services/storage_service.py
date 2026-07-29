from __future__ import annotations

import json
import gzip
from pathlib import Path
from typing import Any


class JsonStorage:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default
        if self.path.suffix == ".gz":
            with gzip.open(self.path, "rt", encoding="utf-8") as handle:
                return json.load(handle)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: Any, *, indent: int | None = 2) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.suffix == ".gz":
            with gzip.open(self.path, "wt", encoding="utf-8") as handle:
                json.dump(data, handle, indent=indent, ensure_ascii=False)
            return
        self.path.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")
