"""Vector clock implementation for causality tracking and conflict resolution."""

import json
from typing import Dict, Literal


class VectorClock:
    """
    Vector clock for causality tracking and conflict resolution.
    Format: {node_id: counter}
    """

    def __init__(self, clock: Dict[str, int] = None):
        self.clock = clock or {}

    def increment(self, node_id: str) -> 'VectorClock':
        """Increment this node's counter"""
        new_clock = self.clock.copy()
        new_clock[node_id] = new_clock.get(node_id, 0) + 1
        return VectorClock(new_clock)

    def merge(self, other: 'VectorClock') -> 'VectorClock':
        """Merge with another vector clock (max of each element)"""
        merged = {}
        all_nodes = set(self.clock.keys()) | set(other.clock.keys())
        for node in all_nodes:
            merged[node] = max(self.clock.get(node, 0), other.clock.get(node, 0))
        return VectorClock(merged)

    def compare(self, other: 'VectorClock') -> Literal['before', 'after', 'concurrent', 'equal']:
        """
        Compare causality relationship.
        Returns: 'before', 'after', 'concurrent', 'equal'
        """
        self_greater = False
        other_greater = False

        all_nodes = set(self.clock.keys()) | set(other.clock.keys())
        for node in all_nodes:
            self_val = self.clock.get(node, 0)
            other_val = other.clock.get(node, 0)

            if self_val > other_val:
                self_greater = True
            elif other_val > self_val:
                other_greater = True

        if self_greater and not other_greater:
            return 'after'
        elif other_greater and not self_greater:
            return 'before'
        elif not self_greater and not other_greater:
            return 'equal'
        else:
            return 'concurrent'

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.clock)

    @staticmethod
    def from_json(json_str: str) -> 'VectorClock':
        """Deserialize from JSON string"""
        if not json_str or json_str == '{}':
            return VectorClock({})
        return VectorClock(json.loads(json_str))

    def __repr__(self):
        return f"VectorClock({self.clock})"

    def __eq__(self, other):
        if not isinstance(other, VectorClock):
            return False
        return self.clock == other.clock
