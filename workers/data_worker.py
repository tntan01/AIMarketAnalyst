from __future__ import annotations

from workers.base_worker import WorkerState


class DataWorker:
    def __init__(self) -> None:
        self.state = WorkerState.IDLE
