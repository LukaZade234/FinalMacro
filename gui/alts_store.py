"""Alt accounts: each alt's three parts, and the turn order between them.

Stored under ``settings.json › alts``::

    {"order": ["<account id>", …], "rules": {"<account id>": {…AltRules…}}}

Which accounts are alts is not stored here — that is ``AccountProfile.type``
on the Accounts page. :meth:`AltsStore.alt_ids` reconciles the two: the stored
order first (alts that still exist), then any new alt at the end, so every
account always sees one and the same turn order.
"""

from __future__ import annotations

from typing import Any, Iterable

from macro.alt_rules import AltRules, rules_for_tier, tier_of

ALT_TYPE = "Alt"


class AltsStore:
    KEY = "alts"

    def __init__(self) -> None:
        self.order: list[str] = []
        self.rules: dict[str, AltRules] = {}

    def load_from_settings(self, saved: dict[str, Any]) -> None:
        raw = saved.get(self.KEY)
        raw = raw if isinstance(raw, dict) else {}
        self.order = [str(x) for x in (raw.get("order") or []) if str(x).strip()]
        rules = raw.get("rules")
        self.rules = {
            str(acc): AltRules.from_dict(data)
            for acc, data in (rules.items() if isinstance(rules, dict) else [])
            if isinstance(data, dict)
        }

    def to_settings_fragment(self) -> dict[str, Any]:
        return {
            self.KEY: {
                "order": list(self.order),
                "rules": {acc: rules.to_dict() for acc, rules in sorted(self.rules.items())},
            }
        }

    # ---- who the alts are -------------------------------------------------

    def alt_ids(self, accounts: Iterable[Any]) -> list[str]:
        """Alt account ids in turn order (stored order, then new alts)."""
        alts = [str(acc.id) for acc in accounts if str(getattr(acc, "type", "")) == ALT_TYPE]
        known = set(alts)
        ordered = [acc for acc in self.order if acc in known]
        ordered += [acc for acc in alts if acc not in ordered]
        return ordered

    def sync(self, accounts: Iterable[Any]) -> bool:
        """Bring ``order`` in line with the accounts; True when it changed."""
        ordered = self.alt_ids(list(accounts))
        changed = ordered != self.order
        self.order = ordered
        return changed

    def enabled_alt_ids(self, accounts: Iterable[Any]) -> list[str]:
        return [acc for acc in self.alt_ids(accounts) if self.get(acc).enabled]

    # ---- rules ------------------------------------------------------------

    def get(self, account_id: str) -> AltRules:
        rules = self.rules.get(str(account_id))
        if rules is None:
            rules = rules_for_tier("support")
            self.rules[str(account_id)] = rules
        return rules

    def set_rules(self, account_id: str, data: dict[str, Any]) -> AltRules:
        rules = AltRules.from_dict(data)
        self.rules[str(account_id)] = rules
        return rules

    def apply_tier(self, account_id: str, tier: str) -> AltRules:
        old = self.get(account_id)
        rules = rules_for_tier(tier, enabled=old.enabled)
        # A tier sets behaviour; it does not forget which preset, reserves or
        # kakera colours the user chose.
        rules.claims.own_preset_id = old.claims.own_preset_id
        rules.kakera.keep = old.kakera.keep
        rules.kakera.main_roll_types = list(old.kakera.main_roll_types)
        rules.spheres.keep = old.spheres.keep
        self.rules[str(account_id)] = rules
        return rules

    def set_enabled(self, account_id: str, on: bool) -> None:
        self.get(account_id).enabled = bool(on)

    def move(self, account_id: str, index: int) -> bool:
        """Move an alt to ``index`` in the turn order."""
        account_id = str(account_id)
        if account_id not in self.order:
            return False
        index = max(0, min(int(index), len(self.order) - 1))
        current = self.order.index(account_id)
        if current == index:
            return False
        self.order.pop(current)
        self.order.insert(index, account_id)
        return True

    def forget(self, account_id: str) -> None:
        self.rules.pop(str(account_id), None)
        self.order = [acc for acc in self.order if acc != str(account_id)]

    def tier(self, account_id: str) -> str:
        return tier_of(self.get(account_id))
