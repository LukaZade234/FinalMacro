"""Parse Mudae ``$ov`` — the player's own settings sheet.

Same bullet grammar as ``$settings`` (``· Label: **value** ($command)``) for a
different subject: what *this account* has configured, wherever it rolls. The
parser is separate rather than a flag on ``parse_settings`` for one structural
reason — ``$ov`` prints three different toggles under a single ``($rdmimg)``
suffix, so a field cannot be identified by its command alone. Identity comes
from :mod:`mudae.parsers.ov_catalog`, which resolves a line by its command when
that is unique and by its printed label when it is not.

Never sent automatically. ``docs/TODO.md`` is explicit that ``$ov`` goes out
only when a person asks for it, which in the app means clicking Fetch ``$ov`` on
the Mudae page's scope bar.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.ov_catalog import (
    MEANING_BY_LABEL,
    format_persrare,
    MEANINGS_BY_COMMAND,
    OV_FIELD_KEYS,
    empty_ov_fields,
    normalize_label,
)
from mudae.types import MessageKind, ParseResult

_BULLET_RE = re.compile(r"^[·•]\s*(.+)$", re.MULTILINE)
_CMD_SUFFIX_RE = re.compile(r"\(\$([^)]+)\)\s*$")
_SEE_CMD_RE = re.compile(r"\bsee\s+\$([a-z0-9]+)", re.IGNORECASE)
_PREMIUM_RE = re.compile(r"player premium\s*(\d+)", re.IGNORECASE)
_MARKDOWN_RE = re.compile(r"\*\*([^*]*)\*\*|__([^_]*)__")
_INT_RE = re.compile(r"\d+")
_FLAGS_RE = re.compile(r"^[ynYN](?:\s+[ynYN])+$")
# ``$persrare`` prints a multiplier: ``x2``, ``x10``. One is not printed as
# ``x1`` — Mudae writes ``none``, because a multiplier of one has no effect.
_PERSRARE_MULT_RE = re.compile(r"^x?\s*(\d+)$", re.IGNORECASE)

# What ``$persrare`` reads as at its lowest setting. Mudae calls one "none"
# rather than "x1": the value *is* one, and one has no effect.
PERSRARE_OFF_WORDS = frozenset({"none", "disabled", "off", "no"})


def is_ov_response(content: str) -> bool:
    """Mudae's player-settings sheet.

    Deliberately narrow. Without the ``($persrare)`` / ``($wishdm)`` check the
    header alone would also match anyone quoting the sheet, and the sheet is a
    wall of bold text — which ``mudae.parsers.claim.is_custom_claim`` reads as a
    claim, the way this message was in fact classified before this parser
    existed.
    """
    if not content:
        return False
    lower = content.lower()
    if "player settings" not in lower:
        return False
    return "($persrare)" in lower or "($wishdm)" in lower


def parse_persrare(raw: str) -> int | None:
    """``none`` -> 1, ``x2`` -> 2. ``None`` when the wording is unfamiliar.

    ``$persrare`` is a **multiplier**, not a count of extra tries, and its
    lowest setting prints as ``none`` rather than ``x1`` because multiplying by
    one changes nothing. So one is a real value here, not a missing one — which
    is why an unfetched ``$ov`` and a fetched one reading ``none`` give the `$bw`
    sweep the same answer by different routes.
    """
    text = str(raw or "").strip().lower()
    if not text:
        return None
    if text in PERSRARE_OFF_WORDS:
        return 1
    match = _PERSRARE_MULT_RE.match(text)
    if match:
        return max(int(match.group(1)), 1)
    return None


def persrare_rerolls(value: Any) -> int | None:
    """A stored ``persrare`` field as the `$bw` sweep's ``N``, or ``None``.

    The parser normalises the line to an int, so this is usually the identity.
    It still accepts the printed forms, because a sheet stored before that
    normalisation holds the raw text, and because a caller that gets ``None``
    is meant to keep the user's own value and say why rather than guess.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number >= 1 else None
    return parse_persrare(str(value))


def _strip_markdown(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return match.group(1) or match.group(2) or ""

    return _MARKDOWN_RE.sub(repl, text).replace("****", "").strip()


def _label_and_value(body: str) -> tuple[str, str]:
    if ":" in body:
        label, value = body.split(":", 1)
        return label.strip(), _strip_markdown(value.strip())
    return body.strip(), ""


def _coerce_value(key: str, raw: str) -> Any:
    text = raw.strip()
    lower = text.lower()
    # Before the enabled/disabled test: ``$persrare`` prints ``none``, which
    # that test would otherwise never see, and its own "off" word is a *value*
    # of one rather than a false.
    if key == "persrare":
        return parse_persrare(text) or text
    if lower in {"enabled", "yes"}:
        return True
    if lower in {"disabled", "no"}:
        return False
    # ``$wishdm`` prints one letter per wish kind ("n  n  n"), which is a row of
    # flags rather than a single value — keep the parts.
    if _FLAGS_RE.match(text):
        return [part.lower() for part in text.split()]
    if key == "player_premium" and _INT_RE.fullmatch(text):
        return int(text)
    return text


def _resolve(command: str, label: str, taken: set[str]) -> tuple[str | None, str]:
    """Which field a bullet is, and a warning if that took guessing."""
    by_label = MEANING_BY_LABEL.get(normalize_label(label))
    candidates = MEANINGS_BY_COMMAND.get(command.lower(), ())
    if by_label is not None:
        # A label that names a different command than the line carries means the
        # sheet has been reworded under us; the label is the more specific of
        # the two, so it wins, but not quietly.
        if candidates and by_label not in candidates:
            return by_label.key, (
                f"$ov line labelled {label!r} carries (${command}), "
                f"expected ({by_label.command})"
            )
        return by_label.key, ""
    if len(candidates) == 1:
        return candidates[0].key, ""
    if len(candidates) > 1:
        # Several toggles share this command and the label is not one we know.
        # They print in a fixed order, so fill the next free slot rather than
        # dropping the line — and say that it was positional.
        for meaning in candidates:
            if meaning.key not in taken:
                return meaning.key, (
                    f"Unknown $ov label {label!r} for (${command}); "
                    f"read positionally as {meaning.key}"
                )
    return None, ""


def parse_ov(content: str) -> ParseResult:
    warnings: list[str] = []
    fields = empty_ov_fields()
    taken: set[str] = set()

    premium = _PREMIUM_RE.search(content or "")
    if premium:
        fields["player_premium"] = int(premium.group(1))
        taken.add("player_premium")

    parsed_lines = 0
    for match in _BULLET_RE.finditer(content or ""):
        line = match.group(1).strip()
        cmd_match = _CMD_SUFFIX_RE.search(line)
        if cmd_match:
            command = cmd_match.group(1).split()[0].lstrip("$")
            body = line[: cmd_match.start()].strip()
        else:
            # "Character pool limits: see $limroul" — the command is the value.
            see = _SEE_CMD_RE.search(line)
            if not see:
                warnings.append(f"Unparsed $ov line: {line[:120]}")
                continue
            command = see.group(1)
            body = line

        label, raw_value = _label_and_value(body)
        key, warning = _resolve(command, label, taken)
        if warning:
            warnings.append(warning)
        if key is None:
            warnings.append(f"Unknown $ov setting ${command}: {label[:80]}")
            continue

        value = _coerce_value(key, raw_value) if raw_value else f"see ${command}"
        if key in taken and fields.get(key) != value:
            warnings.append(f"Duplicate $ov setting {key!r}; keeping first value")
            continue
        fields[key] = value
        taken.add(key)
        parsed_lines += 1

    if parsed_lines == 0:
        warnings.append("No $ov bullet lines matched")

    return ParseResult(
        kind=MessageKind.OV,
        summary=_build_summary(fields),
        fields=fields,
        warnings=warnings,
    )


def _build_summary(fields: dict[str, Any]) -> str:
    parts: list[str] = ["$ov"]
    if fields.get("player_premium") is not None:
        parts.append(f"Premium {fields['player_premium']}")
    persrare = fields.get("persrare")
    if persrare is not None:
        parts.append(f"$persrare {format_persrare(persrare)}")
    known = sum(1 for key in OV_FIELD_KEYS if fields.get(key) is not None)
    parts.append(f"{known}/{len(OV_FIELD_KEYS)} fields")
    return " · ".join(parts)
