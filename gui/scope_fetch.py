"""How a page's fetch button reaches the scope its bar is pointed at.

Every sheet the app parses — ``$settings``, ``$bonus``, ``$shop``, ``$wl`` —
describes exactly one ``(account, server)`` pair, and is only obtainable by
sending a command *as that account, in that server*. So a fetch button on a
page whose scope bar has been detached from the Run target has a problem the
old Servers-page buttons dodged by refusing: the sheet you are looking at and
the connection you have are for different pairs.

The answer is a **temporary connection**: go where the scope points, send the
one command, and put the session back exactly as it was. This module holds the
decision half of that — which of the four routes applies — as plain data, so
the rules can be tested without a Discord gateway anywhere near them.

The routes, in order of how much they disturb:

``send``
    The live session is already on this pair. Nothing to move.
``hop``
    A session exists on a different pair. Move the monitor over, send, move it
    back. The same manoeuvre ``$p``/``$daily`` already performs every hour
    (``AppBridge._run_account_dailies``), and it shares that lock so the two
    can never interleave.
``temporary``
    No session at all. Stand one up for the length of the command, then take
    it down. It is deliberately *not* a Run session: no engine, no roll cycle,
    no daily loops, and nothing written to the run logs.
``blocked``
    The macro is in the middle of something else, or the scope is not a scope.
    A fetch is never worth interrupting live work for, so it does not go
    through — and it says why rather than failing silently.
"""

from __future__ import annotations

from dataclasses import dataclass

# The commands a scope fetch may send, mapped to what the button says. Kept as
# an allowlist rather than passing a command straight through from QML: this
# path can connect as an arbitrary account, so what it is allowed to send is
# worth being explicit about.
SCOPE_FETCH_COMMANDS: dict[str, str] = {
    "settings": "$settings",
    "bonus": "$bonus",
    "shop": "$shop",
    "wishlist": "$wl",
}

# How long to wait for a sheet after sending its command. Sheets are one big
# embed rather than a paged listing, so a reply that has not arrived by now is
# a rate limit or an outage, not a slow one.
SCOPE_FETCH_TIMEOUT = 20.0

ROUTE_SEND = "send"
ROUTE_HOP = "hop"
ROUTE_TEMPORARY = "temporary"
ROUTE_BLOCKED = "blocked"


@dataclass(frozen=True)
class ScopeFetchPlan:
    """What a fetch on one scope would have to do to get there."""

    route: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.route != ROUTE_BLOCKED

    @property
    def moves_the_connection(self) -> bool:
        """Whether the session has to be put back afterwards."""
        return self.route in (ROUTE_HOP, ROUTE_TEMPORARY)


def plan_scope_fetch(
    *,
    command: str,
    account_id: str,
    channel_profile_id: str,
    has_session: bool,
    live_account_id: str,
    live_channel_profile_id: str,
    busy_reason: str = "",
) -> ScopeFetchPlan:
    """Decide how — or whether — to run ``command`` on the given pair.

    ``busy_reason`` is the caller's own answer to "is the macro mid-anything",
    already phrased for the status line; a non-empty one always wins, because
    no sheet is worth stealing the gateway from a running session.
    """
    if command not in SCOPE_FETCH_COMMANDS:
        return ScopeFetchPlan(ROUTE_BLOCKED, f"Unknown fetch: {command}")
    # Half a scope is not a scope: a sheet fetched without both halves has
    # nowhere honest to be filed.
    if not account_id or not channel_profile_id:
        return ScopeFetchPlan(ROUTE_BLOCKED, "Pick an account and a server first")
    if busy_reason:
        return ScopeFetchPlan(ROUTE_BLOCKED, busy_reason)
    if not has_session:
        return ScopeFetchPlan(ROUTE_TEMPORARY)
    if (
        account_id == live_account_id
        and channel_profile_id == live_channel_profile_id
    ):
        return ScopeFetchPlan(ROUTE_SEND)
    return ScopeFetchPlan(ROUTE_HOP)
