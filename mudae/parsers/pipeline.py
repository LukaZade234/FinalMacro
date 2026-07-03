"""Main parse pipeline for captured channel messages."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from mudae.channel_cache import remember_settings
from mudae.commands import ResolvedCommand, normalize_command, resolve_command
from mudae.parsers.bonus import parse_bonus
from mudae.parsers.classify import classify_message
from mudae.parsers.embed import is_character_embed, parse_character_embed, parse_ownership_update
from mudae.parsers.claim_interval import parse_claim_interval
from mudae.parsers.kakera import parse_kakera_claim
from mudae.parsers.claim import parse_claim
from mudae.parsers.marriage import parse_marriage
from mudae.parsers.settings import parse_settings
from mudae.parsers.sphere import parse_sphere_click
from mudae.parsers.roll import parse_roll, parse_roll_ownership
from mudae.parsers.ohu8 import parse_ohu8
from mudae.parsers.dk import parse_dk
from mudae.parsers.reaction_power import parse_kakera_react_denied, parse_ku
from mudae.parsers.tu import parse_tu
from mudae.parsers.us import parse_us
from mudae.types import MessageKind, MudaeMessageSnapshot, ParseResult

_COMMAND_PARSERS: dict[str, Callable[[str], ParseResult]] = {
    "tu": parse_tu,
    "ku": parse_ku,
    "settings": parse_settings,
    "us": parse_us,
    "ohu8": parse_ohu8,
}
_KNOWN_PARSERS = frozenset({*_COMMAND_PARSERS.keys(), "bonus", "roll"})

# GUI kind column — human-readable names for non-command message types.
_KIND_DISPLAY: dict[MessageKind, str] = {
    MessageKind.KAKERA_CLAIM: "kakera claim",
    MessageKind.DK_CLAIM: "daily kakera ($dk)",
    MessageKind.KAKERA_REACT_DENIED: "kakera react denied",
    MessageKind.SPHERE_CLICK: "sphere click",
    MessageKind.CLAIM: "claim",
    MessageKind.CLAIM_INTERVAL: "claim interval",
    MessageKind.ROLL_OWNERSHIP: "roll ownership",
    MessageKind.OWNERSHIP_UPDATE: "ownership update",
}


def _store_settings_cache(snapshot: MudaeMessageSnapshot, result: ParseResult) -> None:
    if result.fields.get("setrolls") is not None:
        remember_settings(snapshot.channel_id, result.fields)


def _run_command_parser(
    parser_id: str,
    content: str,
    *,
    snapshot: MudaeMessageSnapshot | None = None,
    part: int = 1,
    parts: int = 1,
    channel_id: int | None = None,
) -> ParseResult:
    if parser_id == "roll":
        if snapshot is None:
            raise ValueError("roll parser requires message snapshot")
        if part == 2:
            return parse_roll_ownership(snapshot)
        return parse_roll(snapshot, part=part, parts=parts)
    if parser_id == "bonus":
        return parse_bonus(
            content,
            part=part,
            parts=parts,
            channel_id=channel_id,
        )
    parser = _COMMAND_PARSERS.get(parser_id)
    if parser is None:
        raise KeyError(parser_id)
    return parser(content)


def _parse_buttons(snapshot: MudaeMessageSnapshot, kind: MessageKind) -> ParseResult:
    labels = [btn.get("label") or btn.get("emoji") or "?" for btn in snapshot.buttons]
    summary = f"{kind.value.replace('_', ' ').title()} · {', '.join(labels) or 'buttons'}"
    return ParseResult(
        kind=kind,
        summary=summary,
        fields={"buttons": snapshot.buttons},
        warnings=[],
    )


def parse_channel_message(snapshot: MudaeMessageSnapshot) -> ParseResult:
    preview = (snapshot.content or "").strip()
    if not preview and snapshot.embeds:
        preview = snapshot.embeds[0].get("author") or snapshot.embeds[0].get("title") or "(embed)"
    if len(preview) > 80:
        preview = preview[:77] + "..."
    summary = f"{snapshot.author_name}: {preview or '(empty)'}"
    return ParseResult(
        kind=MessageKind.CHANNEL,
        summary=summary,
        fields={
            "author_id": snapshot.author_id,
            "author_name": snapshot.author_name,
            "content": snapshot.content,
            "embed_count": len(snapshot.embeds),
            "button_count": len(snapshot.buttons),
        },
        warnings=[],
    )


def parse_mudae_message(
    snapshot: MudaeMessageSnapshot,
    *,
    reply_to_command: str | None = None,
    reply_part: int = 1,
    reply_parts: int = 1,
) -> ParseResult:
    resolved = resolve_command(
        reply_to_command,
        snapshot.content,
        known_parsers=_KNOWN_PARSERS,
        snapshot=snapshot,
    )
    if resolved is not None:
        resolved = replace(resolved, part=reply_part, parts=reply_parts)
    if resolved is not None and resolved.parser in _KNOWN_PARSERS:
        return _parse_command_response(snapshot, resolved)

    kind = classify_message(snapshot)

    if kind == MessageKind.BONUS:
        return parse_bonus(
            snapshot.content,
            part=reply_part,
            parts=max(reply_parts, 2),
            channel_id=snapshot.channel_id,
        )
    if kind == MessageKind.SETTINGS:
        result = parse_settings(snapshot.content)
        _store_settings_cache(snapshot, result)
        return result
    if kind == MessageKind.TU:
        return parse_tu(snapshot.content)
    if kind == MessageKind.KAKERA_REACT_DENIED:
        return parse_kakera_react_denied(snapshot.content)
    if kind == MessageKind.DK_CLAIM:
        return parse_dk(snapshot.content)
    if kind == MessageKind.KAKERA_CLAIM:
        return parse_kakera_claim(snapshot.content)
    if kind == MessageKind.SPHERE_CLICK:
        return parse_sphere_click(snapshot.content)
    if kind == MessageKind.MARRIAGE:
        return parse_marriage(snapshot.content)
    if kind == MessageKind.CLAIM:
        return parse_claim(snapshot.content)
    if kind == MessageKind.ROLL_OWNERSHIP:
        return parse_roll_ownership(snapshot)
    if kind == MessageKind.CLAIM_INTERVAL:
        return parse_claim_interval(snapshot.content)
    if kind == MessageKind.OWNERSHIP_UPDATE:
        return parse_ownership_update(snapshot)
    if kind == MessageKind.CHARACTER_EMBED and snapshot.embeds:
        return parse_character_embed(snapshot)
    if kind in {MessageKind.KAKERA_BUTTONS, MessageKind.CLAIM_BUTTONS}:
        if snapshot.embeds and is_character_embed(snapshot.embeds[0]):
            embed_result = parse_character_embed(snapshot)
            return ParseResult(
                kind=kind,
                summary=embed_result.summary,
                fields=embed_result.fields,
                warnings=embed_result.warnings,
            )
        return _parse_buttons(snapshot, kind)

    # User sent a $command we do not parse yet, but have no content match.
    if resolved is not None:
        return _parse_command_response(snapshot, resolved)

    warnings = []
    if snapshot.content:
        warnings.append("Plain text present but message type unknown")
    if snapshot.embeds:
        warnings.append("Embed present but not classified as character roll")
    return ParseResult(
        kind=MessageKind.UNKNOWN,
        summary="Unknown Mudae message",
        fields={
            "content": snapshot.content,
            "embed_count": len(snapshot.embeds),
            "button_count": len(snapshot.buttons),
        },
        warnings=warnings,
    )


def _parse_command_response(
    snapshot: MudaeMessageSnapshot,
    resolved: ResolvedCommand,
) -> ParseResult:
    label = resolved.response_label
    parser_id = resolved.parser or ""

    if parser_id in _KNOWN_PARSERS:
        result = _run_command_parser(
            parser_id,
            snapshot.content,
            snapshot=snapshot,
            part=resolved.part,
            parts=resolved.parts,
            channel_id=snapshot.channel_id,
        )
        if parser_id == "settings":
            _store_settings_cache(snapshot, result)
    else:
        kind = classify_message(snapshot)
        if kind == MessageKind.BONUS:
            result = parse_bonus(
                snapshot.content,
                part=resolved.part,
                parts=resolved.parts,
                channel_id=snapshot.channel_id,
            )
        elif kind == MessageKind.SETTINGS:
            result = parse_settings(snapshot.content)
            _store_settings_cache(snapshot, result)
        elif kind == MessageKind.TU:
            result = parse_tu(snapshot.content)
        elif kind == MessageKind.KAKERA_CLAIM:
            result = parse_kakera_claim(snapshot.content)
        elif kind == MessageKind.SPHERE_CLICK:
            result = parse_sphere_click(snapshot.content)
        elif kind == MessageKind.MARRIAGE:
            result = parse_marriage(snapshot.content)
        elif kind == MessageKind.CLAIM:
            result = parse_claim(snapshot.content)
        elif kind == MessageKind.ROLL_OWNERSHIP:
            result = parse_roll_ownership(snapshot)
        elif kind == MessageKind.CLAIM_INTERVAL:
            result = parse_claim_interval(snapshot.content)
        elif kind in {MessageKind.CHARACTER_EMBED, MessageKind.KAKERA_BUTTONS, MessageKind.CLAIM_BUTTONS}:
            result = parse_roll(snapshot)
        else:
            result = ParseResult(
                kind=MessageKind.UNKNOWN,
                summary="Unknown Mudae message",
                fields={"content": snapshot.content},
                warnings=["No parser for this command yet"],
            )

    fields = dict(result.fields)
    fields["command"] = resolved.display
    fields["response_label"] = label
    if resolved.parts > 1:
        fields["part"] = resolved.part
        fields["parts"] = resolved.parts
    if resolved.parser and resolved.parser != resolved.display:
        fields["parser_command"] = resolved.parser
    if resolved.detected and resolved.detected != resolved.display:
        fields["detected_command"] = resolved.detected
    if resolved.user_input and normalize_command(resolved.user_input) != resolved.user_input:
        fields["command_alias"] = resolved.user_input

    inner = result.summary
    display_prefix = f"${resolved.display}"
    parser_prefix = f"${resolved.parser}" if resolved.parser else None

    if inner.startswith(display_prefix):
        tail = inner[len(display_prefix) :].lstrip(" ·")
        summary = f"{label} · {tail}" if tail else label
    elif parser_prefix and inner.startswith(parser_prefix):
        tail = inner[len(parser_prefix) :].lstrip(" ·")
        summary = f"{label} · {tail}" if tail else label
    elif inner.startswith("$"):
        summary = inner
    else:
        summary = f"{label} · {inner}"

    warnings = list(result.warnings)
    if resolved.user_input and resolved.detected and resolved.parser == resolved.detected:
        if normalize_command(resolved.user_input) != resolved.detected:
            warnings.append(
                f"Typed ${resolved.user_input} but response matches ${resolved.detected}"
            )

    return ParseResult(
        kind=MessageKind.COMMAND_RESPONSE,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )


def parse_message(
    snapshot: MudaeMessageSnapshot,
    *,
    reply_to_command: str | None = None,
    reply_part: int = 1,
    reply_parts: int = 1,
) -> ParseResult:
    from mudae.command_context import extract_command

    if not snapshot.is_mudae:
        command = extract_command(snapshot.content)
        if command:
            canonical = normalize_command(command)
            fields: dict[str, Any] = {"command": command, "content": snapshot.content}
            if canonical != command:
                fields["parser_command"] = canonical
            return ParseResult(
                kind=MessageKind.COMMAND,
                summary=f"${command}",
                fields=fields,
                warnings=[],
            )
        return parse_channel_message(snapshot)

    return parse_mudae_message(
        snapshot,
        reply_to_command=reply_to_command,
        reply_part=reply_part,
        reply_parts=reply_parts,
    )


def format_entry_for_gui(
    snapshot: MudaeMessageSnapshot,
    parsed: ParseResult,
) -> dict[str, Any]:
    author_tag = "Mudae" if snapshot.is_mudae else snapshot.author_name
    kind_display = (
        parsed.fields.get("response_label")
        or _KIND_DISPLAY.get(parsed.kind)
        or parsed.kind.value
    )
    return {
        "id": str(snapshot.message_id),
        "time": snapshot.created_at,
        "channel": snapshot.channel_name,
        "author": author_tag,
        "kind": kind_display,
        "summary": parsed.summary,
        "edited": snapshot.edited,
        "rawContent": snapshot.content or "(no plain text)",
        "rawEmbeds": json.dumps(snapshot.embeds, indent=2) if snapshot.embeds else "(none)",
        "rawButtons": json.dumps(snapshot.buttons, indent=2) if snapshot.buttons else "(none)",
        "parsedFields": json.dumps(parsed.fields, indent=2, default=str),
        "warnings": "\n".join(parsed.warnings) if parsed.warnings else "(none)",
    }
