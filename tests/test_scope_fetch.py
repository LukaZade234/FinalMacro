"""Tests for fetching a sheet on the scope a page is pointed at.

Two halves, and the split is deliberate. The *policy* — which of the four
routes a fetch takes — is plain data in `gui/scope_fetch.py` and is pinned
here exhaustively. The *bridge* half is pinned only where it decides
something a Discord gateway is not needed to observe: who a sheet gets filed
under, and what refuses to run.
"""

from __future__ import annotations

import json

import pytest

from gui.accounts import AccountStore
from gui.presets import PresetStore
from gui.run_target import resolve_run_target, resolve_scope_target
from gui.scope_fetch import (
    ROUTE_BLOCKED,
    ROUTE_HOP,
    ROUTE_SEND,
    ROUTE_TEMPORARY,
    SCOPE_FETCH_COMMANDS,
    plan_scope_fetch,
)
from gui.server_profiles import ServerProfileStore
from gui.targets import TargetStore


def _plan(**overrides):
    kwargs = dict(
        command="settings",
        account_id="acc-a",
        channel_profile_id="chan-1",
        has_session=True,
        live_account_id="acc-a",
        live_channel_profile_id="chan-1",
        busy_reason="",
    )
    kwargs.update(overrides)
    return plan_scope_fetch(**kwargs)


# --- The four routes --------------------------------------------------------


def test_same_pair_as_the_live_session_just_sends():
    plan = _plan()
    assert plan.route == ROUTE_SEND
    assert plan.moves_the_connection is False


def test_a_different_server_hops_and_comes_back():
    assert _plan(live_channel_profile_id="chan-2").route == ROUTE_HOP


def test_a_different_account_on_the_same_server_also_hops():
    """The sheet is per (account, server) — either half moving is a move."""
    assert _plan(live_account_id="acc-b").route == ROUTE_HOP


def test_no_session_stands_a_temporary_one_up():
    plan = _plan(has_session=False, live_account_id="", live_channel_profile_id="")
    assert plan.route == ROUTE_TEMPORARY
    assert plan.moves_the_connection is True


def test_both_moving_routes_have_to_put_the_session_back():
    assert _plan(live_account_id="acc-b").moves_the_connection is True


# --- What refuses -----------------------------------------------------------


def test_a_busy_macro_blocks_and_says_why():
    plan = _plan(busy_reason="Stop the macro first")
    assert plan.route == ROUTE_BLOCKED
    assert plan.allowed is False
    assert plan.reason == "Stop the macro first"


def test_busy_beats_every_route_including_the_free_one():
    """Even a send that would not move anything waits its turn."""
    for overrides in (
        {},
        {"live_account_id": "acc-b"},
        {"has_session": False},
    ):
        assert _plan(busy_reason="Applying settings", **overrides).route == ROUTE_BLOCKED


@pytest.mark.parametrize(
    "overrides",
    [{"account_id": ""}, {"channel_profile_id": ""}, {"account_id": "", "channel_profile_id": ""}],
)
def test_half_a_scope_is_not_a_scope(overrides):
    plan = _plan(**overrides)
    assert plan.route == ROUTE_BLOCKED
    assert "account and a server" in plan.reason


def test_only_allowlisted_commands_go_through():
    """This path can connect as any account, so what it may send is explicit."""
    assert _plan(command="roll").route == ROUTE_BLOCKED
    assert _plan(command="marry").route == ROUTE_BLOCKED
    for command in SCOPE_FETCH_COMMANDS:
        assert _plan(command=command).allowed is True


# --- Resolving an explicit pair ---------------------------------------------


def _stores():
    accounts = AccountStore()
    profiles = ServerProfileStore()
    presets = PresetStore()
    targets = TargetStore()

    acc_a = accounts.add_account("A", token="token-a")
    acc_b = accounts.add_account("B", token="token-b")
    server = profiles.add_server("Key Server")
    chan_1 = profiles.add_channel(server, "mudae-w", "1111")
    chan_2 = profiles.add_channel(server, "mudae-x", "2222")
    return accounts, profiles, presets, targets, acc_a, acc_b, chan_1, chan_2


def test_scope_target_resolves_a_pair_that_is_not_the_active_one():
    accounts, profiles, presets, targets, acc_a, acc_b, _chan_1, chan_2 = _stores()

    active = resolve_run_target(accounts, profiles, presets, targets)
    other = resolve_scope_target(accounts, profiles, presets, targets, acc_b, chan_2)

    assert active is not None and other is not None
    assert (active.account_id, active.discord_channel_id) == (acc_a, "1111")
    assert (other.account_id, other.discord_channel_id) == (acc_b, "2222")
    assert other.token == "token-b"
    # And it left the actives exactly where it found them.
    assert accounts.active_account_id == acc_a


def test_scope_target_refuses_a_pair_it_cannot_connect_as():
    accounts, profiles, presets, targets, acc_a, _acc_b, chan_1, _chan_2 = _stores()

    assert resolve_scope_target(accounts, profiles, presets, targets, "nope", chan_1) is None
    assert resolve_scope_target(accounts, profiles, presets, targets, acc_a, "nope") is None

    accounts.find_account(acc_a).token = "   "
    assert resolve_scope_target(accounts, profiles, presets, targets, acc_a, chan_1) is None


def test_scope_target_uses_that_pairs_own_preset():
    accounts, profiles, presets, targets, _acc_a, acc_b, _chan_1, chan_2 = _stores()
    preset_id = presets.default_preset_id
    targets.ensure_target(acc_b, chan_2, preset_id)

    resolved = resolve_scope_target(accounts, profiles, presets, targets, acc_b, chan_2)
    assert resolved is not None
    assert resolved.preset_id == preset_id


# --- The bridge half --------------------------------------------------------


def _bridge(tmp_path, monkeypatch):
    monkeypatch.setattr("gui.settings.SETTINGS_PATH", tmp_path / "settings.json")
    from gui.bridge import AppBridge

    return AppBridge()


def test_a_fetch_in_flight_is_the_reason_the_next_one_is_refused(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path, monkeypatch)
    assert bridge._scope_fetch_busy_reason() == ""

    bridge._scope_fetch_command = "settings"
    assert bridge._scope_fetch_busy_reason() == "Already fetching $settings"

    bridge.fetchForScope("bonus", "acc-a", "chan-1")
    assert bridge.statusText == "Already fetching $settings"


def test_the_button_state_names_what_is_running_and_what_blocks_it(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path, monkeypatch)

    idle = json.loads(bridge.scopeFetchJson)
    assert idle == {"command": "", "busy": False, "blocked_by": ""}

    bridge._scope_fetch_command = "wishlist"
    running = json.loads(bridge.scopeFetchJson)
    assert running["command"] == "wishlist"
    assert running["busy"] is True
    assert running["blocked_by"] == "Already fetching $wishlist"


def test_the_characters_page_spinner_follows_the_wishlist_fetch(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path, monkeypatch)

    assert json.loads(bridge.mudaeWishlistFor("acc-a", "chan-1"))["fetching"] is False
    bridge._scope_fetch_command = "shop"
    assert json.loads(bridge.mudaeWishlistFor("acc-a", "chan-1"))["fetching"] is False
    bridge._scope_fetch_command = "wishlist"
    assert json.loads(bridge.mudaeWishlistFor("acc-a", "chan-1"))["fetching"] is True


def test_a_sheet_is_filed_under_the_account_that_asked_for_it(tmp_path, monkeypatch):
    """The point of the whole exercise.

    While a fetch has borrowed the connection, Mudae is answering *its*
    account — so a sheet arriving then belongs to that account, not to
    whichever one the Run target is bound to.
    """
    bridge = _bridge(tmp_path, monkeypatch)
    bridge._run_account_id = "acc-run"

    assert bridge._sheet_account_id() == "acc-run"
    bridge._scope_fetch_account_id = "acc-other"
    assert bridge._sheet_account_id() == "acc-other"
    bridge._scope_fetch_account_id = ""
    assert bridge._sheet_account_id() == "acc-run"


def test_the_delivered_sheet_honours_the_stamped_account(tmp_path, monkeypatch):
    bridge = _bridge(tmp_path, monkeypatch)
    server = bridge._profiles.add_server("Key Server")
    channel_profile_id = bridge._profiles.add_channel(server, "mudae-w", "1111")
    bridge._run_account_id = "acc-run"

    def deliver(account_id: str, rolls: int) -> None:
        bridge._deliver_profile_update(
            json.dumps(
                {
                    "discord_channel_id": 1111,
                    "kind": "bonus",
                    "fields": {"rolls_per_hour": rolls},
                    "summary": "",
                    "guild_id": None,
                    "guild_name": None,
                    "channel_name": "mudae-w",
                    "account_id": account_id,
                }
            )
        )

    deliver("acc-run", 30)
    deliver("acc-other", 12)

    channel = bridge._profiles.find_channel_by_profile_id(channel_profile_id)[1]
    assert bridge._profiles.account_sheet(
        channel, "bonus", account_id="acc-run"
    ).fields["rolls_per_hour"] == 30
    # The borrower's sheet landed on its own slice rather than over the top.
    assert bridge._profiles.account_sheet(
        channel, "bonus", account_id="acc-other"
    ).fields["rolls_per_hour"] == 12


def test_an_unstamped_delivery_still_falls_back_to_the_run_account(tmp_path, monkeypatch):
    """Older payloads, and every non-fetch parse, carry no account id."""
    bridge = _bridge(tmp_path, monkeypatch)
    server = bridge._profiles.add_server("Key Server")
    channel_profile_id = bridge._profiles.add_channel(server, "mudae-w", "1111")
    bridge._run_account_id = "acc-run"

    bridge._deliver_profile_update(
        json.dumps(
            {
                "discord_channel_id": 1111,
                "kind": "shop",
                "fields": {"spheres": 5},
                "summary": "",
                "guild_id": None,
                "guild_name": None,
                "channel_name": "mudae-w",
            }
        )
    )

    channel = bridge._profiles.find_channel_by_profile_id(channel_profile_id)[1]
    assert bridge._profiles.account_sheet(
        channel, "shop", account_id="acc-run"
    ).fields["spheres"] == 5


def test_the_legacy_fetch_slots_target_the_run_pair(tmp_path, monkeypatch):
    """`fetchSettings()` and friends still mean "here", for the setup wizard."""
    bridge = _bridge(tmp_path, monkeypatch)
    server = bridge._profiles.add_server("Key Server")
    channel_profile_id = bridge._profiles.add_channel(server, "mudae-w", "1111")
    account_id = bridge._accounts.add_account("A", token="token-a")

    assert bridge._default_fetch_scope() == (account_id, channel_profile_id)

    bridge._run_account_id = "acc-run"
    bridge._run_channel_profile_id = "chan-run"
    assert bridge._default_fetch_scope() == ("acc-run", "chan-run")
