"""Play all available sphere minigames after querying ``$ohu``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from macro.minigame_util import minigame_use_batches
from macro.oc_game import OcSphereGame
from macro.oq_game import OqSphereGame
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
        "spheres_bonus": 0,
        "reason": "done",
        "batches": len(results),
    }
    for result in results:
        merged["clicks"] += int(result.get("clicks") or 0)
        merged["reward"] += int(result.get("reward") or 0)
        merged["oq_bonus"] += int(result.get("oq_bonus") or 0)
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
        between_games_sec: float = _BETWEEN_GAMES_SEC,
    ) -> None:
        self._actions = actions
        self._monitor = monitor
        self._log = log
        self._on_game_reward = on_game_reward
        self._between_games_sec = between_games_sec
        self.availability: dict[str, int] = {
            f"{game}_{kind}": 0
            for game in ("oh", "oc", "oq", "ot")
            for kind in ("left", "stored", "total")
        }

    async def play(self, *, prefix: str = "$") -> dict[str, Any]:
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

        if oh_uses > 0:
            oh_results = await self._play_batches(
                "oh", OhSphereGame, oh_uses, prefix=prefix
            )
            oh_result = _merge_game_results(oh_results)
            played["oh"] = oh_result
            for result in oh_results:
                self._record_reward("oh", result)
            oq_bonus = int(oh_result.get("oq_bonus") or 0)
            spheres_bonus = int(oh_result.get("spheres_bonus") or 0)
            if oq_bonus > 0:
                oq_uses += oq_bonus
                self.availability["oq_total"] = oq_uses
                self._log(
                    f"play-all: +{oq_bonus} $oq from invested spheres → $oq {oq_uses}"
                )
            if spheres_bonus > 0 and self._on_game_reward:
                self._on_game_reward("oh", spheres_bonus, 0)
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
        else:
            self._log("play-all: no $oq uses — skipping")

        self._log(
            "play-all: finished · "
            f"$oh {oh_uses} · $oc {oc_uses} · $oq {oq_uses} · "
            f"$ot {availability['ot_total']} unused"
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
        return _availability_from_fields(dict(parsed.fields or {}))
