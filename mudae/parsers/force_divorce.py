"""Parse Mudae's ``$forcedivorce`` exchange.

``$forcedivorce`` is a two-step, admin-only command: Mudae asks for a plain-text
confirmation and only acts once ``y`` is sent back. Both halves matter to the
macro for different reasons.

**The prompt is a safety gate, not a formality.** It names the character and the
account that owns it::

    <@5540…>, **Lucy** belongs to <@5540…>, do you want to force the divorce?
    (y/n/yes/no)

    ⚠️ Spheres are still invested in the divorced characters until …

Because the command works on *other people's* characters too, the macro must
read that line and refuse to answer ``y`` unless both the character and the
owner are the ones it meant. Sending a blind ``y`` would divorce whatever Mudae
happened to match.

**It is not a claim.** Two bold runs is all ``claim.is_custom_claim`` asks for,
so before this module existed the prompt classified as ``MessageKind.CLAIM``
with ``winner="Lucy", character="$sphererefund"`` — which also let it satisfy
``DiscordActions.wait_for_claim``, i.e. a prompt could be mistaken for the
confirmation of a real claim.

**The success wording, confirmed from a live run on 2026-09-08**, is exactly::

    Successful divorce...

That is Mudae's whole reply — no character name, no owner, nothing else — which
is why the success test cannot key on anything but the wording itself. It stays
tolerant of a longer sentence (a "**Lucy** has been divorced" style reply) so a
Mudae wording change degrades into a re-read of ``$mmk=`` rather than a farm
that thinks every divorce failed.
"""

from __future__ import annotations

import re
from typing import Any

from mudae.parsers.utils import strip_markdown
from mudae.types import MessageKind, ParseResult

# "<@554009750375890945>, **Lucy** belongs to <@554009750375890945>,"
_PROMPT_RE = re.compile(
    r"<@!?(?P<asked>\d+)>\s*,\s*\*\*(?P<character>[^*]+)\*\*\s+belongs\s+to\s+"
    r"<@!?(?P<owner>\d+)>",
    re.IGNORECASE,
)
_CONFIRM_RE = re.compile(r"\(\s*y\s*/\s*n\b", re.IGNORECASE)
_FORCE_DIVORCE_RE = re.compile(r"force\s+the\s+divorce|forcedivorce", re.IGNORECASE)
# "Successful divorce..." is the live wording; the alternation keeps a
# reworded or translated reply readable.
_SUCCESS_RE = re.compile(r"success\w*\s+divorce|divorce\w*\s+success\w*", re.IGNORECASE)
_DIVORCED_RE = re.compile(r"\bdivorced\b", re.IGNORECASE)
_CANCEL_RE = re.compile(r"\bcancel\w*\b|\baborted\b", re.IGNORECASE)
# Mudae's refusals are not captured either; these are the shapes it uses
# elsewhere for a command the account may not run.
_REFUSED_RE = re.compile(
    r"not\s+(?:allowed|permitted)|reserved\s+(?:to|for)|no\s+permission"
    r"|administrator|couldn'?t\s+find|not\s+found|does\s+not\s+exist",
    re.IGNORECASE,
)


def is_force_divorce_prompt(content: str) -> bool:
    """The confirmation question, which must be answered ``y`` to take effect."""
    if not content:
        return False
    return bool(_FORCE_DIVORCE_RE.search(content) and _CONFIRM_RE.search(content))


def is_force_divorce_result(content: str) -> bool:
    """Mudae's answer *after* the confirmation — success, refusal or cancel."""
    if not content or is_force_divorce_prompt(content):
        return False
    if _SUCCESS_RE.search(content) or _CANCEL_RE.search(content):
        return True
    return bool(_DIVORCED_RE.search(content) and not _CONFIRM_RE.search(content))


def is_force_divorce_message(content: str) -> bool:
    return is_force_divorce_prompt(content) or is_force_divorce_result(content)


def parse_force_divorce(content: str) -> ParseResult:
    fields: dict[str, Any] = {}
    warnings: list[str] = []
    text = content or ""

    if is_force_divorce_prompt(text):
        fields["outcome"] = "prompt"
        match = _PROMPT_RE.search(text)
        if match:
            fields["character"] = strip_markdown(match.group("character")).strip()
            fields["owner_id"] = match.group("owner")
            fields["asked_id"] = match.group("asked")
        else:
            # Without the character and owner there is nothing to check the
            # prompt against, so the caller must not answer it.
            warnings.append("Could not read the character or owner from the prompt")
        character = fields.get("character") or "?"
        return ParseResult(
            kind=MessageKind.FORCE_DIVORCE_PROMPT,
            summary=f"$forcedivorce · confirm {character}?",
            fields=fields,
            warnings=warnings,
        )

    if _CANCEL_RE.search(text):
        fields["outcome"] = "cancelled"
        summary = "$forcedivorce · cancelled"
    elif _REFUSED_RE.search(text):
        fields["outcome"] = "refused"
        summary = "$forcedivorce · refused"
    elif _SUCCESS_RE.search(text) or _DIVORCED_RE.search(text):
        fields["outcome"] = "success"
        summary = "$forcedivorce · divorced"
    else:
        fields["outcome"] = "unknown"
        summary = "$forcedivorce · unrecognised reply"
        warnings.append("Unrecognised $forcedivorce reply")

    return ParseResult(
        kind=MessageKind.FORCE_DIVORCE_RESULT,
        summary=summary,
        fields=fields,
        warnings=warnings,
    )
