from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

@pytest.fixture
def temp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield Path(path)
    try:
        os.remove(path)
    except OSError:
        pass
