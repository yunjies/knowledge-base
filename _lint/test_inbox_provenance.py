"""The inbox front block: a demand states its references before its flow.

`assets/inbox/README.md` requires every demand document to open with a YAML
block naming three things — what knowledge-base content it targets, where its
result lands, and the prompts it originated from. The block is the demand's
*reference* surface: the flow drawing below it says how the work proceeds, while
the block says what the work is about, where its result belongs, and what was
actually asked for. Nothing in the flow graph can carry those three facts, which
is why they are structured keys rather than nodes.

Two properties are checked, and they fail differently. A missing key makes the
demand's scope unreadable to the next reader. A `prompt` entry that was rewritten
rather than appended destroys the record the list exists to keep, so the list is
checked for the shape that appending preserves.

The exact placement of this block is the inbox directory's own relaxation of
F01, stated there; this file judges the block's *content*, not its position —
`test_flowdoc_prologue.py` judges position.
"""

from __future__ import annotations

import re

from _harness import paths

INBOX_PREFIX = "assets/inbox/"
REQUIRED_KEYS = ("target", "output", "prompt")

# Files in `assets/inbox/` that are not demands: the boundary statement, and the
# skeleton readers copy. The skeleton carries the same keys as a demand but with
# `<...>` placeholders, so judging it by the demand rules would report the
# template as a defective demand rather than as a template.
NON_DEMAND_FILES = {"README.md", "template.md"}

# A value consisting solely of one or more `<...>` placeholders — the shape a
# copy leaves behind when the template was never filled in.
PLACEHOLDER_ONLY = re.compile(r"^(?:<[^<>]*>\s*)+$")

# Keys at the block's top level: no indent, `name:` shape.
TOP_LEVEL_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):", re.MULTILINE)
# A list item under `prompt`, indented and dashed.
LIST_ITEM = re.compile(r"^\s+-\s+\S")


def provenance_block(text: str) -> str | None:
    """The body of the document's leading `yaml` fence, or None if absent."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip().startswith("```yaml")), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("```")), None)
    if end is None:
        return None
    return "\n".join(lines[start + 1 : end])


def inbox_documents() -> list:
    """Every demand document under `assets/inbox/`, README excluded.

    Discovered by walking rather than listed: a demand nobody registers would
    otherwise escape every check here, which is the failure mode the block is
    meant to prevent.
    """
    inbox = paths.repository_root() / "assets" / "inbox"
    if not inbox.is_dir():
        return []
    return [
        path
        for path in paths._walk(inbox)
        if path.name not in NON_DEMAND_FILES
    ]


def placeholder_values(block: str) -> list[str]:
    """Required keys whose value is still an unfilled `<...>` placeholder.

    A skeleton that was copied and never edited parses as a complete block —
    every key is present and non-empty — so nothing above would catch it. What
    distinguishes an unfilled copy is that its values are still the template's
    own placeholders, which is what this reads.

    A value that merely *contains* a placeholder alongside real text is not
    flagged: only a value that is entirely a placeholder means the author never
    filled it in.
    """
    offenders = []
    lines = block.split("\n")
    for index, line in enumerate(lines):
        match = TOP_LEVEL_KEY.match(line)
        if not match or match.group(1) not in REQUIRED_KEYS:
            continue
        value = line.split(":", 1)[1].strip()
        if not value:
            # A list: every entry must be filled in too.
            for inner in lines[index + 1 :]:
                if TOP_LEVEL_KEY.match(inner):
                    break
                if not LIST_ITEM.match(inner):
                    if inner.strip():
                        break
                    continue
                entry = inner.strip()[1:].strip()
                if PLACEHOLDER_ONLY.match(entry):
                    offenders.append(f"{match.group(1)}: {entry}")
            continue
        if PLACEHOLDER_ONLY.match(value):
            offenders.append(f"{match.group(1)}: {value}")
    return offenders


def missing_keys(block: str) -> list[str]:
    """Required keys absent from the block's top level."""
    declared = set(TOP_LEVEL_KEY.findall(block))
    return [key for key in REQUIRED_KEYS if key not in declared]


def empty_keys(block: str) -> list[str]:
    """Required keys declared with no value and no list beneath them."""
    offenders = []
    lines = block.split("\n")
    for index, line in enumerate(lines):
        match = TOP_LEVEL_KEY.match(line)
        if not match or match.group(1) not in REQUIRED_KEYS:
            continue
        value = line.split(":", 1)[1].strip()
        if value:
            continue
        # An empty scalar is legal only when the key opens a list.
        if index + 1 < len(lines) and LIST_ITEM.match(lines[index + 1]):
            continue
        offenders.append(match.group(1))
    return offenders


def prompt_items(block: str) -> list[str]:
    """The entries under `prompt`, in order."""
    lines = block.split("\n")
    start = next((i for i, line in enumerate(lines) if TOP_LEVEL_KEY.match(line) and
                  TOP_LEVEL_KEY.match(line).group(1) == "prompt"), None)
    if start is None:
        return []
    items = []
    for line in lines[start + 1 :]:
        if TOP_LEVEL_KEY.match(line):
            break
        if LIST_ITEM.match(line):
            items.append(line.strip()[1:].strip())
        elif line.strip():
            break
    return items


def test_every_demand_declares_target_output_and_prompt(repo) -> None:
    """The three reference keys must all be present and carry a value.

    A demand without `target` leaves the next reader unable to tell which part
    of the knowledge base it touches; without `output`, unable to tell where the
    result belongs. Both are unreadable from the flow graph, which is why the
    block exists.
    """
    offenders = []
    documents = inbox_documents()
    for path in documents:
        block = provenance_block(path.read_text(encoding="utf-8"))
        if block is None:
            offenders.append(f"{paths.relative(path)}: no leading yaml provenance block")
            continue
        missing = missing_keys(block)
        if missing:
            offenders.append(f"{paths.relative(path)}: missing key(s) {missing}")
        blank = empty_keys(block)
        if blank:
            offenders.append(f"{paths.relative(path)}: key(s) with no value {blank}")
        unfilled = placeholder_values(block)
        if unfilled:
            offenders.append(
                f"{paths.relative(path)}: still carrying the template's placeholders {unfilled}"
            )
    assert offenders == [], (
        "a demand must state what it targets, where its result lands, and the prompts it came "
        f"from, before its flow — with real values, not the skeleton's placeholders: {offenders}"
    )


def test_prompt_entries_are_present_and_never_rewritten(repo) -> None:
    """`prompt` must hold the originating dialogue, one entry per revision.

    The rule in the directory README is that a revision **appends** an entry: an
    existing entry is never rewritten or dropped, because the list is the
    demand's provenance and an edited provenance records nothing. What is
    decidable here is the shape that appending preserves — the list exists, and
    its entries are substantive rather than placeholders.
    """
    offenders = []
    for path in inbox_documents():
        block = provenance_block(path.read_text(encoding="utf-8"))
        if block is None:
            continue
        if "prompt" not in set(TOP_LEVEL_KEY.findall(block)):
            continue
        items = prompt_items(block)
        if not items:
            offenders.append(f"{paths.relative(path)}: prompt declares no entry")
            continue
        for entry in items:
            if len(entry) < 4:
                offenders.append(f"{paths.relative(path)}: prompt entry {entry!r} records nothing")
    assert offenders == [], (
        "prompt is the demand's provenance: it must carry at least one substantive entry, and a "
        f"revision appends rather than rewrites: {offenders}"
    )


def test_the_block_parser_reads_both_forms_and_rejects_a_thin_one() -> None:
    """The parser must find a real block and its entries, and reject a hollow one.

    Asserted over literal source so the property outlives the corpus. A parser
    that found no keys anywhere would report every document as compliant, and
    one that accepted placeholders would let an empty provenance through — the
    negative half is what makes the green mean something.
    """
    good = "target: _lint/\noutput: _lint/x.py\nprompt:\n  - 新增 format\n  - 再补一条\n"
    thin = "prompt:\n"
    assert provenance_block("```yaml\n" + good + "```\n") == good.rstrip("\n"), (
        "the parser must return the block body verbatim"
    )
    assert missing_keys(good) == [], "a complete block must report no missing key"
    assert missing_keys(thin) == ["target", "output"], (
        "a block declaring only prompt must report the other two as missing"
    )
    assert prompt_items(good) == ["新增 format", "再补一条"], "both entries must be read in order"
    assert prompt_items(thin) == [], "a prompt key with no entries must yield none"
    assert not empty_keys(good), "a fully populated block declares no empty key"
    assert empty_keys(thin) == ["prompt"], "an empty prompt scalar must be reported"

    unfilled = "target: <针对什么>\noutput: <产出在哪>\nprompt:\n  - <原话>\n"
    assert placeholder_values(unfilled), (
        "an unedited skeleton must be reported as unfilled, or a copied template reads as a demand"
    )
    assert not placeholder_values(good), "a filled-in block must report no placeholder"
    assert not placeholder_values("target: _lint/ 下的 <某文件>\noutput: 见上\nprompt:\n  - 原文\n"), (
        "a value that merely contains a placeholder alongside real text is filled in"
    )
