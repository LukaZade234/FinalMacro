"""The `$bw` page's inputs, per ``(account, channel)``.

What the sweep needs and no sheet reliably supplies, so the page asks and this
remembers the answers:

* **base pool** — how many different characters the roulette can roll, the
  wishlist included. A *fallback* since ``$limroul`` parsed: that sheet reports
  the figure per roulette and :func:`macro.advisor.bw_advisory` prefers it,
  flat. This typed value stands when ``$limroul`` has not been fetched, or when
  the four roulettes disagree and ``limroul_pool`` has not named one.
* **which roulette** (``limroul_pool``) — blank means "they agree, take any".
  Setting one below the server's ceiling is itself an unlock, so the four can
  differ and there is then a real choice to make.
* **`$persrare` rerolls** — a *fallback* rather than the answer since ``$ov``
  parsed: :func:`macro.advisor.bw_advisory` prefers the sheet's own value and
  falls back to this when ``$ov`` has not been fetched, or printed a value
  :func:`mudae.parsers.ov.persrare_rerolls` does not recognise. At the default
  of 1 the model is exactly the no-persrare one, so an unfetched ``$ov`` costs
  nothing.
* **the claimed-character count** — the ``r`` the reroll correction divides by.
  Nothing reports it; only ``$persrare`` above makes it matter at all.
* **slash rolling** — off, because the macro rolls with the `$` prefix.

Plus the focus character, so a page reopened stays on the row you were reading.

Scoped per pair rather than per account, because base pool is a property of the
*server* while the wishlist it is weighed against belongs to the *account* —
half a scope is not a scope, and one server's pool silently applied to another
would move the optimum without saying so.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gui.wishlist_store import scope_key
from macro.bw_calc import DEFAULT_BASE_POOL
from mudae.parsers.limroul import ROULETTES

# Room to model a tiny private server or a whole unrestricted pool, without
# letting a typo produce a curve with no meaning.
MIN_BASE_POOL = 1
MAX_BASE_POOL = 200_000
# `$persrare` accepts a small reroll limit; past a handful the correction is
# indistinguishable from its own limit.
MAX_PERSRARE_N = 20


def _roulette(value: Any) -> str:
    """One of Mudae's four roulettes, or blank for "whichever, they agree"."""
    text = str(value or "").strip().lower().lstrip("$")
    return text if text in ROULETTES else ""


def _clamp(value: Any, low: int, high: int, default: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


@dataclass
class BwOptions:
    """One pair's answers to the questions no sheet answers."""

    base_pool: int = DEFAULT_BASE_POOL
    persrare_n: int = 1
    claimed_pool: int = 0
    uses_slash: bool = False
    focus_name: str = ""
    # "" | "wa" | "ha" | "wg" | "hg" — blank asks the advisor to take $limroul's
    # own answer when the four roulettes agree.
    limroul_pool: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BwOptions:
        data = data if isinstance(data, dict) else {}
        return cls(
            base_pool=_clamp(
                data.get("base_pool"), MIN_BASE_POOL, MAX_BASE_POOL, DEFAULT_BASE_POOL
            ),
            persrare_n=_clamp(data.get("persrare_n"), 1, MAX_PERSRARE_N, 1),
            claimed_pool=_clamp(data.get("claimed_pool"), 0, MAX_BASE_POOL, 0),
            uses_slash=bool(data.get("uses_slash")),
            focus_name=str(data.get("focus_name") or "").strip(),
            limroul_pool=_roulette(data.get("limroul_pool")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_pool": self.base_pool,
            "persrare_n": self.persrare_n,
            "claimed_pool": self.claimed_pool,
            "uses_slash": self.uses_slash,
            "focus_name": self.focus_name,
            "limroul_pool": self.limroul_pool,
        }


class BwOptionsStore:
    """Every scope's `$bw` inputs, as one ``settings.json`` key."""

    KEY = "bw_options"

    def __init__(self) -> None:
        self.by_scope: dict[str, BwOptions] = {}

    def load_from_settings(self, saved: dict[str, Any]) -> None:
        raw = saved.get(self.KEY)
        self.by_scope = {}
        if not isinstance(raw, dict):
            return
        for key, payload in raw.items():
            scope = str(key or "").strip()
            if scope:
                self.by_scope[scope] = BwOptions.from_dict(payload)

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            self.KEY: {
                scope: options.to_dict()
                for scope, options in sorted(self.by_scope.items())
            }
        }

    def get(self, account_id: str, channel_profile_id: str) -> BwOptions:
        """This pair's inputs, or the defaults — never another pair's."""
        key = scope_key(account_id, channel_profile_id)
        if not key:
            return BwOptions()
        return self.by_scope.get(key, BwOptions())

    def set(
        self, account_id: str, channel_profile_id: str, options: BwOptions
    ) -> None:
        key = scope_key(account_id, channel_profile_id)
        if key:
            self.by_scope[key] = options
