"""F08: a sub-flow blueprint draws its graph in its own chapter, then details it.

A node that cannot be explained without a second graph is a sub-flow: it takes
the blueprint shape, its graph is drawn inside its own chapter, and its internal
nodes each get a chapter one level deeper. The recursion has no depth limit, and
it ends where a sub-graph contains no further blueprint.

What is asserted here is the shape of that nesting — a blueprint chapter draws
exactly one graph and then details its own nodes, and every node of that graph
has a chapter beneath it.
"""

from __future__ import annotations

import re

from _harness import mermaid, paths

HEADING = re.compile(r"^(#{2,6})\s+(\S+)\s*$", re.MULTILINE)


def sections(text: str) -> list[tuple[int, str, int]]:
    """Every heading as (line index, title, depth)."""
    out = []
    for index, line in enumerate(text.split("\n")):
        match = HEADING.match(line)
        if match:
            out.append((index, match.group(2), len(match.group(1))))
    return out


def chapter_span(heads: list[tuple[int, str, int]], position: int, total: int) -> int:
    """The line where the chapter at `position` ends.

    A chapter runs until the next heading of equal or shallower depth, not until
    the next heading of any depth: a blueprint's chapter contains its sub-node
    chapters, and cutting at the first one would leave those nodes looking
    undocumented.
    """
    depth = heads[position][2]
    for index in range(position + 1, len(heads)):
        if heads[index][2] <= depth:
            return heads[index][0]
    return total


def node_shapes(text: str) -> dict[str, set[str]]:
    """Shapes of every node across all graphs in the document."""
    found: dict[str, set[str]] = {}
    for block in mermaid.graph_blocks(text):
        for name, shapes in mermaid.nodes_in(block).items():
            found.setdefault(name, set()).update(shapes)
    return found


def test_blueprint_chapters_draw_their_own_graph(repo) -> None:
    """F08: a blueprint node's chapter must carry its graph, not point elsewhere.

    The blueprint shape is what makes a node a sub-flow; a node drawn as one
    whose chapter contains no graph leaves the reader with a name and no picture.
    """
    offenders = []
    for path in paths.flow_documents():
        text = path.read_text(encoding="utf-8")
        heads = sections(text)
        lines = text.split("\n")
        blueprints = {name for name, shapes in node_shapes(text).items() if "blueprint" in shapes}
        for position, (start, title, _depth) in enumerate(heads):
            if title not in blueprints:
                continue
            end = chapter_span(heads, position, len(lines))
            body = "\n".join(lines[start:end])
            if not mermaid.graph_blocks(body):
                offenders.append(f"{paths.relative(path)}: blueprint {title} draws no graph in its chapter")
    assert offenders == [], (
        "a sub-flow must be drawn where it is described, so the reader never has to leave the "
        f"chapter to see it: {offenders}"
    )


def test_every_blueprint_graph_node_has_a_nested_chapter(repo) -> None:
    """F08: each node of a blueprint's graph gets a chapter one level deeper.

    This is F06 applied recursively. The exact depth is not asserted — the
    nesting follows the document's own structure — only that a chapter exists
    inside the blueprint's span.
    """
    offenders = []
    for path in paths.flow_documents():
        text = path.read_text(encoding="utf-8")
        heads = sections(text)
        lines = text.split("\n")
        main_titles = {"主流程图", "主流程"}
        for position, (start, title, depth) in enumerate(heads):
            # The main graph chapter holds only the graph (F02); its nodes are
            # detailed by sibling chapters, so the nesting rule does not apply.
            if title in main_titles:
                continue
            end = chapter_span(heads, position, len(lines))
            blocks = mermaid.graph_blocks("\n".join(lines[start:end]))
            if not blocks:
                continue
            own = set(mermaid.nodes_in(blocks[0]))
            if not own:
                continue
            inner = {
                name
                for index, name, inner_depth in heads
                if index > start and index < end and inner_depth > depth
            }
            missing = sorted(own - inner)
            if missing:
                offenders.append(f"{paths.relative(path)}: {title} graph nodes without a chapter: {missing}")
    assert offenders == [], (
        "each node of a sub-flow needs its own chapter beneath the blueprint, so the recursion that "
        f"starts at the main graph reaches every node: {offenders}"
    )
