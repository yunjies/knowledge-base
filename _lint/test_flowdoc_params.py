"""F07: a parameter handoff must be declared by both of its ends.

F07 requires each node section to list its inputs and outputs in a fixed slot,
naming the counterpart node. That makes every declared edge checkable from the
document alone: if a producer says a parameter goes to a consumer, the consumer
must list that parameter as an input, and the reverse.

A one-sided edge is a reader-visible contradiction — the graph asserts the
handoff while the destination's section denies it — and it survives review
precisely because each section reads correctly on its own.

The check belongs here rather than in the project's suite: it reads only the
document, needs no implementation to judge, and a project checkout must stay
usable without reaching outside itself.
"""

from __future__ import annotations

import re

from _harness import paths

HEADING = re.compile(r"^(#{2,6})\s+(\S+)\s*$", re.MULTILINE)
ENTRY = re.compile(r"^\s*-\s*`([A-Za-z_][A-Za-z0-9_]*)`：(.+?)$")
NODE_REF = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")

# Two spellings are in use across the corpus and both are F07-compliant: the
# samples write `**输入**` / `**输出**`, while feature-flow.md writes
# `- 输入参数` / `- 输出参数`. A parser that knows one reads only one document
# family and reports the others as having no parameters at all.
INPUT_SLOTS = ("- 输入参数", "**输入**")
OUTPUT_SLOTS = ("- 输出参数", "**输出**")


def parse(path) -> dict[str, dict[str, dict[str, str]]]:
    """Read every node section into its declared inputs and outputs.

    A node is a heading whose title is an identifier. Parameter lines belong to
    whichever slot marker most recently appeared, so a section listing both is
    read without ambiguity rather than by guesswork about ordering.
    """
    lines = path.read_text(encoding="utf-8").split("\n")
    heads = []
    for index, line in enumerate(lines):
        match = HEADING.match(line)
        if match:
            heads.append((index, match.group(2), len(match.group(1))))

    nodes: dict[str, dict[str, dict[str, str]]] = {}
    for position, (start, name, depth) in enumerate(heads):
        # A chapter ends at the next heading of equal or shallower depth. Cutting
        # at the next heading of *any* depth would end a blueprint's chapter at
        # its first sub-node, and the blueprint's own parameter slots — which sit
        # between its graph and those sub-nodes — would never be read.
        end = len(lines)
        for index in range(position + 1, len(heads)):
            if heads[index][2] <= depth:
                end = heads[index][0]
                break
        node = {"in": {}, "out": {}}
        mode: str | None = None
        for index in range(start + 1, end):
            stripped = lines[index].strip()
            if stripped.startswith(INPUT_SLOTS):
                mode = "in"
                continue
            if stripped.startswith(OUTPUT_SLOTS):
                mode = "out"
                continue
            match = ENTRY.match(lines[index])
            if match and mode:
                node[mode][match.group(1)] = match.group(2)
        nodes[name] = node
    return nodes


def declared_edges(nodes: dict[str, dict[str, dict[str, str]]]) -> set[tuple[str, str, str]]:
    """Every declared handoff as (producer, parameter, consumer).

    Both directions are read, so an edge stated on either side is checked on
    both: an output naming a destination and an input naming a source describe
    the same handoff and must agree about the parameter name.
    """
    found: set[tuple[str, str, str]] = set()
    for name, node in nodes.items():
        for parameter, destination in node["out"].items():
            for target in NODE_REF.findall(destination):
                if target in nodes and target != name:
                    found.add((name, parameter, target))
        for parameter, source in node["in"].items():
            for origin in NODE_REF.findall(source):
                if origin in nodes and origin != name:
                    found.add((origin, parameter, name))
    return found


def gaps(nodes: dict[str, dict[str, dict[str, str]]]) -> list[str]:
    """Edges where one side names the parameter and the other does not."""
    offenders = []
    for producer, parameter, consumer in sorted(declared_edges(nodes)):
        declares_out = parameter in nodes[producer]["out"]
        declares_in = parameter in nodes[consumer]["in"]
        if declares_out and declares_in:
            continue
        missing = []
        if not declares_out:
            missing.append("producer declares no such output")
        if not declares_in:
            missing.append("consumer declares no such input")
        offenders.append(f"{producer} -{parameter}-> {consumer} ({'; '.join(missing)})")
    return offenders


def test_the_parse_finds_the_documents_parameter_sections(repo) -> None:
    """The parse must find node sections and parameter slots.

    A renamed format would leave the check matching nothing and reporting a
    consistent corpus it never read.
    """
    for path in paths.flow_documents():
        nodes = parse(path)
        assert len(nodes) > 3, (
            f"{paths.relative(path)}: the parse found only {len(nodes)} node sections; the heading "
            "pattern no longer matches and the assertions below would pass vacuously"
        )
        with_parameters = [name for name, node in nodes.items() if node["in"] or node["out"]]
        assert with_parameters, (
            f"{paths.relative(path)}: no node declares a parameter; the slot format changed and "
            "this check can no longer read it"
        )


def test_every_declared_parameter_edge_lands_on_both_sides(repo) -> None:
    """F07: a handoff carried on one side only is a contradiction.

    The criterion is the document's own — it names the counterpart node for each
    parameter — so this is not a matter of style.
    """
    offenders = []
    for path in paths.flow_documents():
        for gap in gaps(parse(path)):
            offenders.append(f"{paths.relative(path)}: {gap}")
    assert offenders == [], (
        "these parameter handoffs are declared on one side only; the graph asserts the edge while "
        f"the other section denies it: {offenders}"
    )


def test_the_criterion_fires_on_a_one_sided_edge() -> None:
    """The rule must report a handoff missing from either end.

    Stated over literals so the failure branch is exercised whatever the corpus
    contains: a criterion only ever run against a consistent corpus has never
    been shown to detect an inconsistency.
    """
    paired = {
        "A_NODE": {"in": {}, "out": {"HANDOFF": "handoff; 去向为 `B_NODE`"}},
        "B_NODE": {"in": {"HANDOFF": "handoff; 来源为 `A_NODE`"}, "out": {}},
    }
    assert gaps(paired) == [], "the paired fixture must be clean, or the cases below prove nothing"

    missing_output = {
        "A_NODE": {"in": {}, "out": {"UNRELATED": "other; 去向为 `B_NODE`"}},
        "B_NODE": {"in": {"HANDOFF": "handoff; 来源为 `A_NODE`"}, "out": {}},
    }
    found = gaps(missing_output)
    assert "A_NODE -HANDOFF-> B_NODE (producer declares no such output)" in found, (
        f"a parameter the producer omits must be reported, got: {found}"
    )

    missing_input = {
        "A_NODE": {"in": {}, "out": {"HANDOFF": "handoff; 去向为 `B_NODE`"}},
        "B_NODE": {"in": {"OTHER": "unrelated; 来源为 `A_NODE`"}, "out": {}},
    }
    found = gaps(missing_input)
    assert "A_NODE -HANDOFF-> B_NODE (consumer declares no such input)" in found, (
        f"a parameter the consumer omits must be reported, got: {found}"
    )
