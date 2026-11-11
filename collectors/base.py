from abc import ABC, abstractmethod
from typing import Any, Dict, List, NotRequired, TypedDict


class Item(TypedDict):
    title: str
    source: str
    raw_text: str
    timestamp: str
    url: NotRequired[str]
    category: NotRequired[str]
    data: NotRequired[Dict[str, Any]]


class BaseCollector(ABC):
    """Collectors must never raise: failures are logged and yield fewer items."""

    @abstractmethod
    def collect(self) -> List[Item]:
        raise NotImplementedError
