"""The alts' connections, alongside the main's run.

Each alt gets its own Discord gateway in the main's run channel. Claim and
kakera windows are seconds long, and button clicks need a live gateway
session, so the one-connection token switching used for ``$p``/``$daily`` is
not fast enough here.

The pool owns, per alt: the monitor, a ``DiscordActions`` fed only by that
alt's monitor, and the alt's own ``AccountState``. Every alt's commands go
through the channel's :class:`~macro.turns.ChannelCoordinator` lane, as do
the main's while alts are running, so no two accounts' commands or reply
waits overlap.

Alt connections are narrow, like the temporary fetch connection: they feed
their own waiter and nothing else. The main's monitor already records every
roll for the Run feed and the logs; an alt seeing the same messages must not
record them a second time.
"""

from __future__ import annotations

import asyncio
import time
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable

from macro.actions import is_harem_parse_result, is_ohu_parse_result
from macro.alt_rules import AltRules, tier_of
from macro.config import MacroConfig
from macro.state import AccountState
from macro.transfers import TransferParty, TransferResult, Transfers
from macro.tu_apply import apply_tu_fields
from macro.turns import ChannelCoordinator
from mudae.parsers.ohu import parse_sphere_stock
from mudae.parsers.transfers import KIND_KAKERA, KIND_SPHERES
from mudae.types import MessageKind

# The alts connect together; one that hasn't answered by then is left out.
CONNECT_TIMEOUT_SEC = 45.0
TU_REPLY_TIMEOUT_SEC = 12.0
# Mudae answers $mmk= at once when there is a harem and stays silent when
# there is none, so a quiet wait this long means "empty", not "lost".
HAREM_SILENCE_SEC = 5.0
# Between two of one alt's own commands. Mudae drops a command sent straight
# after the same account's last one ($tu then $mmk= on Fetch; $tu then $givek).
# The channel lane already spaces different accounts.
OWN_COMMAND_GAP_SEC = 1.5

# Called as make_monitor(token, channel_id, on_parsed) → a ChannelMonitor-like
# object with start_background / stop_background / get_own_user_id /
# get_own_usernames / is_connected.
MonitorFactory = Callable[[str, int, Callable[[Any, Any], None]], Any]
ActionsFactory = Callable[[Any], Any]


@dataclass
class AltSpec:
    account_id: str
    name: str
    token: str
    rules: AltRules
    config: MacroConfig


@dataclass
class AltSession:
    spec: AltSpec
    monitor: Any = None
    actions: Any = None
    state: AccountState = field(default_factory=AccountState)
    connected: bool = False
    status: str = "off"
    user_id: int | None = None
    # The alt's Discord *username*, as its own $tu opens with it. Transfer
    # prompts use the same name ("**lukijade**, do you really want to give …"),
    # never the display name ("you guys played sekiro?").
    mudae_name: str = ""
    # Page 1 of the alt's ``$mmk=`` (most valuable first), for passing
    # characters by hand: [{"name", "kakera"}]. ``harem_pages`` is how many
    # pages the whole harem has.
    harem: list[dict[str, Any]] = field(default_factory=list)
    harem_pages: int | None = None
    # When the last Fetch ran (UTC "HH:MM:SS") and what it read.
    fetched_at: str = ""
    fetched_from: list[str] = field(default_factory=list)
    # Its own $bonus is stored for the run channel and applied to ``state``.
    # Until then it takes no trigger (macro/alt_readiness.py).
    ready: bool = False
    not_ready: str = "$bonus not read"
    # Kakera earned clicking the main's rolls this session.
    kakera_from_main_rolls: int = 0
    # monotonic time of this alt's last command (``AccountPool.own_gap``).
    last_command_at: float = 0.0
    # Characters claimed on the main's rolls, waiting for the batch-end $give.
    claimed_for_main: list[str] = field(default_factory=list)

    @property
    def account_id(self) -> str:
        return self.spec.account_id

    def names(self) -> list[str]:
        names = [self.mudae_name, *self.state.own_usernames]
        return [n for n in dict.fromkeys(names) if n]

    def snapshot(self, turn: int) -> dict[str, Any]:
        """What the Run page's alts block shows for this alt."""
        st = self.state
        return {
            "account_id": self.account_id,
            "name": self.spec.name,
            "turn": turn,
            "tier": tier_of(self.spec.rules),
            "connected": self.connected,
            "status": self.status,
            "claim_available": st.claim_available,
            "claim_cooldown_minutes": st.claim_cooldown_minutes,
            "power_percent": st.power_percent,
            "power_max_percent": st.power_max_percent,
            "dk_stock": st.dk_stock,
            "dk_next_minutes": st.dk_next_minutes,
            "rt_available": st.rt_available,
            "rt_next_minutes": st.rt_next_minutes,
            "rolls_left": st.rolls_left,
            "kakera_stock": st.kakera_stock,
            "sphere_stock": st.sphere_stock,
            "minigames_left": st.minigames_left,
            "daily_available": st.daily_available,
            "ready": self.ready,
            "not_ready": "" if self.ready else self.not_ready,
            "power_cost": st.kakera_base_cost,
            "kakera_from_main_rolls": self.kakera_from_main_rolls,
            "claimed_for_main": list(self.claimed_for_main),
        }


class AccountPool:
    def __init__(
        self,
        coordinator: ChannelCoordinator,
        *,
        make_monitor: MonitorFactory,
        make_actions: ActionsFactory,
        log: Callable[[str], None] | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.coordinator = coordinator
        self._make_monitor = make_monitor
        self._make_actions = make_actions
        self._log = log or (lambda _t: None)
        self._on_change = on_change or (lambda: None)
        self.sessions: dict[str, AltSession] = {}
        self._main: TransferParty | None = None
        self._main_names: Callable[[], list[str]] = lambda: []
        # This session's transfers, newest last, for Alts › Ledger.
        self.transfer_log: list[dict[str, Any]] = []
        # macro/alt_ledger.py: daily totals, transfers and pending gives on
        # disk. None (tests, previews) keeps everything in memory.
        self.ledger: Any = None

    # ---- lifecycle -------------------------------------------------------

    async def start(self, specs: list[AltSpec], channel_id: int) -> int:
        """Connect every alt in ``specs``; returns how many came up.

        The turn order is ``specs``' order. An alt whose connection fails is
        left out of the order, so a trigger is never handed to an account that
        cannot act on it.
        """
        for spec in specs:
            self.sessions[spec.account_id] = self._build(spec, channel_id)
        await asyncio.gather(*(self._connect(s) for s in self.sessions.values()))
        self._sync_order()
        up = sum(1 for s in self.sessions.values() if s.connected)
        self._log(f"Alts: {up}/{len(specs)} connected")
        self._on_change()
        return up

    def _build(self, spec: AltSpec, channel_id: int) -> AltSession:
        session = AltSession(spec=spec, status="connecting")
        holder: dict[str, Any] = {}

        def on_parsed(snapshot: Any, parsed: Any) -> None:
            actions = holder.get("actions")
            if actions is not None:
                actions.feed(snapshot, parsed)

        session.monitor = self._make_monitor(spec.token, int(channel_id), on_parsed)
        session.actions = self._make_actions(session.monitor)
        holder["actions"] = session.actions
        session.actions.set_lane(
            self.coordinator,
            spec.account_id,
            session.names,
        )
        return session

    async def _connect(self, session: AltSession) -> None:
        name = session.spec.name
        if not session.spec.token.strip():
            session.status = "no token"
            self._log(f"Alts: {name} has no token — left out")
            return
        try:
            ready = await asyncio.wait_for(session.monitor.start_background(), CONNECT_TIMEOUT_SEC)
        except Exception as exc:  # noqa: BLE001 - one alt must not stop the others
            ready = False
            self._log(f"Alts: {name} could not connect ({exc})")
        if not ready:
            session.status = "offline"
            return
        session.connected = True
        session.status = "watching"
        session.user_id = session.monitor.get_own_user_id()
        session.state.own_usernames = list(session.monitor.get_own_usernames() or [])
        session.state.own_user_ids = [session.user_id] if session.user_id is not None else []

    async def own_gap(self, session: AltSession) -> None:
        """Wait until :data:`OWN_COMMAND_GAP_SEC` after this alt's last command."""
        wait = OWN_COMMAND_GAP_SEC - (time.monotonic() - session.last_command_at)
        if wait > 0:
            await asyncio.sleep(wait)

    def _sync_order(self) -> None:
        self.coordinator.set_alt_order(
            acc for acc, s in self.sessions.items() if s.connected
        )

    async def stop(self) -> None:
        for session in self.sessions.values():
            if session.monitor is not None and session.connected:
                try:
                    await session.monitor.stop_background()
                except Exception:  # noqa: BLE001
                    pass
            session.connected = False
            session.status = "off"
        self.coordinator.set_alt_order([])
        self.sessions.clear()
        self._on_change()

    # ---- notification mode follows the main ------------------------------

    async def release_for_notifications(self) -> None:
        """The main disconnected between sessions: the alts do too."""
        for session in self.sessions.values():
            if session.connected:
                try:
                    await session.monitor.stop_background()
                except Exception:  # noqa: BLE001
                    pass
                session.connected = False
                session.status = "standby"
        self._sync_order()
        self._on_change()

    async def restore_for_notifications(self) -> None:
        """The main reconnected for its session: bring the alts back."""
        waiting = [s for s in self.sessions.values() if s.status == "standby"]
        await asyncio.gather(*(self._connect(s) for s in waiting))
        self._sync_order()
        self._on_change()

    # ---- status ----------------------------------------------------------

    def connected_sessions(self) -> list[AltSession]:
        """Connected alts, in turn order."""
        return [self.sessions[acc] for acc in self.coordinator.alts if acc in self.sessions]

    def notify(self) -> None:
        """Something on an alt changed that the Run page shows."""
        self._on_change()

    def ready_sessions(self) -> list[AltSession]:
        """Connected alts whose own sheets are read, in turn order: the only
        ones any automatic trigger may go to."""
        return [s for s in self.connected_sessions() if s.ready]

    async def refresh_status(self, session: AltSession) -> bool:
        """``$tu`` for one alt, through the lane; True when it answered."""
        if not session.connected:
            return False
        session.actions.drain_queue()
        await self.own_gap(session)
        await session.actions.send_command("tu", prefix=session.spec.config.prefix)
        session.last_command_at = time.monotonic()
        parsed = await session.actions.wait_for_tu(timeout=TU_REPLY_TIMEOUT_SEC)
        if parsed is None:
            self._log(f"Alts: {session.spec.name} $tu timeout")
            return False
        user = str(parsed.fields.get("tu_user") or "").strip()
        if user:
            session.mudae_name = user
        apply_tu_fields(session.state, parsed.fields)
        self._on_change()
        return True

    async def refresh_all(self) -> None:
        """``$tu`` for every connected alt, one after another in turn order."""
        for session in self.connected_sessions():
            await self.refresh_status(session)

    def snapshot(self) -> list[dict[str, Any]]:
        order = self.coordinator.alts
        rows = []
        for acc, session in self.sessions.items():
            turn = order.index(acc) + 1 if acc in order else 0
            rows.append(session.snapshot(turn))
        rows.sort(key=lambda r: (r["turn"] == 0, r["turn"]))
        return rows

    # ---- transfers to the main -------------------------------------------

    def set_main(self, actions: Any, user_id: int | None, names: Callable[[], list[str]]) -> None:
        """The main's side of every transfer (``None`` id: transfers refused)."""
        self._main = None if user_id is None else TransferParty(actions, user_id, [])
        self._main_names = names

    async def give_to_main(
        self,
        account_id: str,
        *,
        character: str | None = None,
        kind: str | None = None,
        amount: int | None = None,
        why: str = "by hand",
    ) -> TransferResult:
        """One ``$give`` (``character``) or ``$givek``/``$givesp`` (``kind`` + ``amount``).

        ``why`` is what the Ledger shows next to it (by hand, claimed for the
        main, end of session, once a day).
        """
        what = "character" if character else str(kind or "")
        session = self.sessions.get(account_id)
        if self._main is None:
            return TransferResult(False, what, reason="main not connected")
        if session is None or not session.connected or session.user_id is None:
            return TransferResult(False, what, reason="alt not connected")
        await self.own_gap(session)
        giver = TransferParty(session.actions, session.user_id, session.names())
        receiver = TransferParty(self._main.actions, self._main.user_id, list(self._main_names()))
        transfers = Transfers(prefix=session.spec.config.prefix, log=self._log)
        previous, session.status = session.status, "giving to main"
        self._on_change()
        try:
            if character:
                result = await transfers.give_character(giver, receiver, character)
            else:
                result = await transfers.give_amount(giver, receiver, str(kind), int(amount or 0))
        finally:
            session.status = previous
            session.last_command_at = time.monotonic()
            self._on_change()
        if not result.ok:
            self._log(f"Alts: {session.spec.name} → main {what} failed ({result.reason})")
        if self.ledger is not None:
            entry = self.ledger.record_transfer(account_id, session.spec.name, result, why=why)
        else:
            entry = {
                "time": dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S"),
                "alt": session.spec.name,
                "transfer": result.transfer,
                "what": result.character or (f"{result.amount:,}" if result.amount else ""),
                "ok": result.ok,
                "confirmed": result.confirmed,
                "reason": result.reason,
                "why": why,
            }
        self.transfer_log.append(entry)
        del self.transfer_log[:-200]
        return result

    # ---- passing by hand (Alts › Ledger) ---------------------------------

    async def fetch_balances(self, account_id: str) -> dict[str, Any]:
        """Kakera and sphere stock, and page 1 of the harem, for one alt.

        ``$tu`` first: an alt's untrimmed ``$tu`` carries both balances. Only
        what it lacks is asked for separately, ``$ku`` for kakera and ``$ohu``
        for spheres. Then ``$mmk=`` for the characters.
        """
        session = self.sessions.get(account_id)
        if session is None or not session.connected:
            return {"ok": False, "reason": "alt not connected"}
        previous, session.status = session.status, "reading balances"
        self._on_change()
        sources: list[str] = []
        try:
            sources += await self._read_stocks(session)
            harem_source = await self._fetch_harem(session)
            if harem_source:
                sources.append(harem_source)
            session.fetched_at = dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")
            session.fetched_from = sources
        finally:
            session.status = previous
            self._on_change()
        return {
            "ok": True,
            "kakera_stock": session.state.kakera_stock,
            "sphere_stock": session.state.sphere_stock,
            "harem": list(session.harem),
            "harem_pages": session.harem_pages,
            "fetched_from": list(session.fetched_from),
        }

    async def read_stocks(self, account_id: str) -> bool:
        """Fresh kakera and sphere stock for one alt (no harem); True when
        both are known afterwards."""
        session = self.sessions.get(account_id)
        if session is None or not session.connected:
            return False
        previous, session.status = session.status, "reading balances"
        self._on_change()
        try:
            await self._read_stocks(session)
        finally:
            session.status = previous
            self._on_change()
        return session.state.kakera_stock is not None and session.state.sphere_stock is not None

    async def _read_stocks(self, session: AltSession) -> list[str]:
        """``$tu`` first; ``$ku`` / ``$ohu`` only for what it lacks."""
        prefix = session.spec.config.prefix
        actions = session.actions
        sources: list[str] = []
        # Stale balances must not survive a fetch that cannot re-read them.
        session.state.kakera_stock = None
        session.state.sphere_stock = None
        if await self.refresh_status(session):
            sources.append("$tu")
        st = session.state
        if st.kakera_stock is None:
            actions.drain_queue()
            await self.own_gap(session)
            await actions.send_command("ku", prefix=prefix)
            session.last_command_at = time.monotonic()
            found = await actions.wait_for(
                lambda _s, p: p.kind != MessageKind.TU and p.fields.get("kakera_stock") is not None,
                timeout=TU_REPLY_TIMEOUT_SEC,
            )
            if found:
                st.kakera_stock = int(found[1].fields["kakera_stock"])
                sources.append("$ku")
        if st.sphere_stock is None:
            actions.drain_queue()
            await self.own_gap(session)
            await actions.send_command("ohu", prefix=prefix)
            session.last_command_at = time.monotonic()
            found = await actions.wait_for(
                lambda _s, p: is_ohu_parse_result(p), timeout=TU_REPLY_TIMEOUT_SEC
            )
            if found:
                stock = found[1].fields.get("sphere_stock")
                if stock is None:
                    stock = parse_sphere_stock(str(found[1].fields.get("content") or ""))
                if stock is not None:
                    st.sphere_stock = int(stock)
                    sources.append("$ohu")
        return sources

    def account_for_username(self, username: str) -> str | None:
        """The alt account a Discord username belongs to, or None."""
        key = str(username or "").strip().casefold()
        if not key:
            return None
        for acc, session in self.sessions.items():
            if key in {n.casefold() for n in session.names()}:
                return acc
        return None

    async def holds_character(self, account_id: str, name: str) -> bool:
        """Whether this alt's ``$mmk=`` page 1 lists ``name``.

        Page 1 is enough for the force-divorce target: it is the main's most
        valuable character, so it tops any harem it is in.
        """
        from macro.wishlist import normalize_wishlist_name

        session = self.sessions.get(account_id)
        if session is None or not session.connected:
            return False
        if not await self._fetch_harem(session):
            return False
        key = normalize_wishlist_name(name)
        return any(normalize_wishlist_name(str(h.get("name") or "")) == key for h in session.harem)

    async def _fetch_harem(self, session: AltSession) -> str | None:
        """Page 1 of ``$mmk=``; returns what to list as the source, or None."""
        names = {n.casefold() for n in session.names()}
        session.actions.drain_queue()
        await self.own_gap(session)
        sent = await session.actions.send_command("mmk=", prefix=session.spec.config.prefix)
        session.last_command_at = time.monotonic()
        if sent is None:
            return None
        # ``is_harem_parse_result``: the alt typed ``$mmk=`` itself, so its own
        # connection labels the reply a command response wrapping the harem,
        # not a bare HAREM. Matching only HAREM timed out on a real reply and
        # read it as an empty harem (2026-11-06).
        found = await session.actions.wait_for(
            lambda _s, p: is_harem_parse_result(p)
            and (not names or str(p.fields.get("owner") or "").casefold() in names),
            timeout=HAREM_SILENCE_SEC,
        )
        if found is None:
            # Mudae says nothing at all for an empty harem.
            session.harem = []
            session.harem_pages = 0
            # Nothing came back, so nothing else will clear the lane's hold.
            session.actions.release_hold()
            return "$mmk= (silent: empty harem)"
        fields = found[1].fields
        session.harem = [
            {"name": str(e.get("name")), "kakera": e.get("kakera")}
            for e in fields.get("entries") or []
            if e.get("name")
        ]
        session.harem_pages = fields.get("pages")
        return "$mmk="

    @staticmethod
    def amount_to_pass(stock: int | None, keep: int) -> int:
        """Everything above ``keep`` (0 when the stock is unknown or below it)."""
        if stock is None:
            return 0
        return max(0, int(stock) - max(0, int(keep)))

    async def pass_to_main(
        self,
        account_id: str,
        *,
        kakera_keep: int | None = None,
        spheres_keep: int | None = None,
        characters: list[str] | tuple[str, ...] = (),
        why: str = "by hand",
    ) -> list[TransferResult]:
        """Hand stock above each ``*_keep`` (``None`` = don't pass) and the
        named characters to the main, one exchange at a time, using the last
        fetched balances. A failed exchange stops the rest."""
        session = self.sessions.get(account_id)
        results: list[TransferResult] = []
        if session is None:
            return results
        plan: list[tuple[str, Any]] = []
        if kakera_keep is not None:
            plan.append((KIND_KAKERA, self.amount_to_pass(session.state.kakera_stock, kakera_keep)))
        if spheres_keep is not None:
            plan.append((KIND_SPHERES, self.amount_to_pass(session.state.sphere_stock, spheres_keep)))
        plan.extend(("character", name) for name in characters)
        for kind, what in plan:
            if kind == "character":
                result = await self.give_to_main(account_id, character=str(what), why=why)
                if result.ok:
                    session.harem = [h for h in session.harem if h["name"] != what]
            else:
                if not what:
                    continue
                result = await self.give_to_main(account_id, kind=kind, amount=int(what), why=why)
                if result.ok:
                    attr = "kakera_stock" if kind == KIND_KAKERA else "sphere_stock"
                    setattr(session.state, attr, int(getattr(session.state, attr) or 0) - int(what))
            results.append(result)
            if not result.ok:
                break
        self._on_change()
        return results
