"""The data layer: pull REAL fresh market data, freshness/sanity-check it, and
hash it. If data is stale, missing, or insane, the division abstains — "no fresh
data, no trade" is a hard rule (scope §5).
"""

from boardroom.data.snapshot import (
    Bars,
    SanityError,
    build_snapshot,
    content_hash,
    sanity_check,
)

__all__ = ["Bars", "SanityError", "build_snapshot", "content_hash", "sanity_check"]
