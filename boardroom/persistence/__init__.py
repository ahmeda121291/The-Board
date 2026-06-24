"""State + metrics persistence. The single source of truth for pitches,
decisions, feature snapshots, calibration, and performance (scope §12).

``get_repository()`` returns a Supabase-backed repo when configured, else an
in-memory one — so the whole system runs in dry-run and tests with no database.
The repository has NO trading power; it is data only.
"""

from boardroom.persistence.repository import (
    DivisionState,
    InMemoryRepository,
    Repository,
    get_repository,
)

__all__ = ["Repository", "InMemoryRepository", "DivisionState", "get_repository"]
