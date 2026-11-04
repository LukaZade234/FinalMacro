"""Capture a full Mudae wishlist listing, by DM or by paging the channel.

Two routes to the same body (`mudae/parsers/wishlist.py` parses either):

* **DM** — ``$wlsz+z!``. The ``s`` flag makes Mudae mail the whole listing
  instead of posting it, across several messages sent back to back. Faster and
  with nothing to click, but it needs *Settings → Mudae direct messages* on.
* **Pages** — ``$wlz+z!``. Posted in the channel 20 rows at a time with
  ``Page 1 / 8`` and two buttons (back, forward). Always available, but every
  page is a click and a slow edit can cut the listing short.

Both end in :func:`macro.wishlist_capture.CaptureResult`, which reports
``complete`` honestly: a listing that lost a page is returned **as
incomplete** rather than as a short wishlist, because the ``$bw`` maths and
the perk roster are both wrong if rows are silently missing.

Neither command is ever sent on its own — this runs when the user asks for it.
"""

from __future__ import annotations

from typing import Any, Callable

from macro.listing_capture import CaptureResult as _CaptureResult
from macro.listing_capture import (
    PAGE_BACK_EMOJI,
    PAGE_FORWARD_EMOJI,
    capture_paged_listing,
    forward_button,
)
from mudae.parsers.wishlist import merge_wishlist_pages
from mudae.types import MessageKind

# The command with and without the DM (``s``) flag.
#
# ``z+`` / ``z!`` are the sphere flags (spheres and upgrades on each row), and
# on their own they *hide* every character with no spheres invested — so a
# listing taken with only them was silently short by every uninvested wish,
# which also put the wrong neighbours beside each row for the perk-1 wrap.
# ``z-`` brings those rows back.
DM_COMMAND = "wlsz+z!z-"
CHANNEL_COMMAND = "wlz+z!z-"

# How long to wait for the first reply, and for each DM part after it.
FIRST_REPLY_TIMEOUT = 15.0
# DM parts arrive "with virtually no delay", so a gap this long means Mudae
# has finished rather than that the next part is slow.
DM_PART_TIMEOUT = 6.0
# Page timing and the page cap live in `macro/listing_capture.py`.


# Shared with the $dl / $adl captures; re-exported for existing callers.
CaptureResult = _CaptureResult


def _is_wishlist(parsed: Any) -> bool:
    """A listing part, however the pipeline labelled it.

    A reply paired with the command the macro just sent comes back as
    ``COMMAND_RESPONSE`` — that is true of every command, not just this one —
    with the parser that ran recorded in ``parser_command``. Matching on
    ``MessageKind.WISHLIST`` alone therefore misses the *first* reply and
    catches only the later page edits, which is why the capture sent the
    command and then sat there. Same shape as
    ``macro.actions.is_tu_parse_result``.
    """
    kind = getattr(parsed, "kind", None)
    if kind == MessageKind.WISHLIST:
        return True
    if kind == MessageKind.COMMAND_RESPONSE:
        fields = getattr(parsed, "fields", None) or {}
        command = str(
            fields.get("parser_command") or fields.get("command") or ""
        ).lower()
        return command == "wishlist" or bool(fields.get("entries"))
    return False


def _page_of(parsed: Any) -> int | None:
    fields = getattr(parsed, "fields", None) or {}
    return fields.get("page")


async def capture_via_dm(
    actions: Any,
    *,
    log: Callable[[str], None] | None = None,
) -> CaptureResult:
    """Send ``$wlsz+z!z-`` and collect the DM parts Mudae mails back.

    Mudae sends the parts back to back with no page numbers, so the end is
    found two ways: the header says how many characters to expect, and a gap
    longer than :data:`DM_PART_TIMEOUT` means no more are coming.
    """
    say = log or (lambda _text: None)
    await actions.send_command(DM_COMMAND)

    parts: list[dict[str, Any]] = []
    timeout = FIRST_REPLY_TIMEOUT
    while True:
        found = await actions.wait_for(
            lambda _s, parsed: _is_wishlist(parsed),
            timeout=timeout,
        )
        if found is None:
            break
        _snapshot, parsed = found
        parts.append(dict(parsed.fields))
        merged = merge_wishlist_pages(parts)
        say(f"Wishlist DM part {len(parts)} — {len(merged['entries'])} characters")
        if merged["complete"]:
            break
        timeout = DM_PART_TIMEOUT

    if not parts:
        return CaptureResult(
            ok=False,
            route="dm",
            reason=(
                "No DM arrived. Mudae reacts with a mailbox when it sends one and "
                "an ✕ when it cannot — check DMs are open, and that "
                "Settings → Mudae direct messages is on."
            ),
        )

    merged = merge_wishlist_pages(parts)
    return CaptureResult(
        ok=True,
        route="dm",
        data=merged,
        reason="" if merged["complete"] else "The DM stopped before every character arrived.",
    )


async def capture_via_pages(
    actions: Any,
    *,
    log: Callable[[str], None] | None = None,
) -> CaptureResult:
    """Send ``$wlz+z!z-`` and click forward through every page.

    The loop itself is `macro.listing_capture.capture_paged_listing`, shared
    with ``$dl`` and ``$adl``.
    """
    return await capture_paged_listing(
        actions,
        command=CHANNEL_COMMAND,
        label="Wishlist",
        is_page=_is_wishlist,
        merge=merge_wishlist_pages,
        log=log,
    )


# Kept under their old names for callers and tests.
_forward_button = forward_button
__all__ = [
    "CHANNEL_COMMAND",
    "DM_COMMAND",
    "CaptureResult",
    "PAGE_BACK_EMOJI",
    "PAGE_FORWARD_EMOJI",
    "capture_via_dm",
    "capture_via_pages",
    "capture_wishlist",
]


async def capture_wishlist(
    actions: Any,
    *,
    allow_dms: bool,
    log: Callable[[str], None] | None = None,
) -> CaptureResult:
    """Capture by whichever route the DM setting allows.

    With DMs off the paged route is not a fallback but the supported path, so
    it is taken directly rather than after a failed DM attempt.
    """
    if allow_dms:
        return await capture_via_dm(actions, log=log)
    return await capture_via_pages(actions, log=log)
