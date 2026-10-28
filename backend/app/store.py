import asyncio
from dataclasses import dataclass, field

from app.models import SearchEvent, SearchResult


@dataclass
class SearchJob:
    result: SearchResult
    events: list[SearchEvent] = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)

    async def emit(self, stage: str, message: str):
        if len(self.events) >= 100 and stage != "done":
            raise ValueError("Too many agent events")
        async with self.changed:
            self.events.append(SearchEvent(
                sequence=len(self.events) + 1, stage=stage,
                message=message, status=self.result.status,
            ))
            self.changed.notify_all()


class MemorySearchStore:
    """Один процесс, ограниченная память; завершённые записи вытесняются первыми."""
    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self.jobs: dict[str, SearchJob] = {}

    def add(self, job: SearchJob):
        if len(self.jobs) >= self.capacity:
            completed = next((key for key, value in self.jobs.items() if value.result.status != "processing"), None)
            if completed is None:
                raise OverflowError("Все слоты поиска заняты")
            del self.jobs[completed]
        self.jobs[job.result.id] = job
