from abc import ABC, abstractmethod
from typing import Any


class JobCollector(ABC):

    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """Collect and return normalized job data."""
        raise NotImplementedError