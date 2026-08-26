"""Play all available sphere minigames after querying ``$ohu``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from macro.minigame_daily import (
    PLAYABLE_MINIGAMES,
    availability_from_record,
    load_minigame_record,
    mark_game_exhausted,
    refresh_minigames_if_refill_passed,
    save_minigame_record,
    should_skip_playable_minigames,
    update_record_from_ohu,
)
from macro.minigame_util import minigame_use_batches
from macro.oc_game import OcSphereGame
from macro.oq_game import OqSphereGame
from macro.perk9_daily import (
    apply_record_to_state as apply_perk9_record_to_state,
    load_perk9_record,
    save_perk9_record,
    update_record_from_ohu as update_perk9_from_ohu,
)
from macro.sphere_game import OhSphereGame

_OHU_SETTLE_SEC = 2.0
_OHU_TIMEOUT_SEC = 12.0
_BETWEEN_GAMES_SEC = 1.5


def _availability_from_fields(fields: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for game_id in ("oh", "oc", "oq", "ot"):
        left = int(fields.get(f"{game_id}_left") or 0)
        stored = int(fields.get(f"{game_id}_stored") or 0)
        total = fields.get(f"{game_id}_total")
        if total is None:
            total = left + stored
        result[f"{game_id}_left"] = left
        result[f"{game_id}_stored"] = stored
        result[f"{game_id}_total"] = max(0, int(total))
    return result


def _merge_game_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"clicks": 0, "reward": 0, "reason": "skipped"}
    merged: dict[str, Any] = {
        "clicks": 0,
        "reward": 0,
        "oq_bonus": 0,
        "ot_bonus": 0,
        "oc_bonus": 0,
        "spheres_bonus": 0,
        "reason": "done",
        "batches": len(results),
    }
    for result in results:
        merged["clicks"] += int(result.get("clicks") or 0)
        merged["reward"] += int(result.get("reward") or 0)
        merged["oq_bonus"] += int(result.get("oq_bonus") or 0)
        merged["ot_bonus"] += int(result.get("ot_bonus") or 0)
        merged["oc_bonus"] += int(result.get("oc_bonus") or 0)
        merged["spheres_bonus"] += int(result.get("spheres_bonus") or 0)
        if result.get("reason") not in {None, "done"}:
            merged["reason"] = result.get("reason")
    return merged


class PlayAllMinigames:
    """Query ``$ohu``, then spend all ``$oh`` / ``$oc`` / ``$oq`` uses."""

    def __init__(
        self,
        actions: Any,
        monitor: Any,
        *,
        log: Callable[[str], None],
        on_game_reward: Callable[[str, int, int], None] | None = None,
        on_game_result: Callable[[str, dict[str, Any]], None] | None = None,
        between_games_sec: float = _BETWEEN_GAMES_SEC,
        daily_get: Callable[[], dict[str, Any]] | None = None,
        daily_save: Callable[[dict[str, Any]], None] | None = None,
        state: Any | None = None,
    ) -> None:
        self._actions = actions
        self._monitor = monitor
        self._log = log
        self._on_game_reward = on_game_reward
        self._on_game_result = on_game_result
        self._between_games_sec = between_games_sec
        self._daily_get = daily_get
        self._daily_save = daily_save
        self._state = state
        self.availability: dict[str, int] = {
            f"{game}_{kind}": 0
            for game in ("oh", "oc", "oq", "ot")
            for kind in ("left", "stored", "total")
        }

    async def play(
        self,
        *,
        prefix: str = "$",
        ignore_daily_skip: bool = False,
    ) -> dict[str, Any]:
        cached = self._load_refreshed_record()
        if (
            not ignore_daily_skip
            and cached is not None
            and should_skip_playable_minigames(cached)
        ):
            availability = availability_from_record(cached)
            self.availability = availability
            eta = cached.refill_at or "unknown"
            self._log(f"$ohu: skipped until refill ({eta})")
            return {
                "availability": dict(availability),
                "played": {},
                "reason": "skipped until refill",
            }

        availability = await self._query_ohu(prefix=prefix)
        if availability is None:
            return {
                "availability": dict(self.availability),
                "played": {},
                "reason": "ohu failed",
            }
        self.availability = availability
        self._log(
            "$ohu: available · "
            f"$oh {availability['oh_total']} "
            f"($oh {availability['oh_left']}+{availability['oh_stored']} stored) · "
            f"$oc {availability['oc_total']} · "
            f"$oq {availability['oq_total']} · "
            f"$ot {availability['ot_total']} (saved, not played)"
        )

        played: dict[str, Any] = {}
        oh_uses = availability["oh_total"]
        oc_uses = availability["oc_total"]
        oq_uses = availability["oq_total"]
        ot_uses = availability["ot_total"]

        if oh_uses > 0:
            oh_results = await self._play_batches(
                "oh", OhSphereGame, oh_uses, prefix=prefix
            )
            oh_result = _merge_game_results(oh_results)
            played["oh"] = oh_result
            for result in oh_results:
                self._record_reward("oh", result)
            oq_bonus = int(oh_result.get("oq_bonus") or 0)
            ot_bonus = int(oh_result.get("ot_bonus") or 0)
            oc_bonus = int(oh_result.get("oc_bonus") or 0)
            if oq_bonus > 0:
                oq_uses += oq_bonus
                self.availability["oq_total"] = oq_uses
                self._log(
                    f"play-all: +{oq_bonus} $oq from perk 10 → $oq {oq_uses}"
                )
            if ot_bonus > 0:
                ot_uses += ot_bonus
                self.availability["ot_total"] = ot_uses
                self._log(
                    f"play-all: +{ot_bonus} $ot from perk 10 → $ot {ot_uses} "
                    "(saved, not played)"
                )
            if oc_bonus > 0:
                oc_uses += oc_bonus
                self.availability["oc_total"] = oc_uses
                self._log(
                    f"play-all: +{oc_bonus} $oc from $oh hidden clicks → $oc {oc_uses}"
                )
            self._note_game_finished("oh", oh_result)
            await asyncio.sleep(self._between_games_sec)
        else:
            self._log("play-all: no $oh uses — skipping")

        if oc_uses > 0:
            oc_results = await self._play_batches(
                "oc", OcSphereGame, oc_uses, prefix=prefix
            )
            played["oc"] = _merge_game_results(oc_results)
            for result in oc_results:
                self._record_reward("oc", result)
            self._note_game_finished("oc", played["oc"])
            await asyncio.sleep(self._between_games_sec)
        else:
            self._log("play-all: no $oc uses — skipping")

        if oq_uses > 0:
            oq_results = await self._play_batches(
                "oq", OqSphereGame, oq_uses, prefix=prefix
            )
            played["oq"] = _merge_game_results(oq_results)
            for result in oq_results:
                self._record_reward("oq", result)
            self._note_game_finished("oq", played["oq"])
        else:
            self._log("play-all: no $oq uses — skipping")

        self._log(
            "play-all: finished · "
            f"$oh {oh_uses} · $oc {oc_uses} · $oq {oq_uses} · "
            f"$ot {ot_uses} unused"
        )
        return {
            "availability": dict(self.availability),
            "played": played,
            "reason": "done",
        }

    async def _play_batches(
        self,
        name: str,
        game_cls: type,
        total_uses: int,
        *,
        prefix: str,
    ) -> list[dict[str, Any]]:
        batches = minigame_use_batches(total_uses)
        if len(batches) > 1:
            self._log(
                f"play-all: ${name} {total_uses} exceeds max 10 — "
                f"splitting into {', '.join(str(b) for b in batches)}"
            )
        results: list[dict[str, Any]] = []
        for index, uses in enumerate(batches):
            if index > 0:
                await asyncio.sleep(self._between_games_sec)
            result = await game_cls(
                self._actions, self._monitor, log=self._log
            ).play(prefix=prefix, uses=uses)
            results.append(result)
            if result.get("reason") not in {None, "done"}:
                self._log(
                    f"play-all: ${name} batch {uses} stopped ({result.get('reason')})"
                )
                break
        return results

    def _record_reward(self, game: str, result: dict[str, Any]) -> None:
        if self._on_game_result:
            self._on_game_result(game, result)
        if not self._on_game_reward:
            return
        reward = int(result.get("reward") or 0)
        clicks = int(result.get("clicks") or 0)
        if reward > 0:
            self._on_game_reward(game, reward, clicks)

    async def _query_ohu(self, *, prefix: str) -> dict[str, int] | None:
        self._actions.drain_queue()
        self._log("Sent $ohu")
        await self._actions.send_command("ohu", prefix=prefix)
        await asyncio.sleep(_OHU_SETTLE_SEC)
        parsed = await self._actions.wait_for_ohu(timeout=_OHU_TIMEOUT_SEC)
        if parsed is None:
            self._log("$ohu timeout — cannot play all minigames")
            return None
        fields = dict(parsed.fields or {})
        self._persist_ohu_fields(fields)
        return _availability_from_fields(fields)

    def _load_refreshed_record(self):
        if not self._daily_get:
            return None
        daily = dict(self._daily_get())
        record = load_minigame_record(daily)
        was_exhausted = any(
            record.entry(game).exhausted for game in PLAYABLE_MINIGAMES
        )
        refreshed = refresh_minigames_if_refill_passed(record)
        now_exhausted = any(
            refreshed.entry(game).exhausted for game in PLAYABLE_MINIGAMES
        )
        if was_exhausted and not now_exhausted:
            self._persist_daily(save_minigame_record(daily, refreshed))
        return refreshed

    def _persist_daily(self, daily: dict[str, Any]) -> None:
        if self._daily_save:
            self._daily_save(daily)

    def _persist_ohu_fields(self, fields: dict[str, Any]) -> None:
        if not self._daily_get or not self._daily_save:
            return
        daily = dict(self._daily_get())
        minigames = update_record_from_ohu(load_minigame_record(daily), fields)
        daily = save_minigame_record(daily, minigames)
        perk9 = update_perk9_from_ohu(load_perk9_record(daily), fields)
        daily = save_perk9_record(daily, perk9)
        self._persist_daily(daily)
        if self._state is not None:
            apply_perk9_record_to_state(self._state, perk9)

    def _note_game_finished(self, game: str, result: dict[str, Any]) -> None:
        reason = result.get("reason")
        if reason not in {None, "done", "exhausted"}:
            return
        if not self._daily_get or not self._daily_save:
            return
        daily = dict(self._daily_get())
        record = load_minigame_record(daily)
        refill = result.get("refill_minutes")
        try:
            refill_minutes = int(refill) if refill is not None else None
        except (TypeError, ValueError):
            refill_minutes = None
        daily = save_minigame_record(
            daily,
            mark_game_exhausted(record, game, refill_minutes=refill_minutes),
        )
        self._persist_daily(daily)
