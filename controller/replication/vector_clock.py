"""
Vector clock implementation for tracking causality in distributed operations.

Vector clocks enable detection of causal relationships (happens-before) and
concurrent events across multiple controller instances.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict
import json


@dataclass
class VectorClock:
    """
    Vector clock for tracking causality across distributed controllers.

    Each controller maintains a counter that increments on local operations.
    Vector clocks are merged when receiving remote operations to track causality.
    """

    clocks: Dict[str, int] = field(default_factory=dict)

    def increment(self, controller_id: str) -> None:
        """
        Increment the clock for a specific controller.

        Args:
            controller_id: UUID of the controller whose clock to increment
        """
        self.clocks[controller_id] = self.clocks.get(controller_id, 0) + 1

    def merge(self, other: VectorClock) -> None:
        """
        Merge another vector clock into this one (take max for each controller).

        Args:
            other: The vector clock to merge
        """
        for controller_id, seq in other.clocks.items():
            self.clocks[controller_id] = max(
                self.clocks.get(controller_id, 0),
                seq
            )

    def happens_before(self, other: VectorClock) -> bool:
        """
        Check if this vector clock causally precedes another.

        Returns True if self happened before other (self <= other and self != other).

        Args:
            other: The vector clock to compare against

        Returns:
            True if self causally precedes other, False otherwise
        """
        if self.clocks == other.clocks:
            return False

        for controller_id, seq in self.clocks.items():
            if seq > other.clocks.get(controller_id, 0):
                return False

        return True

    def is_concurrent(self, other: VectorClock) -> bool:
        """
        Check if this vector clock is concurrent with another.

        Two clocks are concurrent if neither causally precedes the other.

        Args:
            other: The vector clock to compare against

        Returns:
            True if the clocks are concurrent, False otherwise
        """
        return not self.happens_before(other) and not other.happens_before(self)

    def to_json(self) -> str:
        """
        Serialize vector clock to JSON string.

        Returns:
            JSON string representation
        """
        return json.dumps(self.clocks)

    @classmethod
    def from_json(cls, json_str: str) -> VectorClock:
        """
        Deserialize vector clock from JSON string.

        Args:
            json_str: JSON string representation

        Returns:
            VectorClock instance
        """
        clocks = json.loads(json_str)
        return cls(clocks=clocks)

    def copy(self) -> VectorClock:
        """
        Create a deep copy of this vector clock.

        Returns:
            A new VectorClock instance with the same values
        """
        return VectorClock(clocks=dict(self.clocks))

    def __eq__(self, other: object) -> bool:
        """
        Check equality with another vector clock.

        Args:
            other: Object to compare with

        Returns:
            True if clocks are equal, False otherwise
        """
        if not isinstance(other, VectorClock):
            return False
        return self.clocks == other.clocks

    def __repr__(self) -> str:
        """
        String representation of vector clock.

        Returns:
            String representation showing all controller:sequence pairs
        """
        return f"VectorClock({self.clocks})"
