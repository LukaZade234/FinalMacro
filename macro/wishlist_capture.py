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

from dataclasses import dataclass, field
from typing import Any, Callable

from mudae.parsers.wishlist import merge_wishlist_pages
from mudae.types import MessageKind

# The command with and without the DM (``s``) flag.
DM_COMMAND = "wlsz+z!"
CHANNEL_COMMAND = "wlz+z!"

# How long to wait for the first reply, and for each part/page after it.
FIRST_REPLY_TIMEOUT = 15.0
# DM parts arrive "with virtually no delay", so a gap this long means Mudae
# has finished rather than that the next part is slow.
DM_PART_TIMEOUT = 6.0
PAGE_TIMEOUT = 12.0
# A listing is 8 pages today; the cap only exists so a paginator that wraps
# around instead of stopping cannot spin forever.
MAX_PAGES = 40


@dataclass
class CaptureResult:
    """What one capture attempt produced."""

    ok: bool = False
    route: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    @property
    def complete(self) -> bool:
        return bool(self.data.get("complete"))

    @property
    def entries(self) -> list[dict[str, Any]]:
        return list(self.data.get("entries") or [])


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
    """Send ``$wlsz+z!`` and collect the DM parts Mudae mails back.

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
    """Send ``$wlz+z!`` and click forward through every page.

    Mudae edits the one message in place, so this is the same click → wait for
    the edit → read it loop the minigames already run on their boards. Paging
    stops once every page number has been seen rather than when the forward
    button goes quiet, because a paginator that wraps around never runs out of
    clicks.
    """
    say = log or (lambda _text: None)
    await actions.send_command(CHANNEL_COMMAND)

    found = await actions.wait_for(
        lambda _s, parsed: _is_wishlist(parsed),
        timeout=FIRST_REPLY_TIMEOUT,
    )
    if found is None:
        return CaptureResult(
            ok=False, route="pages", reason="Mudae did not answer $wlz+z! in the channel."
        )

    snapshot, parsed = found
    message_id = snapshot.message_id
    parts = [dict(parsed.fields)]
    total = parsed.fields.get("pages")
    seen = {parsed.fields.get("page")} - {None}
    say(f"Wishlist page {parsed.fields.get('page')}/{total}")

    if not total or total <= 1:
        merged = merge_wishlist_pages(parts)
        return CaptureResult(ok=True, route="pages", data=merged)

    forward = _forward_button(snapshot)
    if forward is None:
        merged = merge_wishlist_pages(parts)
        return CaptureResult(
            ok=False,
            route="pages",
            data=merged,
            reason="No page-forward button on the listing, so only page 1 could be read.",
        )

    for _ in range(min(int(total), MAX_PAGES)):
        if len(seen) >= int(total):
            break
        clicked = await actions.click_button(message_id, forward)
        if not clicked:
            break
        found = await actions.wait_for(
            lambda s, parsed: (
                s.message_id == message_id
                and _is_wishlist(parsed)
                and _page_of(parsed) not in seen
            ),
            timeout=PAGE_TIMEOUT,
        )
        if found is None:
            break
        snapshot, parsed = found
        parts.append(dict(parsed.fields))
        page = parsed.fields.get("page")
        if page is not None:
            seen.add(page)
        say(f"Wishlist page {page}/{total}")
        # The buttons are re-rendered with the edit, so the custom id is read
        # again rather than reused from the first page.
        forward = _forward_button(snapshot) or forward

    merged = merge_wishlist_pages(parts)
    missing = sorted(set(range(1, int(total) + 1)) - seen)
    return CaptureResult(
        ok=True,
        route="pages",
        data=merged,
        reason="" if not missing else f"Missing page(s) {missing} — the listing is partial.",
    )


# Mudae's own paging arrows, by custom-emoji name.
PAGE_BACK_EMOJI = "wleft"
PAGE_FORWARD_EMOJI = "wright"


def _forward_button(snapshot: Any) -> str | None:
    """Custom id of the page-forward button.

    Matched on the **emoji name** rather than the button ``kind``: Mudae's
    paging custom ids have the same ``<id>p<id>p<id>`` shape as a claim
    button, so ``classify_button_kind`` calls both arrows ``claim``. Position
    is the fallback for a future listing whose arrows are named differently —
    first is back, second forward, which is how they read on screen.
    """
    buttons = [
        button
        for button in (getattr(snapshot, "buttons", None) or [])
        if not button.get("disabled")
    ]
    for button in buttons:
        if str(button.get("emoji") or "").strip().lower() == PAGE_FORWARD_EMOJI:
            return str(button.get("custom_id") or "") or None
    # Fallback for a renamed arrow. Deliberately requires *exactly* two
    # buttons rather than filtering by kind: a listing page carries the two
    # arrows and nothing else, and filtering on kind would discard them both.
    if len(buttons) == 2:
        return str(buttons[1].get("custom_id") or "") or None
    return None


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
