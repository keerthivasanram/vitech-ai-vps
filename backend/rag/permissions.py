"""Permission filter — the access-control seam on retrieval.

A principal (role) is checked against each candidate chunk before it reaches the
answer, so restricted material never leaks into a reply. Today the platform is
single-team, so the DEFAULT is allow-all: with no `RESTRICTED_DOC_CATEGORIES`
configured, every principal sees everything (current behaviour, unchanged).

The wiring is real and in the hot path, so switching on a genuine ACL later is a
config/`principal` change, not a retrofit: set `RESTRICTED_DOC_CATEGORIES` and
give privileged users a role in `PRIVILEGED_ROLES`; everyone else stops seeing
those doc categories.
"""
from __future__ import annotations

from dataclasses import dataclass

from app import config


@dataclass(frozen=True)
class Principal:
    """Who is asking. `role` comes from the request (X-Role header) and defaults
    to a normal engineer. Extend with user_id / customer scoping when a real
    user model exists."""
    role: str = "engineer"

    @property
    def privileged(self) -> bool:
        return self.role in config.PRIVILEGED_ROLES


DEFAULT_PRINCIPAL = Principal()


def allowed(hit: dict, principal: Principal = DEFAULT_PRINCIPAL) -> bool:
    """True if this principal may see this chunk."""
    restricted = config.RESTRICTED_DOC_CATEGORIES
    if not restricted:
        return True                      # single-team default: allow all
    cat = hit.get("doc_category") or hit.get("category")
    if cat in restricted and not principal.privileged:
        return False
    return True


def filter_hits(hits: list[dict], principal: Principal = DEFAULT_PRINCIPAL) -> list[dict]:
    """Drop any chunk the principal is not allowed to see. A no-op until
    `RESTRICTED_DOC_CATEGORIES` is set."""
    if not config.RESTRICTED_DOC_CATEGORIES:
        return hits
    return [h for h in hits if allowed(h, principal)]
