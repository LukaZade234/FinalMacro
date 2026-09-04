"""Tests for the `$wlz+z!` / `$wlsz+z!` wishlist listing parser.

Rows are taken verbatim from a real listing, because the awkward parts are all
in real names — a leading digit (`2B`), dots (`C.C.`), an apostrophe and
parentheses (`Jeanne d'Arc (Alter)`), a macron (`Yoruichi Shihōin`), an accent
(`Chloé D'Apchier`) — plus Mudae's own inconsistent bolding, which lands
mid-row as often as around the name.
"""

from __future__ import annotations

from mudae.parsers.wishlist import (
    is_wishlist_message,
    merge_wishlist_pages,
    parse_upgrades,
    parse_wishlist_page,
    parse_wishlist_row,
)

_HEADER = "lukazade234's Wishlist - 160/162 $wl, 16/16 $sw"

_PAGE_ONE = f"""{_HEADER}

Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full
Reze ✅ ⭐ 🔐 +313% · 30,000 sp - Full
Nazuna Nanakusa ✅ 🔐 +125% · 7,000 sp - 5 (x5), 6, 8, 9, 10
Shizuku Murasaki ✅ 🔐 · 7,000 sp - 5 (x5), 6, 8, 9, 10
Page 1 / 8"""


def test_header_gives_the_wishlist_sizes():
    """The `$bw` optimum's missing input — nothing else in the app has it."""
    fields = parse_wishlist_page(_PAGE_ONE)
    assert fields["owner"] == "lukazade234"
    assert (fields["wl_used"], fields["wl_max"]) == (160, 162)
    assert (fields["sw_used"], fields["sw_max"]) == (16, 16)


def test_page_footer_is_read_and_absent_in_a_dm():
    assert parse_wishlist_page(_PAGE_ONE)["page"] == 1
    assert parse_wishlist_page(_PAGE_ONE)["pages"] == 8
    dm = f"{_HEADER}\n\nRebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full"
    assert parse_wishlist_page(dm)["page"] is None


def test_starwish_row():
    row = parse_wishlist_row("Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full")
    assert row == {
        "name": "Rebecca",
        "starwish": True,
        "sphere_percent": 188,
        "spheres": 30000,
        "upgrades_full": True,
        "upgrades": {},
    }


def test_plain_row_without_a_percent():
    row = parse_wishlist_row("Shizuku Murasaki ✅ 🔐 · 7,000 sp - 5 (x5), 6, 8, 9, 10")
    assert row["starwish"] is False
    assert row["sphere_percent"] is None
    assert row["spheres"] == 7000
    assert row["upgrades"] == {5: 5, 6: 1, 8: 1, 9: 1, 10: 1}
    assert row["upgrades_full"] is False


def test_awkward_real_names_survive():
    cases = {
        "2B ✅ ⭐ 🔐 +313% · 30,000 sp - Full": "2B",
        "C.C. ✅ 🔐 · 7,000 sp - 5 (x5), 6": "C.C.",
        "Jeanne d'Arc (Alter) ✅ 🔐 · 7,000 sp - 5 (x5)": "Jeanne d'Arc (Alter)",
        "Yoruichi Shihōin ✅ 🔐 · 7,000 sp - 5 (x5)": "Yoruichi Shihōin",
        "Chloé D'Apchier ✅ 🔐 · 7,000 sp - 5 (x5)": "Chloé D'Apchier",
        "Zero (HCLW) ✅ 🔐 · 7,000 sp - 5 (x5)": "Zero (HCLW)",
        "Susie (LoM) ✅ 🔐 · 7,000 sp - 5 (x5)": "Susie (LoM)",
    }
    for line, expected in cases.items():
        assert parse_wishlist_row(line)["name"] == expected, line


def test_bold_is_stripped_wherever_mudae_put_it():
    """Mudae bolds some rows and not others, and mid-row at that."""
    bolded = parse_wishlist_row(
        "**Evil Neuro** ✅ 🔐 · **9,000** sp - **5** (x6), **6**, **8**, **9**, **10**"
    )
    plain = parse_wishlist_row("Evil Neuro ✅ 🔐 · 9,000 sp - 5 (x6), 6, 8, 9, 10")
    assert bolded == plain
    assert bolded["spheres"] == 9000
    assert bolded["upgrades"][5] == 6


def test_multiplicity_and_full():
    assert parse_upgrades("Full") == {"full": True, "perks": {}}
    assert parse_upgrades("4 (x2), 5 (x5), 6, 8, 9, 10") == {
        "full": False,
        "perks": {4: 2, 5: 5, 6: 1, 8: 1, 9: 1, 10: 1},
    }


def test_non_wishlist_lines_are_not_rows():
    assert parse_wishlist_row("") is None
    assert parse_wishlist_row("Page 1 / 8") is None
    assert parse_wishlist_row(_HEADER) is None
    assert parse_wishlist_row("You have 3 rolls left.") is None
    assert parse_wishlist_row("· 7,000 sp - 5") is None  # no name


def test_is_wishlist_message_covers_a_headerless_continuation():
    """Later DM parts carry rows only — the header arrives once."""
    assert is_wishlist_message(_PAGE_ONE) is True
    assert is_wishlist_message("Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full") is True
    assert is_wishlist_message("$tu\nYou have 3 rolls left.") is False


def test_merge_joins_parts_and_dedupes_by_name():
    first = parse_wishlist_page(_PAGE_ONE)
    second = parse_wishlist_page(
        "Rebecca ✅ ⭐ 🔐 +188% · 30,000 sp - Full\n"  # repeat, e.g. paged back
        "Ado ✅ ⭐ 🔐 +188% · 30,000 sp - Full\n"
        "Page 2 / 8"
    )
    merged = merge_wishlist_pages([first, second])
    names = [entry["name"] for entry in merged["entries"]]
    assert names == ["Rebecca", "Reze", "Nazuna Nanakusa", "Shizuku Murasaki", "Ado"]
    assert merged["wl_used"] == 160  # carried from the part that had a header
    assert merged["seen_pages"] == [1, 2]


def test_merge_reports_incomplete_until_every_row_arrived():
    """A listing cut short must be visibly incomplete, not silently short."""
    short = parse_wishlist_page(_PAGE_ONE)
    assert merge_wishlist_pages([short])["complete"] is False

    tiny_header = "someone's Wishlist - 2/5 $wl, 0/3 $sw"
    full = parse_wishlist_page(
        f"{tiny_header}\n"
        "Rem ✅ 🔐 · 7,000 sp - 5 (x5)\n"
        "Emilia ✅ 🔐 · 7,000 sp - 5 (x5)"
    )
    assert merge_wishlist_pages([full])["complete"] is True


def test_merge_falls_back_to_page_coverage_without_a_header():
    parts = [
        parse_wishlist_page("Rem ✅ 🔐 · 7,000 sp - 5 (x5)\nPage 1 / 2"),
        parse_wishlist_page("Emilia ✅ 🔐 · 7,000 sp - 5 (x5)\nPage 2 / 2"),
    ]
    merged = merge_wishlist_pages(parts)
    assert merged["complete"] is True
    assert merge_wishlist_pages(parts[:1])["complete"] is False


def test_starwishes_are_a_subset_of_the_wl_count():
    """16 starred rows against ``16/16 $sw`` inside ``160/162 $wl``.

    Pinned because the ``$bw`` maths depends on whether starwishes are extra
    slots or the same ones: 160 rows over 8 pages of 20 says they are the same.
    """
    fields = parse_wishlist_page(_PAGE_ONE)
    starred = [entry for entry in fields["entries"] if entry["starwish"]]
    assert len(starred) == 2  # in this excerpt
    assert fields["sw_used"] <= fields["wl_used"]


def test_classifier_routes_a_wishlist_page_and_not_to_claim():
    """A page of bold names is exactly what the claim heuristic misfires on."""
    from types import SimpleNamespace

    from mudae.parsers.classify import classify_message
    from mudae.types import MessageKind

    bolded = (
        "**Rem** ✅ 🔐 · **7,000** sp - **5** (x5), **6**\n"
        "**Emilia** ✅ 🔐 · **7,000** sp - **5** (x5), **6**"
    )
    snapshot = SimpleNamespace(
        content=bolded,
        embeds=[],
        buttons=[],
        components=[],
        edited=False,
        is_mudae=True,
        channel_id=1,
    )
    assert classify_message(snapshot) == MessageKind.WISHLIST


def test_wishlist_never_reaches_the_run_feed():
    """The feed mirrors channel events, not a listing the macro asked for."""
    from mudae.live_feed import format_live_feed
    from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

    snapshot = MudaeMessageSnapshot(
        message_id=1,
        channel_id=1,
        channel_name="mudae",
        guild_id=1,
        guild_name="g",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content="lukazade234's Wishlist - 160/162 $wl, 16/16 $sw",
        embeds=[],
        buttons=[],
        created_at="12:00:00",
        edited=False,
        components=[],
    )
    parsed = ParseResult(
        kind=MessageKind.WISHLIST, summary="$wl", fields={}, warnings=[]
    )
    assert format_live_feed(snapshot, parsed, own_usernames=["lukazade234"]) is None


# --- The channel reply is an embed, not plain text --------------------------
#
# Taken from a real captured `$wlz+z!` reply (Debug → save). The DM route
# worked from the start and this one did not, because the channel form carries
# no message content at all: the header is the embed's author, the rows its
# description, and `Page 1 / 8` its footer.

_CHANNEL_FIXTURE = (
    __import__("pathlib").Path(__file__).parent / "fixtures" / "wlz_channel_page.json"
)


def _channel_snapshot():
    import json
    from types import SimpleNamespace

    raw = json.loads(_CHANNEL_FIXTURE.read_text(encoding="utf-8"))
    return SimpleNamespace(
        message_id=100000000000000001,
        channel_id=1,
        channel_name="mudae-w",
        guild_id=1,
        guild_name="g",
        author_id=1,
        author_name="Mudae",
        is_mudae=True,
        content=raw["content"],
        embeds=raw["embeds"],
        buttons=raw["buttons"],
        created_at="16:51:02",
        edited=False,
        components=raw["components"],
    )


def test_channel_page_has_no_content_at_all():
    """The premise of the bug: reading `content` alone finds nothing."""
    snapshot = _channel_snapshot()
    assert snapshot.content == ""
    assert parse_wishlist_page(snapshot.content)["entries"] == []


def test_channel_embed_parses_through_the_pipeline():
    from mudae.parsers.pipeline import parse_message
    from mudae.types import MessageKind

    result = parse_message(_channel_snapshot())

    assert result.kind == MessageKind.WISHLIST
    assert len(result.fields["entries"]) == 20
    assert (result.fields["page"], result.fields["pages"]) == (1, 8)
    assert (result.fields["wl_used"], result.fields["wl_max"]) == (160, 162)
    assert result.fields["entries"][0]["name"] == "Rebecca"
    assert result.fields["entries"][0]["starwish"] is True


def test_channel_page_is_not_mistaken_for_a_roll():
    """Its paging arrows have claim-shaped custom ids, so it parsed as a roll.

    That is worse than the capture failing: a wishlist page came out with
    `can_claim: true` and a character name taken from the header.
    """
    from mudae.parsers.classify import classify_message
    from mudae.types import MessageKind

    snapshot = _channel_snapshot()
    assert classify_message(snapshot) == MessageKind.WISHLIST
    # The buttons really do look like claim buttons — that is the trap.
    assert [b["kind"] for b in snapshot.buttons] == ["claim", "claim"]


def test_forward_button_found_despite_the_claim_kind():
    from macro.wishlist_capture import _forward_button

    snapshot = _channel_snapshot()
    forward = _forward_button(snapshot)
    expected = next(b["custom_id"] for b in snapshot.buttons if b["emoji"] == "wright")
    assert forward == expected
