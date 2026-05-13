"""
Examples of complexity reduction techniques.
"""

from dataclasses import dataclass
from typing import List, Dict, Any
from abc import ABC, abstractmethod


@dataclass
class ConsolidatedDataNode:
    """Consolidated data node with reduced complexity."""

    id: str
    type: str
    data: Dict[str, Any]
    connections: List[str] = None

    def __post_init__(self):
        if self.connections is None:
            self.connections = []

    def add_connection(self, node_id: str):
        """Add connection to another node."""
        if node_id not in self.connections:
            self.connections.append(node_id)

    def remove_connection(self, node_id: str):
        """Remove connection to another node."""
        if node_id in self.connections:
            self.connections.remove(node_id)


class DataProcessor(ABC):
    """Abstract base class for data processors."""

    @abstractmethod
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data."""
        pass


class ConsolidatedProcessor(DataProcessor):
    """Consolidated processor with reduced complexity."""

    def __init__(self):
        self._processors = {}

    def register_processor(self, data_type: str, processor: DataProcessor):
        """Register processor for data type."""
        self._processors[data_type] = processor

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Process data using appropriate processor."""
        data_type = data.get("type", "unknown")
        processor = self._processors.get(data_type)

        if processor:
            return processor.process(data)
        else:
            return self._default_process(data)

    def _default_process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Default processing logic."""
        return {"processed": True, "original_type": data.get("type"), "data": data}


# Usage example
def create_consolidated_system():
    """Create consolidated data processing system."""

    processor = ConsolidatedProcessor()

    # Create consolidated nodes
    nodes = [
        ConsolidatedDataNode("node1", "input", {"value": 42}),
        ConsolidatedDataNode("node2", "process", {"value": 84}),
        ConsolidatedDataNode("node3", "output", {"value": 126}),
    ]

    # Connect nodes
    nodes[0].add_connection("node2")
    nodes[1].add_connection("node3")

    return processor, nodes
