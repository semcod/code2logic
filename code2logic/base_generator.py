from typing import Protocol, Any
from .models import ProjectInfo


class ProjectGenerator(Protocol):
    def generate(self, project: ProjectInfo, **kwargs: Any) -> Any: ...
