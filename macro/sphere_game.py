"""Play the Mudae ``$oh`` sphere minigame.

The ``$oh`` command posts a 5x5 grid of clickable sphere buttons. Some are
already revealed (a colored sphere), the rest are face-down (``spU``). Clicking
a sphere claims its value; blue/teal spheres additionally unveil more hidden
buttons (3 and 1 respectively). The grid lives in a single message that Mudae
*edits* after every click, so the engine must wait for each edit to land before
deciding its next move.

Purple spheres (``spP``) are **free**: they do not consume the click allowance.
Dark spheres (``spD``) use a paid click and become one other colour; the
grid stays dark. Mudae's tracker writes ``spD turns into spP`` (or another
colour) and may add a ``(Free)`` payout line for the result — that is still
the same paid dark click, not a free purple press. Light spheres (``spL``)
split into other colours; the tracker writes ``spL breaks down into spB + …``.
Clicking a face-down cell can grant a bonus ``$oc`` use — the reward tracker
shows ``spU`` instead of a colour.

Strategy (per the user's spec):
    * always take free purple (``spP``) when available;
    * never click an already-revealed blue (``spB``) or teal (``spT``) — they
      are worth so little that a face-down click is preferable;
    * otherwise click the highest-value revealed paid sphere available;
    * if no worthwhile revealed sphere remains, click a random face-down button.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Callable
from typing import Any

from mudae.macro_activity import enter_macro_activity, exit_macro_activity
from mudae.constants import (
    SPHERE_EMOJI_NAME_PATTERN,
    SPHERE_FREE_EMOJIS,
    SPHERE_HIDDEN_EMOJI,
    SPHERE_REVEAL_EMOJIS,
    SPHERE_VALUE_RANK,
    canonical_sphere_emoji,
)
from mudae.parsers.ohu import parse_oh_invested_bonus

from macro.minigame_util import (
    empty_minigame_result,
    log_minigame_exhausted,
    minigame_command,
    snapshot_is_minigame_exhausted,
    wait_for_grid_or_exhausted,
)
from macro.minigame_board import (
    TRANSFORM_EMOJIS,
    board_emojis,
    build_session,
    cell_index,
    classify_oh_click,
    make_click,
    normalize_sphere_emoji,
)


# $oh picks between revealed spheres by what they actually pay, not by the
# ordinal SPHERE_VALUE_RANK. That rank orders spD(5) < spL(6) < spO(7), but
# dark pays ~104 SP against orange's 90 and light's 76, so ranking made the
# greedy take a revealed orange over a revealed dark. Dark and light have no
# SPHERE_BASE_SP entry (they transform on click); these are their measured
# means over the logged games. SPHERE_VALUE_RANK is shared with $oc/$oq and
# is deliberately left alone.
_OH_CLICK_VALUE: dict[str, float] = {
    "spB": 10.0,
    "spT": 20.0,
    "spG": 35.0,
    "spY": 55.0,
    "spL": 76.0,
    "spO": 90.0,
    "spD": 104.0,
    "spR": 150.0,
    "sp": 150.0,
    "spW": 500.0,
    "spP": 5.0,
}


def oh_click_value(emoji: str) -> float:
    """SP a revealed sphere pays if clicked now (dark/light at their means)."""
    return _OH_CLICK_VALUE.get(canonical_sphere_emoji(emoji), 0.0)


def sphere_value_rank(emoji: str) -> int:
    """Paid-click value for a revealed sphere emoji (higher = click first)."""
    return SPHERE_VALUE_RANK.get(canonical_sphere_emoji(emoji), 0)


def _button_sort_key(buttons: list[dict[str, Any]], button: dict[str, Any]) -> tuple[float, int]:
    value = oh_click_value(_emoji(button))
    for index, candidate in enumerate(buttons):
        if candidate.get("custom_id") == button.get("custom_id"):
            return value, -index
    return value, 0

# "You can click **5** times on the buttons below ..."
_CLICKS_ALLOWED_RE = re.compile(r"click\s*\*{0,2}(\d+)\*{0,2}\s*times", re.IGNORECASE)
# Custom <:spY:id> or bare :spY: (copy-paste from the Discord client).
_SPHERE_CUSTOM_RE = re.compile(r"<:([^:>]+):\d+>")
_SPHERE_BARE_RE = re.compile(rf"(?<!<):({SPHERE_EMOJI_NAME_PATTERN}):")
_TURNS_INTO_RE = re.compile(
    rf"(?:<:(?P<src1>[^:>]+):\d+>|:(?P<src2>{SPHERE_EMOJI_NAME_PATTERN}):)"
    r"\s*turns\s+into\s*"
    rf"(?:<:(?P<dst1>[^:>]+):\d+>|:(?P<dst2>{SPHERE_EMOJI_NAME_PATTERN}):)",
    re.IGNORECASE,
)
_BREAKS_DOWN_RE = re.compile(r"breaks\s+down\s+into", re.IGNORECASE)
# ":spL: breaks down into :spB: + :spT:  => +156" / "=> **+156**".
_ARROW_AMOUNT_RE = re.compile(
    r"=>\s*(?:\*\*)?\+\s*(?:\*\*)?(?P<amount>[\d,]+)",
)
# "<:spP:id> (Free) **+46**", "<:spY:id> **+59**", ":spO: +216".
_PAYOUT_RE = re.compile(
    rf"(?:<:(?P<emoji1>[^:>]+):\d+>|:(?P<emoji2>{SPHERE_EMOJI_NAME_PATTERN}):)"
    r"(?:\s*\([^)]*\))?"
    r"\s*(?:\*\*)?\+\s*(?:\*\*)?(?P<amount>[\d,]+)",
)
_DEFAULT_CLICKS_ALLOWED = 5
# Minimum sphere buttons that distinguishes the $oh grid from a roll's lone
# sphere react button.
_MIN_GRID_BUTTONS = 10
# Pause after the grid message lands before the first button click — clicking
# immediately often fails to register with Mudae.
FIRST_CLICK_DELAY_SEC = 1.0


def _emoji(button: dict[str, Any]) -> str:
    raw = (button.get("emoji") or "").strip()
    if not raw:
        return ""
    return normalize_sphere_emoji(raw)


def _sphere_buttons(buttons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in buttons if (b.get("kind") == "sphere") or _emoji(b).startswith("sp")]


def _is_clickable(button: dict[str, Any]) -> bool:
    return bool(button.get("custom_id")) and not button.get("disabled")


def is_oh_grid_message(snapshot: Any) -> bool:
    """True when ``snapshot`` is the ``$oh`` grid (initial post or an edit)."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    content = (getattr(snapshot, "content", "") or "").lower()
    spheres = _sphere_buttons(getattr(snapshot, "buttons", []) or [])
    if len(spheres) < _MIN_GRID_BUTTONS:
        return False
    if "red sphere" in content and "find" in content:
        return False
    if "purple" in content and "find" in content:
        return False
    return "buttons below" in content or "spheres buttons" in content


def is_oh_reward_message(snapshot: Any) -> bool:
    """True for the side message that lists per-click sphere payouts."""
    if not getattr(snapshot, "is_mudae", False):
        return False
    if getattr(snapshot, "buttons", None):
        return False
    content = getattr(snapshot, "content", "") or ""
    has_sphere = "<:sp" in content or bool(_SPHERE_BARE_RE.search(content))
    if not has_sphere:
        return False
    lower = content.lower()
    return "+" in content or "turns into" in lower or "breaks down into" in lower


def parse_clicks_allowed(content: str) -> int:
    match = _CLICKS_ALLOWED_RE.search(content or "")
    if not match:
        return _DEFAULT_CLICKS_ALLOWED
    return max(1, int(match.group(1)))


def _sphere_emojis_in(text: str) -> list[str]:
    custom = _SPHERE_CUSTOM_RE.findall(text or "")
    if custom:
        return custom
    return _SPHERE_BARE_RE.findall(text or "")


def _breakdown_fragments(line: str) -> list[str]:
    """Colours after ``breaks down into``, ignoring the ``=> +N`` chat total."""
    parts = _BREAKS_DOWN_RE.split(line, maxsplit=1)
    if len(parts) < 2:
        return []
    tail = parts[1].split("=>", 1)[0]
    return [emoji for emoji in _sphere_emojis_in(tail) if emoji]


def _reward_events(content: str) -> list[tuple[str, str]]:
    """Ordered tracker events: ``("transform", dest)`` or ``("payout", emoji)``."""
    events: list[tuple[str, str]] = []
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if "turns into" in lower:
            match = _TURNS_INTO_RE.search(line)
            dest = ""
            if match:
                dest = (match.group("dst1") or match.group("dst2") or "").strip()
            if not dest:
                emojis = _sphere_emojis_in(line)
                if len(emojis) >= 2:
                    dest = emojis[-1]
            if dest:
                events.append(("transform", dest))
            continue
        if "breaks down into" in lower:
            for emoji in _breakdown_fragments(line):
                events.append(("payout", emoji))
            continue
        match = _PAYOUT_RE.search(line)
        if match:
            emoji = (match.group("emoji1") or match.group("emoji2") or "").strip()
            if emoji:
                events.append(("payout", emoji))
    return events


def total_reward_from_content(content: str) -> int:
    """Sum chat ``+N`` sphere lines, skipping hidden ``spU`` ($oc grant, not SP)."""
    total = 0
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if "turns into" in lower:
            continue
        if "breaks down into" in lower:
            match = _ARROW_AMOUNT_RE.search(line)
            if match:
                total += int((match.group("amount") or "0").replace(",", ""))
            continue
        match = _PAYOUT_RE.search(line)
        if not match:
            continue
        emoji = (match.group("emoji1") or match.group("emoji2") or "").strip()
        if emoji == SPHERE_HIDDEN_EMOJI:
            continue
        total += int((match.group("amount") or "0").replace(",", ""))
    return total


def reward_line_types(content: str) -> list[str]:
    """Emoji names from each payout line in the reward tracker message."""
    return [emoji for kind, emoji in _reward_events(content) if kind == "payout"]


def reward_outcome_types(content: str) -> list[str]:
    """Payout colours plus ``turns into`` destinations and light fragments."""
    return [emoji for _kind, emoji in _reward_events(content)]


def parse_reward_clicks(content: str) -> list[dict[str, Any]]:
    """Group tracker lines into one click each, matching Mudae's list.

    Light ``breaks down into`` is one click. ``turns into`` plus the following
    payout of that colour is one dark click, not a second press.
    """
    clicks: list[dict[str, Any]] = []
    skip_payout = ""
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if "turns into" in lower:
            match = _TURNS_INTO_RE.search(line)
            dest = ""
            if match:
                dest = (match.group("dst1") or match.group("dst2") or "").strip()
            if not dest:
                emojis = _sphere_emojis_in(line)
                if len(emojis) >= 2:
                    dest = emojis[-1]
            dest = normalize_sphere_emoji(dest) if dest else ""
            clicks.append(
                {
                    "emoji": "spD",
                    "resolved": [dest] if dest else [],
                    "paid": True,
                    "oc_bonus": 0,
                }
            )
            skip_payout = dest
            continue
        if "breaks down into" in lower:
            fragments = [
                normalize_sphere_emoji(item) for item in _breakdown_fragments(line)
            ]
            clicks.append(
                {
                    "emoji": "spL",
                    "resolved": [item for item in fragments if item],
                    "paid": True,
                    "oc_bonus": 0,
                }
            )
            skip_payout = ""
            continue
        match = _PAYOUT_RE.search(line)
        if not match:
            continue
        emoji = normalize_sphere_emoji(
            (match.group("emoji1") or match.group("emoji2") or "").strip()
        )
        if skip_payout and emoji == skip_payout:
            skip_payout = ""
            continue
        skip_payout = ""
        if emoji == SPHERE_HIDDEN_EMOJI:
            clicks.append(
                {"emoji": "spU", "resolved": [], "paid": True, "oc_bonus": 1}
            )
            continue
        paid = emoji not in SPHERE_FREE_EMOJIS and "(free)" not in lower
        clicks.append(
            {"emoji": emoji, "resolved": [], "paid": paid, "oc_bonus": 0}
        )
    return clicks


def _click_outcome_note(classified: dict[str, Any], kind: str) -> str:
    """Activity-log fragment: identity plus what light/dark / hidden became."""
    oc_grant = int(classified.get("oc_bonus") or 0)
    if oc_grant:
        return f"{kind} · +{oc_grant} $oc"
    identity = str(classified.get("emoji") or "")
    resolved = [str(item) for item in (classified.get("resolved") or []) if item]
    if identity in TRANSFORM_EMOJIS and resolved:
        return f"{kind} → {'+'.join(resolved)}"
    if kind == "hidden" and identity and identity not in {SPHERE_HIDDEN_EMOJI, ""}:
        return f"hidden → {identity}"
    return kind


def new_reward_line_types(before: str, after: str) -> list[str]:
    """Payout emoji names added to the reward tracker since ``before``."""
    prev = reward_line_types(before)
    curr = reward_line_types(after)
    if len(curr) <= len(prev):
        return []
    return curr[len(prev):]


def new_reward_outcome_types(before: str, after: str) -> list[str]:
    """New payouts and transform destinations since ``before``."""
    prev = reward_outcome_types(before)
    curr = reward_outcome_types(after)
    if len(curr) <= len(prev):
        return []
    return curr[len(prev):]


def reward_has_entries(content: str) -> bool:
    if not content or "rewards appear here" in content.lower():
        return False
    return bool(_reward_events(content))


def disabled_count(buttons: list[dict[str, Any]]) -> int:
    return sum(1 for b in buttons if b.get("disabled"))


def grid_signature(buttons: list[dict[str, Any]]) -> tuple[tuple[str, str, bool, str], ...]:
    """Stable fingerprint of the grid for detecting Mudae edits."""
    sig: list[tuple[str, str, bool, str]] = []
    for button in _sphere_buttons(buttons):
        sig.append((
            str(button.get("custom_id") or ""),
            _emoji(button),
            bool(button.get("disabled")),
            str(button.get("style") or ""),
        ))
    return tuple(sig)


def is_oh_game_over(buttons: list[dict[str, Any]]) -> bool:
    """True when Mudae has ended the session (no sphere buttons left to press)."""
    spheres = _sphere_buttons(buttons)
    if len(spheres) < _MIN_GRID_BUTTONS:
        return True
    return not any(_is_clickable(button) for button in spheres)


def _board_has_hidden(buttons: list[dict[str, Any]]) -> bool:
    for button in _sphere_buttons(buttons)[:25]:
        emoji = _emoji(button)
        if not emoji or emoji == SPHERE_HIDDEN_EMOJI:
            return True
    return False


async def wait_for_final_grid(
    actions: Any,
    *,
    grid_id: int,
    buttons: list[dict[str, Any]],
    is_grid_message: Callable[[Any], bool],
    get_reward_content: Callable[[], str],
    set_reward_content: Callable[[str], None],
    timeout: float = 2.5,
) -> list[dict[str, Any]]:
    """Wait for the post-game reveal that fills remaining hidden cells."""
    if timeout <= 0 or not _board_has_hidden(buttons):
        return buttons
    before_sig = grid_signature(buttons)

    def predicate(snapshot: Any, _parsed: Any) -> bool:
        if is_oh_reward_message(snapshot):
            content = getattr(snapshot, "content", "") or ""
            if reward_has_entries(content):
                set_reward_content(content)
        if getattr(snapshot, "message_id", None) != grid_id:
            return False
        if not is_grid_message(snapshot):
            return False
        return grid_signature(getattr(snapshot, "buttons", []) or []) != before_sig

    result = await actions.wait_for(predicate, timeout=timeout)
    if result is None:
        return buttons
    return list(result[0].buttons)


def _disable_button(buttons: list[dict[str, Any]], custom_id: str) -> list[dict[str, Any]]:
    """Optimistic grid state when Mudae updates the reward tracker first."""
    out: list[dict[str, Any]] = []
    for button in buttons:
        copy = dict(button)
        if copy.get("custom_id") == custom_id:
            copy["disabled"] = True
        out.append(copy)
    return out


async def wait_for_minigame_click_ack(
    actions: Any,
    *,
    monitor: Any | None,
    grid_id: int,
    before_sig: tuple,
    before_reward: str,
    is_grid_message: Callable[[Any], bool],
    get_reward_content: Callable[[], str],
    set_reward_content: Callable[[str], None],
    edit_timeout: float = 12.0,
    bonus_timeout: float = 3.0,
    retry_timeout: float = 6.0,
    max_retries: int = 2,
    log: Callable[[str], None] | None = None,
    on_retry_click: Callable[[], Any] | None = None,
    on_ack_recovered: Callable[[], Any] | None = None,
) -> tuple[Any | None, str]:
    """Wait for Mudae to acknowledge a minigame click, with retries and fetch fallback.

    ``on_ack_recovered`` is awaited whenever the acknowledgement had to be
    fetched over HTTP because nothing arrived on the gateway. One of those is
    ordinary; a run of them means the gateway has stopped delivering while
    still claiming to be connected, which costs ``edit_timeout`` *per click* —
    a 22-click ``$ot`` board took five minutes that way on 2026-08-30.
    """

    async def _wait_for_grid_edit() -> Any | None:
        result = await actions.wait_for(
            _make_wait_predicate(
                lambda snapshot: (
                    snapshot.message_id == grid_id
                    and is_grid_message(snapshot)
                    and grid_signature(snapshot.buttons) != before_sig
                )
            ),
            timeout=bonus_timeout,
        )
        return result[0] if result else None

    def _make_wait_predicate(
        matches: Callable[[Any], bool],
    ) -> Callable[[Any, Any], bool]:
        def predicate(snapshot: Any, _parsed: Any) -> bool:
            if is_oh_reward_message(snapshot):
                content = getattr(snapshot, "content", "") or ""
                if reward_has_entries(content):
                    set_reward_content(content)
            return matches(snapshot)

        return predicate

    async def _try_fetch_grid() -> Any | None:
        if monitor is None or not hasattr(monitor, "fetch_message_snapshot"):
            return None
        try:
            snapshot = await monitor.fetch_message_snapshot(grid_id)
        except Exception:
            return None
        if (
            snapshot is not None
            and is_grid_message(snapshot)
            and grid_signature(snapshot.buttons) != before_sig
        ):
            return snapshot
        return None

    async def _resolve_once(timeout: float) -> tuple[Any | None, str, bool]:
        latest_grid: Any | None = None
        latest_reward = before_reward

        def matches(snapshot: Any) -> bool:
            nonlocal latest_grid, latest_reward
            if is_oh_reward_message(snapshot):
                content = getattr(snapshot, "content", "") or ""
                if reward_has_entries(content) and content != before_reward:
                    latest_reward = content
                    set_reward_content(content)
                    return True
            if (
                snapshot.message_id == grid_id
                and is_grid_message(snapshot)
                and grid_signature(snapshot.buttons) != before_sig
            ):
                latest_grid = snapshot
                latest_reward = get_reward_content()
                return True
            return False

        result = await actions.wait_for(
            _make_wait_predicate(matches),
            timeout=timeout,
        )
        if not result:
            current_reward = get_reward_content()
            if current_reward != before_reward:
                latest_reward = current_reward
            return None, latest_reward, False

        if latest_grid is not None and latest_reward == before_reward:
            bonus = await actions.wait_for(
                _make_wait_predicate(
                    lambda snapshot: (
                        is_oh_reward_message(snapshot)
                        and reward_has_entries(getattr(snapshot, "content", "") or "")
                        and (getattr(snapshot, "content", "") or "") != before_reward
                    )
                ),
                timeout=bonus_timeout,
            )
            if bonus:
                latest_reward = get_reward_content()

        if latest_grid is None and latest_reward != before_reward:
            fetched = await _wait_for_grid_edit()
            if fetched is not None:
                latest_grid = fetched

        if latest_grid is not None:
            return latest_grid, latest_reward, True
        if latest_reward != before_reward:
            return None, latest_reward, True
        return None, latest_reward, False

    for attempt in range(max_retries + 1):
        timeout = edit_timeout if attempt == 0 else retry_timeout
        grid, reward, ok = await _resolve_once(timeout)
        if ok:
            return grid, reward

        fetched = await _try_fetch_grid()
        if fetched is not None:
            if log:
                log("click ack recovered via fetch — continuing")
            if on_ack_recovered is not None:
                await on_ack_recovered()
            return fetched, get_reward_content()

        current_reward = get_reward_content()
        if current_reward != before_reward:
            if log:
                log("reward received — waiting for grid edit")
            grid = await _wait_for_grid_edit()
            if grid is not None:
                return grid, current_reward
            if attempt < max_retries:
                if log:
                    log(
                        f"grid edit slow — retry "
                        f"{attempt + 1}/{max_retries}"
                    )
                await asyncio.sleep(0.5)
                continue
            if log:
                log("grid edit missing — continuing from reward line")
            return None, current_reward

        if attempt < max_retries:
            if log:
                log(f"click ack slow — retry {attempt + 1}/{max_retries}")
            if on_retry_click is not None:
                await on_retry_click()
            await asyncio.sleep(0.5)
            continue

    return None, before_reward


def is_free_oh_click(button: dict[str, Any]) -> bool:
    return _emoji(button) in SPHERE_FREE_EMOJIS


def purple_free_outcome(
    custom_id: str,
    before_reward: str,
    after_reward: str,
    buttons: list[dict[str, Any]],
    *,
    clicked_emoji: str = "",
) -> bool:
    """True when a paid click resolved to a free purple outcome.

    Hidden buttons can flip to ``spP`` on the grid (or add an ``spP`` payout).
    Dark/light transforms stay paid even when the tracker says they became purple.
    """
    if clicked_emoji.strip() in TRANSFORM_EMOJIS:
        return False
    for outcome in new_reward_line_types(before_reward, after_reward):
        if outcome in SPHERE_FREE_EMOJIS:
            return True
    for button in buttons:
        if str(button.get("custom_id") or "") != custom_id:
            continue
        if _emoji(button) in SPHERE_FREE_EMOJIS:
            return True
    return False


def choose_oh_click(
    buttons: list[dict[str, Any]],
    *,
    clicks_spent: int = 0,
    clicks_budget: int = _DEFAULT_CLICKS_ALLOWED,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Pick the next button to click, or ``None`` when no legal move remains.

    Preference order:
        1. any revealed free purple (``spP``);
        2. highest-value revealed paid sphere (never blue/teal — prefer ``spU``);
        3. a random face-down (``spU``) button — only while budget remains.
    """
    chooser = rng or random
    budget_left = clicks_spent < clicks_budget

    free_purples: list[dict[str, Any]] = []
    value_spheres: list[dict[str, Any]] = []
    hidden: list[dict[str, Any]] = []

    for button in buttons:
        if not _is_clickable(button):
            continue
        emoji = _emoji(button)
        if not emoji.startswith("sp"):
            continue
        if emoji in SPHERE_FREE_EMOJIS:
            free_purples.append(button)
        elif emoji == SPHERE_HIDDEN_EMOJI:
            if budget_left:
                hidden.append(button)
        elif emoji in SPHERE_REVEAL_EMOJIS:
            continue  # blue / teal: too low value — prefer face-down spU
        elif budget_left:
            value_spheres.append(button)

    if free_purples:
        return max(free_purples, key=lambda b: _button_sort_key(buttons, b))
    if value_spheres:
        return max(value_spheres, key=lambda b: _button_sort_key(buttons, b))
    if hidden:
        return chooser.choice(hidden)
    return None


class OhSphereGame:
    """Drive a single ``$oh`` session end to end."""

    def __init__(
        self,
        actions: Any,
        monitor: Any,
        *,
        log: Callable[[str], None],
        rng: random.Random | None = None,
        grid_timeout: float = 12.0,
        edit_timeout: float = 12.0,
        click_delay: float = 1.2,
    ) -> None:
        self._actions = actions
        self._monitor = monitor
        self._log = log
        self._rng = rng or random.Random()
        self._grid_timeout = grid_timeout
        self._edit_timeout = edit_timeout
        self._click_delay = click_delay
        self._reward_content = ""

    async def play(self, *, prefix: str = "$", uses: int = 1) -> dict[str, Any]:
        enter_macro_activity(self._monitor)
        clicks_spent = 0
        free_clicks = 0
        try:
            self._actions.drain_queue()
            cmd = minigame_command("oh", uses)
            label = f"${cmd}" if uses > 1 else "$oh"
            self._log(f"{label}: starting sphere game")
            await self._actions.send_command(cmd, prefix=prefix)

            grid, exhausted = await self._wait_for_grid()
            if exhausted is not None:
                log_minigame_exhausted(self._log, exhausted)
                return empty_minigame_result(
                    "exhausted",
                    extra={
                        "free_clicks": 0,
                        "oq_bonus": 0,
                        "ot_bonus": 0,
                        "oc_bonus": 0,
                        "spheres_bonus": 0,
                    },
                    exhausted=exhausted,
                )
            if grid is None:
                self._log(f"{label}: grid did not appear (timeout)")
                return empty_minigame_result(
                    "no grid",
                    extra={
                        "free_clicks": 0,
                        "oq_bonus": 0,
                        "ot_bonus": 0,
                        "oc_bonus": 0,
                        "spheres_bonus": 0,
                    },
                )

            bonus = parse_oh_invested_bonus(grid.content or "")
            if bonus["oq_bonus"] or bonus["ot_bonus"] or bonus["spheres_bonus"]:
                parts = []
                if bonus["oq_bonus"]:
                    parts.append(f"+{bonus['oq_bonus']} $oq")
                if bonus["ot_bonus"]:
                    parts.append(f"+{bonus['ot_bonus']} $ot")
                if bonus["spheres_bonus"]:
                    parts.append(f"+{bonus['spheres_bonus']:,} sp")
                self._log(f"{label}: perk 10 · " + " · ".join(parts))

            grid_id = grid.message_id
            buttons = list(grid.buttons)
            clicks_budget = parse_clicks_allowed(grid.content)
            session_clicks: list[dict[str, Any]] = []
            self._log(f"{label}: grid ready · {clicks_budget} paid clicks allowed")
            await asyncio.sleep(FIRST_CLICK_DELAY_SEC)

            while not is_oh_game_over(buttons):
                choice = choose_oh_click(
                    buttons,
                    clicks_spent=clicks_spent,
                    clicks_budget=clicks_budget,
                    rng=self._rng,
                )
                if choice is None:
                    if clicks_spent < clicks_budget:
                        self._log("$oh: no clickable sphere left — stopping")
                    else:
                        self._log("$oh: paid clicks used · no free purples left")
                    break

                custom_id = choice["custom_id"]
                clicked_index = cell_index(buttons, custom_id)
                emoji = _emoji(choice)
                free = is_free_oh_click(choice)
                kind = "free purple" if free else (
                    "hidden" if emoji == SPHERE_HIDDEN_EMOJI else emoji
                )
                before_sig = grid_signature(buttons)
                before_reward = self._reward_content

                ok = await self._actions.click_button(grid_id, custom_id)
                if not ok:
                    self._log(f"$oh: click failed ({kind}) — stopping")
                    break

                updated, reward_content = await self._wait_for_click_resolution(
                    grid_id,
                    before_sig,
                    before_reward,
                    custom_id=custom_id,
                )
                if updated is None and reward_content == before_reward:
                    self._log("$oh: click ack timeout — stopping")
                    break

                if updated is not None:
                    buttons = list(updated.buttons)
                else:
                    buttons = _disable_button(buttons, custom_id)

                if updated is None and reward_content != before_reward:
                    self._log("$oh: continuing from reward line (grid edit pending)")

                self._reward_content = reward_content
                resolved_free = free or purple_free_outcome(
                    custom_id,
                    before_reward,
                    reward_content,
                    buttons,
                    clicked_emoji=emoji,
                )
                grid_emoji = ""
                if clicked_index is not None:
                    board_now = board_emojis(buttons)
                    if 0 <= clicked_index < len(board_now):
                        grid_emoji = board_now[clicked_index]
                classified = classify_oh_click(
                    clicked_emoji=emoji,
                    reward_types=new_reward_outcome_types(before_reward, reward_content),
                    grid_emoji=grid_emoji,
                )
                oc_grant = int(classified.get("oc_bonus") or 0)
                session_clicks.append(
                    make_click(
                        clicked_index,
                        str(classified["emoji"]),
                        paid=not resolved_free,
                        resolved=list(classified.get("resolved") or []),
                        oc_bonus=oc_grant,
                    )
                )
                outcome = _click_outcome_note(classified, kind)
                if oc_grant:
                    self._log(f"$oh: hidden click granted +{oc_grant} $oc")
                if resolved_free:
                    free_clicks += 1
                    if free:
                        self._log(f"$oh: free click → {outcome} ({free_clicks} free)")
                    else:
                        self._log(
                            f"$oh: free click → purple reveal ({free_clicks} free)"
                        )
                else:
                    clicks_spent += 1
                    self._log(
                        f"$oh: click {clicks_spent}/{clicks_budget} → {outcome}"
                    )

                await asyncio.sleep(self._click_delay)

            if is_oh_game_over(buttons):
                self._log("$oh: grid locked — minigame finished")

            buttons = await wait_for_final_grid(
                self._actions,
                grid_id=grid_id,
                buttons=buttons,
                is_grid_message=is_oh_grid_message,
                get_reward_content=lambda: self._reward_content,
                set_reward_content=lambda content: setattr(self, "_reward_content", content),
            )
            session = build_session(
                "oh",
                session_clicks,
                board_emojis(buttons),
                clicks_paid=clicks_spent,
                clicks_budget=clicks_budget,
                reason="done",
                oq_bonus=bonus["oq_bonus"],
                ot_bonus=bonus["ot_bonus"],
                spheres_bonus=bonus["spheres_bonus"],
            )
            oc_bonus = int(session.get("oc_bonus") or 0)

            reward = total_reward_from_content(self._reward_content)
            reward_note = f" · +{reward} spheres" if reward else ""
            oc_note = f" · +{oc_bonus} $oc" if oc_bonus else ""
            self._log(
                f"{label}: finished · {clicks_spent} paid"
                + (f", {free_clicks} free" if free_clicks else "")
                + reward_note
                + oc_note
            )
            return {
                "clicks": clicks_spent,
                "free_clicks": free_clicks,
                "reward": reward,
                "oq_bonus": bonus["oq_bonus"],
                "ot_bonus": bonus["ot_bonus"],
                "oc_bonus": oc_bonus,
                "spheres_bonus": bonus["spheres_bonus"],
                "reason": "done",
                "session": session,
            }
        finally:
            exit_macro_activity(self._monitor)

    async def _wait_for_grid(self) -> tuple[Any | None, dict[str, Any] | None]:
        return await wait_for_grid_or_exhausted(
            self._actions,
            self._make_predicate(
                lambda s: is_oh_grid_message(s) or snapshot_is_minigame_exhausted(s)
            ),
            timeout=self._grid_timeout,
        )

    async def _wait_for_click_resolution(
        self,
        grid_id: int,
        before_sig: tuple,
        before_reward: str,
        *,
        custom_id: str,
    ) -> tuple[Any | None, str]:
        """Wait for Mudae to acknowledge a click via grid edit and/or reward line."""

        async def _retry_click() -> None:
            ok = await self._actions.click_button(grid_id, custom_id)
            if ok:
                self._log("$oh: resending click")
            else:
                self._log("$oh: retry click send failed")

        return await wait_for_minigame_click_ack(
            self._actions,
            monitor=self._monitor,
            grid_id=grid_id,
            before_sig=before_sig,
            before_reward=before_reward,
            is_grid_message=is_oh_grid_message,
            get_reward_content=lambda: self._reward_content,
            set_reward_content=lambda content: setattr(self, "_reward_content", content),
            edit_timeout=self._edit_timeout,
            log=self._log,
            on_retry_click=_retry_click,
        )

    def _make_predicate(
        self, matches: Callable[[Any], bool]
    ) -> Callable[[Any, Any], bool]:
        """Wrap a snapshot predicate, keeping reward message content in sync."""

        def predicate(snapshot: Any, _parsed: Any) -> bool:
            if is_oh_reward_message(snapshot):
                content = getattr(snapshot, "content", "") or ""
                if reward_has_entries(content):
                    self._reward_content = content
            return matches(snapshot)

        return predicate
