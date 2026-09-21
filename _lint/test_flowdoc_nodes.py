"""F03, F04 and F06: node naming, node shape, and node-to-chapter coverage.

F03 requires each node to carry an English identifier and a separate
human-readable label, with labels unique within one graph. F04 requires the
shape to follow the node's *role in the graph* — a node that branches on a
decision is a condition, whatever its text says. F06 requires every node of the
main graph to have exactly one chapter named after it.

F05, F07 and F08 live in their own files: they assert different properties of
the same graphs, and a failure in one must not be reported as a failure of
another.
"""

from __future__ import annotations

import re

from _harness import mermaid, paths

HEADING = re.compile(r"^(#{2,6})\s+(\S+)\s*$", re.MULTILINE)


def test_every_node_identifier_is_an_english_token(repo) -> None:
    """F03: an identifier must be self-sufficient as an English token.

    A name like `N3` or `A1` tells a reader nothing once the graph is out of
    sight; `CHECK_TOKEN` does. This is the decidable half of F03's
    self-sufficiency criterion; the other half — whether the token is *apt* —
    is judgement and is listed as such in the suite's README.
    """
    offenders = []
    for path in paths.flow_documents():
        for index, block in enumerate(mermaid.graph_blocks(path.read_text(encoding="utf-8")), start=1):
            for name in mermaid.nodes_in(block):
                if len(name) < 3 or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                    offenders.append(f"{paths.relative(path)} graph {index}: identifier {name!r}")
    assert offenders == [], (
        "every node identifier must carry enough meaning to be read outside its graph; short "
        f"positional names do not: {offenders}"
    )


def test_labels_are_unique_within_a_graph(repo) -> None:
    """F03: a label must identify exactly one node in its graph.

    Uniqueness is scoped to one graph; two graphs may each carry a `START`.
    """
    offenders = []
    for path in paths.flow_documents():
        for index, block in enumerate(mermaid.graph_blocks(path.read_text(encoding="utf-8")), start=1):
            seen: dict[str, int] = {}
            for label in mermaid.labels_in(block):
                seen[label] = seen.get(label, 0) + 1
            for label, count in sorted(seen.items()):
                if count > 1:
                    offenders.append(f"{paths.relative(path)} graph {index}: {label!r} used {count} times")
    assert offenders == [], (
        "within one graph a label must resolve to a single node, otherwise a reference to it is "
        f"ambiguous to the reader: {offenders}"
    )


def test_decision_nodes_take_the_condition_shape(repo) -> None:
    """F04: a node the graph branches on must be drawn as a condition.

    The role is decided by the graph, not by the label's wording: a node whose
    outgoing edges each carry a decision label is a condition even if its text
    never says so, and a node reading "判断" that fans out to independent
    sub-flows is a process node.
    """
    offenders = []
    for path in paths.flow_documents():
        for index, block in enumerate(mermaid.graph_blocks(path.read_text(encoding="utf-8")), start=1):
            declared = mermaid.nodes_in(block)
            for name in sorted(mermaid.condition_nodes(block)):
                shapes = declared.get(name, set())
                if shapes and "condition" not in shapes:
                    offenders.append(
                        f"{paths.relative(path)} graph {index}: {name} branches but is drawn as {sorted(shapes)}"
                    )
    assert offenders == [], (
        "a node the graph branches on is read as a decision, so its shape must say so regardless of "
        f"its label: {offenders}"
    )


def test_condition_shaped_nodes_actually_branch(repo) -> None:
    """F04, the other direction: a condition shape must carry a real branch.

    A node drawn as a question that never forks contradicts its own shape, and
    the reader is left looking for a branch that is not there. Both directions
    are asserted so that neither shape can drift from its role unnoticed.
    """
    offenders = []
    for path in paths.flow_documents():
        for index, block in enumerate(mermaid.graph_blocks(path.read_text(encoding="utf-8")), start=1):
            declared = mermaid.nodes_in(block)
            branching = mermaid.condition_nodes(block)
            for name, shapes in sorted(declared.items()):
                if "condition" in shapes and name not in branching:
                    offenders.append(
                        f"{paths.relative(path)} graph {index}: {name} is drawn as a condition but does not branch"
                    )
    assert offenders == [], (
        f"a node drawn as a decision must have a branch for the reader to follow: {offenders}"
    )


def test_every_main_graph_node_has_a_chapter(repo) -> None:
    """F06: coverage — every node of the main graph has a chapter.

    Chapters at any depth count, because F08 puts a blueprint's sub-nodes in
    nested chapters. Only the missing direction is asserted: an extra chapter
    may legitimately document something outside the main graph.
    """
    offenders = []
    for path in paths.flow_documents():
        text = path.read_text(encoding="utf-8")
        declared = set(mermaid.nodes_in(mermaid.main_graph(text)))
        chapters = {name for _, name in HEADING.findall(text)}
        missing = sorted(declared - chapters)
        if missing:
            offenders.append(f"{paths.relative(path)}: nodes without a chapter: {missing}")
    assert offenders == [], (
        "every node of the main graph needs its own chapter stating what it does and which way it "
        f"leaves; a node without one is undocumented: {offenders}"
    )
