"""Capture a paged Mudae listing by clicking through its pages.

``$wl``, ``$dl``/``$dld`` and ``$adl`` all answer the same way in the channel:
one embed with a ``Page 1 / N`` footer and two arrow buttons, edited in place
as the arrows are clicked. This is the click → wait for the edit → read loop
for any of them; the caller supplies what a page of *its* listing looks like
and how to join the pages.

Paging stops once every page number has been seen rather than when the forward
button goes quiet, because a paginator that wraps around never runs out of
clicks. A listing that loses a page comes back ``ok`` with ``complete`` false
and the missing pages named — never as a shorter list.

Nothing here is sent on its own: it runs when the user asks for a fetch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from mudae.types import MessageKind

# How long to wait for the first reply, and for each page edit after it.
FIRST_REPLY_TIMEOUT = 15.0
PAGE_TIMEOUT = 12.0
# Only exists so a paginator that wraps around cannot spin forever.
MAX_PAGES = 40

# Mudae's own paging arrows, by custom-emoji name.
PAGE_BACK_EMOJI = "wleft"
PAGE_FORWARD_EMOJI = "wright"


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
    def entries(self) -> list[Any]:
        return list(self.data.get("entries") or [])


def page_matcher(parser_id: str, kind: MessageKind) -> Callable[[Any], bool]:
    """A predicate for one listing's pages, however the pipeline labelled them.

    A reply paired with the command just sent comes back as
    ``COMMAND_RESPONSE`` with the parser that ran in ``parser_command``; the
    page edits that follow arrive unpaired, as ``kind``. Matching only one of
    the two either misses page 1 or misses every page after it.
    """

    def matches(parsed: Any) -> bool:
        got = getattr(parsed, "kind", None)
        if got == kind:
            return True
        if got == MessageKind.COMMAND_RESPONSE:
            fields = getattr(parsed, "fields", None) or {}
            return str(fields.get("parser_command") or "").lower() == parser_id
        return False

    return matches


def page_of(parsed: Any) -> int | None:
    fields = getattr(parsed, "fields", None) or {}
    return fields.get("page")


def forward_button(snapshot: Any) -> str | None:
    """Custom id of the page-forward button.

    Matched on the **emoji name** rather than the button ``kind``: Mudae's
    paging custom ids have the same ``<id>p<id>p<id>`` shape as a claim
    button, so ``classify_button_kind`` calls both arrows ``claim``. Position
    is the fallback for a listing whose arrows are named differently — first
    is back, second forward, which is how they read on screen.
    """
    buttons = [
        button
        for button in (getattr(snapshot, "buttons", None) or [])
        if not button.get("disabled")
    ]
    for button in buttons:
        if str(button.get("emoji") or "").strip().lower() == PAGE_FORWARD_EMOJI:
            return str(button.get("custom_id") or "") or None
    # Deliberately *exactly* two: a listing page carries the two arrows and
    # nothing else.
    if len(buttons) == 2:
        return str(buttons[1].get("custom_id") or "") or None
    return None


async def capture_paged_listing(
    actions: Any,
    *,
    command: str,
    label: str,
    is_page: Callable[[Any], bool],
    merge: Callable[[list[dict[str, Any]]], dict[str, Any]],
    log: Callable[[str], None] | None = None,
) -> CaptureResult:
    """Send ``command`` and read every page of the listing it answers with.

    ``label`` names the listing in log lines and reasons (``"Wishlist"``).
    """
    say = log or (lambda _text: None)
    await actions.send_command(command)

    found = await actions.wait_for(
        lambda _s, parsed: is_page(parsed),
        timeout=FIRST_REPLY_TIMEOUT,
    )
    if found is None:
        return CaptureResult(
            ok=False, route="pages", reason=f"Mudae did not answer ${command} in the channel."
        )

    snapshot, parsed = found
    message_id = snapshot.message_id
    parts = [dict(parsed.fields)]
    total = parsed.fields.get("pages")
    seen = {parsed.fields.get("page")} - {None}
    if total:
        say(f"{label} page {parsed.fields.get('page')}/{total}")

    if not total or total <= 1:
        return CaptureResult(ok=True, route="pages", data=merge(parts))

    forward = forward_button(snapshot)
    if forward is None:
        return CaptureResult(
            ok=False,
            route="pages",
            data=merge(parts),
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
                and is_page(parsed)
                and page_of(parsed) not in seen
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
        say(f"{label} page {page}/{total}")
        # The buttons are re-rendered with the edit, so the custom id is read
        # again rather than reused from the first page.
        forward = forward_button(snapshot) or forward

    missing = sorted(set(range(1, int(total) + 1)) - seen)
    return CaptureResult(
        ok=True,
        route="pages",
        data=merge(parts),
        reason="" if not missing else f"Missing page(s) {missing} — the listing is partial.",
    )
