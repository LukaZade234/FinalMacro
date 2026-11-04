"""`$dl` / `$adl` / plain `$wl` parsing, paged capture, and the lists store.

The pages come from a real capture (`tests/fixtures/mudae_lists_capture.json`,
2026-11-04 10:24–10:25 UTC). Only page 1 of `$dld` exists in it, so the
multi-page cases build later pages from page 1's shape.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
from types import SimpleNamespace

from gui.mudae_lists_store import MudaeListsStore
from gui.mudae_wishlist_store import MudaeWishlist
from macro.listing_capture import capture_paged_listing, page_matcher
from mudae.commands import normalize_command
from mudae.parsers.antidisablelist import merge_antidisablelist_pages
from mudae.parsers.disablelist import merge_disablelist_pages, parse_disablelist_page
from mudae.parsers.pipeline import parse_message
from mudae.parsers.wishlist import (
    is_wishlist_message,
    merge_wishlist_pages,
    parse_plain_wishlist_row,
    parse_wishlist_page,
)
from mudae.types import MessageKind

_FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "mudae_lists_capture.json").read_text(
        encoding="utf-8"
    )
)


def _snapshot(key: str, *, embed_patch: dict | None = None, edited: bool = False):
    raw = _FIXTURE[key]
    embed = dict(raw["embeds"][0])
    embed.update(embed_patch or {})
    return SimpleNamespace(
        message_id=int(raw["message_id"]),
        channel_id=1,
        channel_name="mudae-commands",
        guild_id=1,
        guild_name="g",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="",
        embeds=[embed],
        buttons=raw["buttons"],
        created_at="10:24:51",
        edited=edited,
        components=raw["components"],
    )


# --- $dld --------------------------------------------------------------------


def test_dld_page_reads_totals_pools_toggles_and_names():
    for paired in ("dld", "dl", None):
        parsed = parse_message(_snapshot("dld_page1"), reply_to_command=paired)
        fields = parsed.fields
        assert fields["owner"] == "lukazade234"
        assert (fields["used"], fields["max"]) == (42, 62)
        assert fields["total"] == 133_775
        assert fields["pools"] == {"wa": 45_920, "ha": 47_768, "wg": 30_870, "hg": 25_315}
        assert fields["pool_limits"] == {"wa": 46_309, "ha": 47_739, "wg": 34_887, "hg": 29_960}
        assert fields["limit_warnings"] == [
            "Pool limit reached: 47,739 $ha (series above this limit are not disabled)"
        ]
        assert fields["floor"].startswith("Can't be reduced below 3,052")
        # A toggle is its own kind of entry, not a disable.
        assert fields["toggles"] == [
            {"name": "Western animanga series", "command": "$togglewestern"}
        ]
        assert len(fields["entries"]) == 14
        assert fields["entries"][0] == "Kadokawa Corporation"
        assert fields["entries"][-1] == "Virtual Music"
        assert "Western animanga series" not in fields["entries"]
        assert (fields["page"], fields["pages"]) == (1, 3)


def test_dld_is_no_longer_a_roll():
    """Regression: the page parsed as a roll named "lukazade234's Disablelist"."""
    paired = parse_message(_snapshot("dld_page1"), reply_to_command="dld")
    assert paired.fields["parser_command"] == "disablelist"
    assert "character_name" not in paired.fields
    unpaired = parse_message(_snapshot("dld_page1"), reply_to_command=None)
    assert unpaired.kind == MessageKind.DISABLELIST


def test_several_toggles_are_all_kept():
    text = (
        "x's Disablelist (3/62)\n"
        "**Western animanga series are completely disabled** ($togglewestern)\n"
        "**Game series are completely disabled** ($togglegames)\n"
        "**Shueisha** (10,925 ~ 4,538 $wa, 6,684 $ha, 171 $wg, 555 $hg)"
    )
    fields = parse_disablelist_page(text)
    assert [t["command"] for t in fields["toggles"]] == ["$togglewestern", "$togglegames"]
    assert fields["entries"] == ["Shueisha"]


def test_dld_merge_joins_pages_in_order_and_reports_partial():
    page1 = parse_disablelist_page(
        "x's Disablelist (4/62)\n**A** (1 ~ 1 $wa)\n**B** (1 ~ 1 $wa)\nPage 1 / 2"
    )
    page2 = parse_disablelist_page("x's Disablelist (4/62)\n**C** (1 ~ 1 $wa)\n**A** (1 ~ 1 $wa)\nPage 2 / 2")
    whole = merge_disablelist_pages([page1, page2])
    assert whole["entries"] == ["A", "B", "C"]
    assert whole["complete"] is True
    only_first = merge_disablelist_pages([page1])
    assert only_first["complete"] is False
    assert only_first["seen_pages"] == [1]


# --- $adl --------------------------------------------------------------------


def test_adl_reads_counts_and_series_in_order():
    parsed = parse_message(_snapshot("adl"), reply_to_command="adl")
    fields = parsed.fields
    assert fields["parser_command"] == "antidisablelist"
    assert (fields["used"], fields["max"]) == (4, 500)
    assert fields["characters"] == 134
    assert fields["entries"] == [
        "Cyberpunk: Edgerunners",
        "Lord of Mysteries 2: Circle of Inevitability",
        "Lord of the Mysteries",
        "Omniscient Reader's Viewpoint",
    ]
    assert parse_message(_snapshot("adl")).kind == MessageKind.ANTIDISABLELIST
    merged = merge_antidisablelist_pages([fields])
    assert merged["complete"] is True  # one page, no footer
    assert merged["count_matches"] is True


def test_list_aliases():
    for typed in ("dl", "dld"):
        assert normalize_command(typed) == "disablelist"
    assert normalize_command("adl") == "antidisablelist"
    for typed in ("wlu", "wlt", "wlsz+z!z-", "wlz+z!z-"):
        assert normalize_command(typed) == "wishlist"


# --- plain $wl -----------------------------------------------------------------


def test_plain_wl_rows_keep_order_and_wish_type():
    parsed = parse_message(_snapshot("wl_plain_page1"), reply_to_command="wl")
    entries = parsed.fields["entries"]
    assert len(entries) == 20
    assert [e["name"] for e in entries[:3]] == ["Han Sooyoung", "Marin Kitagawa", "Lucy"]
    assert sum(1 for e in entries if e["starwish"]) == 9  # matches 9/9 $sw
    assert all(e["locked"] and e["owned"] for e in entries)
    assert entries[0]["sphere_percent"] == 63
    assert entries[0]["spheres"] is None


def test_hand_typed_wlu_is_a_wishlist_not_a_roll():
    """Regression: `$wlu` parsed as a claimable roll card."""
    parsed = parse_message(_snapshot("wlu_plain"), reply_to_command="wlu")
    assert parsed.fields["parser_command"] == "wishlist"
    first = parsed.fields["entries"][0]
    assert first["name"] == "Villager"
    assert first["server_disabled"] is True
    assert first["locked"] is False


def test_kakera_wish_row():
    """Hand-made: no kakera wish has been captured yet."""
    row = parse_plain_wishlist_row("**Makima** ✅ <:kakera:469835869059153940> +188%")
    assert row is not None
    assert row["kakera_wish"] is True
    assert row["locked"] is False
    assert row["name"] == "Makima"


def test_no_sphere_rows_sit_beside_sphere_rows():
    """`z-` adds uninvested wishes to the `z+z!` listing; both shapes must read."""
    text = (
        "x's Wishlist - 3/10 $wl, 1/3 $sw\n"
        "Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full\n"
        "**Power** ✅ 🔐\n"
        "Makima ✅ 🔐 · 7,000 sp - 5 (x5), 6"
    )
    fields = parse_wishlist_page(text)
    assert [e["name"] for e in fields["entries"]] == ["Rebecca", "Power", "Makima"]
    assert fields["entries"][1]["spheres"] is None


def test_a_headerless_dm_part_of_plain_rows_is_recognised_narrowly():
    part = "Power ✅ 🔐\nMakima ✅ 🔐\nQuanxi ✅ 🔐"
    assert is_wishlist_message(part) is True
    # A claim line with a bold name and a ✅ must not qualify.
    assert is_wishlist_message("**Lucy** and **Reze** are now married! ✅") is False


# --- paged capture ---------------------------------------------------------------


class _FakeActions:
    def __init__(self, replies):
        self._replies = list(replies)
        self.sent: list[str] = []
        self.clicks: list[tuple[int, str]] = []

    async def send_command(self, command: str):
        self.sent.append(command)

    async def click_button(self, message_id: int, custom_id: str) -> bool:
        self.clicks.append((message_id, custom_id))
        return True

    async def wait_for(self, predicate, *, timeout: float = 0.0):
        while self._replies:
            snapshot, parsed = self._replies.pop(0)
            if predicate(snapshot, parsed):
                return snapshot, parsed
        return None


def _dld_page(page: int, names: list[str], *, header: bool = True):
    description = "\n".join(f"**{n}** (1 ~ 1 $wa, 0 $ha, 0 $wg, 0 $hg)" for n in names)
    patch = {"description": description, "footer": f"Page {page} / 3"}
    if not header:
        patch["author"] = ""
    return _snapshot("dld_page1", embed_patch=patch, edited=True)


def test_capture_clicks_through_every_dld_page():
    first = _snapshot("dld_page1")
    second = _dld_page(2, ["Bones", "Kyoto Animation"])
    third = _dld_page(3, ["Ufotable"])
    actions = _FakeActions(
        [
            (first, parse_message(first, reply_to_command="dld")),
            (second, parse_message(second)),
            (third, parse_message(third)),
        ]
    )
    result = asyncio.run(
        capture_paged_listing(
            actions,
            command="dld",
            label="Disablelist",
            is_page=page_matcher("disablelist", MessageKind.DISABLELIST),
            merge=merge_disablelist_pages,
        )
    )
    forward = next(b["custom_id"] for b in _FIXTURE["dld_page1"]["buttons"] if b["emoji"] == "wright")
    assert actions.sent == ["dld"]
    assert [c[1] for c in actions.clicks] == [forward, forward]
    assert result.ok and result.complete and result.reason == ""
    assert len(result.entries) == 17
    assert result.entries[-1] == "Ufotable"
    assert result.data["total"] == 133_775  # from page 1, kept through the merge


def test_capture_that_loses_a_page_says_so():
    first = _snapshot("dld_page1")
    actions = _FakeActions([(first, parse_message(first, reply_to_command="dld"))])
    result = asyncio.run(
        capture_paged_listing(
            actions,
            command="dld",
            label="Disablelist",
            is_page=page_matcher("disablelist", MessageKind.DISABLELIST),
            merge=merge_disablelist_pages,
        )
    )
    assert result.ok is True
    assert result.complete is False
    assert "Missing page(s) [2, 3]" in result.reason


def test_wishlist_capture_sends_the_z_minus_flag():
    from macro.wishlist_capture import CHANNEL_COMMAND, DM_COMMAND

    assert DM_COMMAND == "wlsz+z!z-"
    assert CHANNEL_COMMAND == "wlz+z!z-"


# --- store ------------------------------------------------------------------------


def test_store_round_trip_and_presets():
    store = MudaeListsStore()
    page = parse_message(_snapshot("dld_page1")).fields
    store.set("dl", "acc", "chan", merge_disablelist_pages([page]), reason="partial")
    preset = store.save_preset("dl", "Farm", store.get("dl", "acc", "chan").data, source_label="NovelCult")
    assert preset is not None
    wl = MudaeWishlist.from_dict(
        {"entries": parse_message(_snapshot("wl_plain_page1")).fields["entries"]}
    )
    wl_preset = store.save_preset("wl", "Wishes", wl.to_dict())
    assert wl_preset is not None
    assert wl_preset.data["entries"][0] == {
        "name": "Han Sooyoung",
        "starwish": True,
        "locked": True,
        "kakera_wish": False,
    }
    # Claimed-ness (✅) is the capture's, not the saved list's.
    assert "owned" not in wl_preset.data["entries"][0]

    again = MudaeListsStore()
    again.load_from_settings(json.loads(json.dumps(store.to_settings_fragment())))
    snap = again.get("dl", "acc", "chan")
    assert snap.data["toggles"] == [{"name": "Western animanga series", "command": "$togglewestern"}]
    assert len(snap.data["entries"]) == 14
    assert snap.reason == "partial"
    # Another pair never borrows this pair's capture.
    assert again.get("dl", "acc", "other").data["entries"] == []
    assert [p.name for p in again.presets["dl"]] == ["Farm"]
    assert again.rename_preset("dl", preset.id, "Gacha")
    assert again.presets["dl"][0].name == "Gacha"
    assert again.delete_preset("dl", preset.id)
    assert again.presets["dl"] == []


def test_wishlist_store_keeps_the_wish_type_flags():
    entries = parse_message(_snapshot("wlu_plain")).fields["entries"]
    listing = MudaeWishlist.from_dict({"entries": entries})
    assert listing.entries[0]["server_disabled"] is True
    assert MudaeWishlist.from_dict(listing.to_dict()).entries[0]["server_disabled"] is True


def test_reader_lets_list_page_edits_through():
    """Page 2+ arrive as edits; the roll-edit filter must not swallow them."""
    from mudae.discord_reader import _is_listing_page
    from mudae.parsers.classify import snapshot_text

    for key in ("dld_page1", "adl", "wl_plain_page1"):
        assert _is_listing_page(snapshot_text(_snapshot(key, edited=True))), key


def test_blank_preset_filled_from_a_pasted_list_and_edited():
    store = MudaeListsStore()
    preset = store.save_preset("dl", "Custom", {})
    assert preset is not None and preset.data["entries"] == []
    pasted = (
        "Kadokawa Corporation$Shueisha$Kodansha$Webcomics$Shogakukan$Square Enix Holdings"
        "$YouTube$Turn-Based Role-Playing Games$Isekai$Anime Originals$Ecchi$Houbunsha"
        "$Multiplayer Games$Virtual Music$Bandai Namco$Webmanga$Akita Shoten$Horror Genre"
    )
    assert store.add_entries("dl", preset.id, pasted) == 18
    # Repeats and spacing are tidied, not added twice.
    assert store.add_entries("dl", preset.id, " shueisha $ Kodansha\nNew  One ") == 1
    assert preset.data["entries"][-1] == "New One"
    assert preset.data["used"] == 19

    assert store.rename_entry("dl", preset.id, 0, "Kadokawa") is True
    assert store.rename_entry("dl", preset.id, 0, "Shueisha") is False  # already listed
    assert store.remove_entry("dl", preset.id, 1) is True
    assert preset.data["entries"][:2] == ["Kadokawa", "Kodansha"]
    assert store.move_entry("dl", preset.id, 0, 1) is True
    assert preset.data["entries"][:2] == ["Kodansha", "Kadokawa"]
    assert store.move_entry("dl", preset.id, 0, -1) is False

    again = MudaeListsStore()
    again.load_from_settings(json.loads(json.dumps(store.to_settings_fragment())))
    assert again.presets["dl"][0].data["entries"][:2] == ["Kodansha", "Kadokawa"]


def test_editing_a_captured_dl_preset_keeps_totals_the_user_can_change():
    store = MudaeListsStore()
    page = parse_message(_snapshot("dld_page1")).fields
    preset = store.save_preset("dl", "Farm", merge_disablelist_pages([page]))
    assert preset.data["total"] == 133_775
    store.remove_entry("dl", preset.id, 0)
    # Slots follow the rows; the typed-in figures stay until the user changes them.
    assert preset.data["used"] == 13
    assert preset.data["total"] == 133_775
    assert preset.data["pool_limits"] is None  # per server, never on a preset
    assert store.set_count("dl", preset.id, "total", "120,000")
    assert store.set_count("dl", preset.id, "wa", "")
    assert preset.data["total"] == 120_000
    assert "wa" not in preset.data["pools"]
    assert store.set_count("dl", preset.id, "characters", "5") is False
    assert store.remove_toggle("dl", preset.id, 0) is True
    assert preset.data["toggles"] == []


def test_adl_characters_are_typed_and_series_slots_follow_rows():
    store = MudaeListsStore()
    preset = store.save_preset("adl", "Mine", {})
    store.add_entries("adl", preset.id, "Cyberpunk: Edgerunners$Lord of the Mysteries")
    assert preset.data["used"] == 2
    assert preset.data["characters"] is None  # blank is allowed
    assert store.set_count("adl", preset.id, "characters", "134")
    store.add_entries("adl", preset.id, "Omniscient Reader's Viewpoint")
    assert (preset.data["used"], preset.data["characters"]) == (3, 134)


def test_toggles_tick_on_and_off_and_come_from_commands():
    store = MudaeListsStore()
    preset = store.save_preset("dl", "Custom", {})
    assert store.set_toggle("dl", preset.id, "$toggleirl", True)
    assert store.set_toggle("dl", preset.id, "$toggleirl", True) is False  # already on
    assert store.set_toggle("dl", preset.id, "$togglenonsense", True) is False
    summary = store.apply_input("dl", preset.id, "$togglewestern\nShueisha$Kodansha")
    assert summary["toggles"] == 1 and summary["added"] == 2
    assert preset.data["toggles"] == [
        {"name": "IRL series", "command": "$toggleirl"},
        {"name": "Western animanga series", "command": "$togglewestern"},
    ]
    assert store.set_toggle("dl", preset.id, "$toggleirl", False)
    assert [t["command"] for t in preset.data["toggles"]] == ["$togglewestern"]


def test_wish_commands_set_the_wish_type():
    store = MudaeListsStore()
    preset = store.save_preset("wl", "Wishes", {})
    summary = store.apply_input(
        "wl",
        preset.id,
        "$swl reze $lucy\n$wishk Makima\n$wishlk Power\nPlain One\n$wishremove Lucy",
    )
    assert summary["added"] == 5
    assert summary["ignored"] == ["$wishremove Lucy"]
    rows = {e["name"]: e for e in preset.data["entries"]}
    assert [e["name"] for e in preset.data["entries"]] == ["reze", "lucy", "Makima", "Power", "Plain One"]
    assert rows["reze"]["starwish"] and rows["reze"]["locked"] and not rows["reze"]["kakera_wish"]
    assert rows["Makima"]["kakera_wish"] and not rows["Makima"]["starwish"]
    assert rows["Power"]["locked"] and rows["Power"]["kakera_wish"]
    assert not any(rows["Plain One"][f] for f in ("starwish", "locked", "kakera_wish"))
    assert (preset.data["wl_used"], preset.data["sw_used"]) == (5, 2)


def test_wish_insert_by_position_and_reference_and_existing_names_are_updated():
    store = MudaeListsStore()
    preset = store.save_preset("wl", "Wishes", {})
    store.apply_input("wl", preset.id, "A$B$C$D")
    store.apply_input("wl", preset.id, "$wishli 2$X$Y")
    assert [e["name"] for e in preset.data["entries"]] == ["A", "X", "Y", "B", "C", "D"]
    store.apply_input("wl", preset.id, "$wishi C$Z")
    assert [e["name"] for e in preset.data["entries"]] == ["A", "X", "Y", "B", "C", "Z", "D"]
    # An existing name is flagged (and moved with `i`), not duplicated.
    summary = store.apply_input("wl", preset.id, "$swli 1$D")
    assert summary == {"added": 0, "updated": 1, "toggles": 0, "ignored": []}
    assert preset.data["entries"][0]["name"] == "D" and preset.data["entries"][0]["starwish"]


def test_commands_only_apply_to_their_own_list():
    store = MudaeListsStore()
    dl = store.save_preset("dl", "D", {})
    wl = store.save_preset("wl", "W", {})
    assert store.apply_input("dl", dl.id, "$swl reze")["ignored"] == ["$swl reze"]
    assert store.apply_input("wl", wl.id, "$togglewestern")["ignored"] == ["$togglewestern"]


def test_drag_move_to_index():
    store = MudaeListsStore()
    preset = store.save_preset("adl", "S", {})
    store.add_entries("adl", preset.id, "A$B$C$D")
    assert store.move_entry_to("adl", preset.id, 0, 2)
    assert preset.data["entries"] == ["B", "C", "A", "D"]
    assert store.move_entry_to("adl", preset.id, 3, 0)
    assert preset.data["entries"] == ["D", "B", "C", "A"]
    assert store.move_entry_to("adl", preset.id, 1, 1) is False
    assert store.move_entry_to("adl", preset.id, 0, 9) is False


def test_wish_flags_are_editable_and_counts_follow():
    store = MudaeListsStore()
    preset = store.save_preset("wl", "Wishes", {})
    store.add_entries("wl", preset.id, "Lucy$Reze$Makima")
    assert preset.data["entries"][0] == {
        "name": "Lucy", "starwish": False, "locked": False, "kakera_wish": False
    }
    assert store.set_entry_flag("wl", preset.id, 0, "starwish", True)
    assert store.set_entry_flag("wl", preset.id, 2, "kakera_wish", True)
    assert store.set_entry_flag("wl", preset.id, 1, "owned", True) is False
    assert (preset.data["wl_used"], preset.data["sw_used"]) == (3, 1)
    assert store.set_entry_flag("dl", preset.id, 0, "starwish", True) is False


# --- $sdl ---------------------------------------------------------------------

_SDL_CHANNEL = """1,000 disabled

'Her' 💞 - Veil
「Shiki Ryougi」 💞 - Kara no Kyoukai: The Garden of Sinners
●●|●●●●●|●●|● - SCP Foundation
10t 💞 - Boku no Hero Academia
Abby (TLoU) 💞 - The Last of Us Part II
Abiko Samejima 💞 - 【OSHI NO KO】
Abra - Pokédex"""

_SDL_DM_1 = """Disabled characters for this server ($sdl) (5/1,000)
5 disabled

'Her' - Veil
Aiura Mikoto - Saiki Kusuo no Ψ Nan
Akane Tendo - Ranma ½"""

_SDL_DM_2 = """Awesome Face - 
AZKi - hololive"""


def _sdl_embed_snapshot(description, page, pages, *, header=True):
    return SimpleNamespace(
        message_id=900, channel_id=1, channel_name="c", guild_id=1, guild_name="g",
        author_id=1, author_name="Mudae", is_mudae=True, content="",
        embeds=[{
            "author": "Disabled characters for this server ($sdl) (1,000/1,000)" if header else "",
            "title": "", "description": description, "footer": f"Page {page} / {pages}",
        }],
        buttons=_FIXTURE["dld_page1"]["buttons"], created_at="", edited=page > 1, components=[],
    )


def _dm_snapshot(content):
    return SimpleNamespace(
        message_id=901, channel_id=2, channel_name="dm", guild_id=None, guild_name=None,
        author_id=1, author_name="Mudae", is_mudae=True, content=content, embeds=[],
        buttons=[], created_at="", edited=False, components=[],
    )


def test_sdl_channel_page_keeps_names_only():
    from mudae.parsers.serverdisablelist import merge_sdl_pages

    for paired in ("sdl", "sdls", None):
        parsed = parse_message(_sdl_embed_snapshot(_SDL_CHANNEL, 1, 67), reply_to_command=paired)
        fields = parsed.fields
        assert (fields["used"], fields["max"], fields["total"]) == (1000, 1000, 1000)
        assert (fields["page"], fields["pages"]) == (1, 67)
        assert fields["entries"] == [
            "'Her'", "「Shiki Ryougi」", "●●|●●●●●|●●|●", "10t",
            "Abby (TLoU)", "Abiko Samejima", "Abra",
        ]
    assert parse_message(_sdl_embed_snapshot(_SDL_CHANNEL, 1, 67)).kind == MessageKind.SERVERDISABLELIST
    assert merge_sdl_pages([fields])["complete"] is False  # page 1 of 67


def test_sdl_dm_parts_join_and_complete_by_count():
    from mudae.parsers.serverdisablelist import merge_sdl_pages, parse_sdl_page

    first, second = parse_sdl_page(_SDL_DM_1), parse_sdl_page(_SDL_DM_2)
    assert first["entries"] == ["'Her'", "Aiura Mikoto", "Akane Tendo"]
    # An empty series still ends the name; 💞-free DM rows read the same.
    assert second["entries"] == ["Awesome Face", "AZKi"]
    assert merge_sdl_pages([first])["complete"] is False
    merged = merge_sdl_pages([first, second])
    assert merged["complete"] is True and merged["count_matches"] is True


def test_sdl_dm_capture_reads_parts_until_the_count_is_reached():
    from macro.listing_capture import capture_dm_listing
    from mudae.parsers.serverdisablelist import (
        is_serverdisablelist_message, merge_sdl_pages, parse_sdl_page,
    )

    unrelated = _dm_snapshot("Lucy appeared! React with any emoji to claim")
    channel_noise = SimpleNamespace(**{**_dm_snapshot(_SDL_DM_2).__dict__, "guild_id": 1})
    replies = [
        (unrelated, None),        # before the header: not a part
        (channel_noise, None),    # not a DM
        (_dm_snapshot(_SDL_DM_1), None),
        (_dm_snapshot(_SDL_DM_2), None),
        (_dm_snapshot("Zzz - never read"), None),  # after completion
    ]

    class Actions:
        sent: list[str] = []

        async def send_command(self, command):
            self.sent.append(command)

        async def wait_for(self, predicate, *, timeout=0.0):
            while replies:
                snapshot, parsed = replies.pop(0)
                if predicate(snapshot, parsed):
                    return snapshot, parsed
            return None

    actions = Actions()
    result = asyncio.run(capture_dm_listing(
        actions, command="sdls", label="Server disablelist",
        parse_part=parse_sdl_page, has_header=is_serverdisablelist_message, merge=merge_sdl_pages,
    ))
    assert actions.sent == ["sdls"]
    assert result.ok and result.complete and result.route == "dm"
    assert result.entries == ["'Her'", "Aiura Mikoto", "Akane Tendo", "Awesome Face", "AZKi"]


def test_sdl_aliases_and_commands():
    from macro.list_commands import plan_list_commands

    for typed in ("sdl", "sdls"):
        assert normalize_command(typed) == "serverdisablelist"
    plan = plan_list_commands("sdl", {"entries": ["Abra", "Absol", "AZKi"]})
    assert plan["clear"]["text"] == "$serverenableall"
    assert [c["text"] for c in plan["regular"]] == ["$sdc Abra$Absol$AZKi"]
    big = plan_list_commands("sdl", {"entries": [f"Character number {i:04d}" for i in range(1000)]})
    assert big["split"] and all(len(c["text"]) <= 2000 for c in big["regular"])


def test_sdl_store_and_presets():
    store = MudaeListsStore()
    store.set("sdl", "a", "c", {"used": 3, "max": 1000, "total": 3, "entries": ["Abra", "Absol", "AZKi"]})
    preset = store.save_preset("sdl", "Mine", store.get("sdl", "a", "c").data)
    assert store.add_entries("sdl", preset.id, "Acerola$abra") == 1
    again = MudaeListsStore()
    again.load_from_settings(json.loads(json.dumps(store.to_settings_fragment())))
    assert again.get("sdl", "a", "c").data["total"] == 3
    assert again.presets["sdl"][0].data["entries"] == ["Abra", "Absol", "AZKi", "Acerola"]


def test_sdl_empty_answer():
    from mudae.parsers.serverdisablelist import is_sdl_empty, merge_sdl_pages

    text = "List empty! ($serverdisable)"
    assert is_sdl_empty(text)
    for paired in ("sdl", None):
        parsed = parse_message(_dm_snapshot(text) if paired is None else SimpleNamespace(
            **{**_dm_snapshot(text).__dict__, "guild_id": 1}), reply_to_command=paired)
        assert parsed.fields["empty"] is True and parsed.fields["entries"] == []
    merged = merge_sdl_pages([parsed.fields])
    assert merged["empty"] and merged["complete"] and merged["used"] == 0


def test_sdl_dm_capture_stops_at_the_empty_answer_in_the_channel():
    from macro.listing_capture import capture_dm_listing
    from mudae.parsers.serverdisablelist import (
        is_sdl_empty, is_serverdisablelist_message, merge_sdl_pages, parse_sdl_page,
    )

    channel_reply = SimpleNamespace(**{**_dm_snapshot("List empty! ($serverdisable)").__dict__, "guild_id": 1})
    replies = [(channel_reply, None)]

    class Actions:
        async def send_command(self, command):
            pass

        async def wait_for(self, predicate, *, timeout=0.0):
            while replies:
                item = replies.pop(0)
                if predicate(*item):
                    return item
            return None

    result = asyncio.run(capture_dm_listing(
        Actions(), command="sdls", label="Server disablelist", parse_part=parse_sdl_page,
        has_header=is_serverdisablelist_message, merge=merge_sdl_pages, is_empty=is_sdl_empty,
    ))
    assert result.ok and result.complete and result.entries == []
    assert result.data["empty"] is True
