"""Conflict resolution using Last-Write-Wins with vector clocks."""

from typing import Dict, Any, Literal
from controller.vector_clock import VectorClock


class ConflictResolver:
    """
    Resolves conflicts using Last-Write-Wins with vector clocks.
    When concurrent writes detected, use timestamp as tiebreaker.
    """

    @staticmethod
    def resolve(local_entity: Dict[str, Any], remote_entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve conflict between local and remote versions.

        Returns:
            {
                'action': 'keep_local' | 'take_remote',
                'winner': entity that was chosen,
                'reason': str
            }
        """
        local_vc = VectorClock.from_json(local_entity.get('vector_clock', '{}'))
        remote_vc = VectorClock.from_json(remote_entity.get('vector_clock', '{}'))

        relationship = local_vc.compare(remote_vc)

        if relationship == 'after':
            return {
                'action': 'keep_local',
                'winner': local_entity,
                'reason': 'Local version causally after remote'
            }
        elif relationship == 'before':
            return {
                'action': 'take_remote',
                'winner': remote_entity,
                'reason': 'Remote version causally after local'
            }
        elif relationship == 'equal':
            return {
                'action': 'keep_local',
                'winner': local_entity,
                'reason': 'Identical versions'
            }
        else:
            local_ts = local_entity.get('created_at', 0)
            remote_ts = remote_entity.get('created_at', 0)

            if remote_ts > local_ts:
                return {
                    'action': 'take_remote',
                    'winner': remote_entity,
                    'reason': 'Concurrent writes - remote has later timestamp (LWW)'
                }
            else:
                return {
                    'action': 'keep_local',
                    'winner': local_entity,
                    'reason': 'Concurrent writes - local has later timestamp (LWW)'
                }
