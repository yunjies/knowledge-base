"""Parse the parts of a mermaid graph the writing constraints talk about.

Two edge spellings are in active use across the corpus and both must be read:
`A -->|label| B`, and the label between the dashes as `A -- label --> B`. A
parser that knows only one silently drops half the edges, and a reachability
check over half a graph reports nodes as trapped when they are not.
"""

from __future__ import annotations

import re

# `A --> B`, `A -->|label| B`, and `A -- label --> B` all resolve to one edge.
EDGE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*"          # source
    r"--+>?\s*(?:\|([^|]*)\|\s*)?"          # `-->` or `--` plus optional |label|
    r"(?:(?<=--)([^-|>][^-]*?)\s*--+>\s*)?" # `-- label -->` form
    r"([A-Za-z_][A-Za-z0-9_]*)"             # target
)

NODE_SHAPES = {
    "terminal": re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(\["),
    "condition": re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\{"),
    "blueprint": re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[\["),
    "process": re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[(?!\[)"),
}

LABELLED = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\[|\[\[|\[|\{)\s*\"([^\"]*)\"")

GRAPH = re.compile(r"^```mermaid\s*$(.*?)^```\s*$", re.MULTILINE | re.DOTALL)


def graph_blocks(text: str) -> list[str]:
    """Every mermaid graph body in the document."""
    return GRAPH.findall(text)


def main_graph(text: str) -> str:
    """The first graph, which the document's main flow occupies."""
    blocks = graph_blocks(text)
    return blocks[0] if blocks else ""


def nodes_in(block: str) -> dict[str, set[str]]:
    """Map each identifier to the set of shapes it was declared with."""
    found: dict[str, set[str]] = {}
    for shape, pattern in NODE_SHAPES.items():
        for name in pattern.findall(block):
            found.setdefault(name, set()).add(shape)
    return found


def labels_in(block: str) -> list[str]:
    """Every human-readable label declared in the block, in order."""
    return [label for _, label in LABELLED.findall(block)]


def edges_in(block: str) -> list[tuple[str, str, str]]:
    """Every edge as (source, label, target), covering both spellings."""
    out = []
    for match in EDGE.finditer(block):
        source, piped, bare, target = match.groups()
        out.append((source, (piped or bare or "").strip(), target))
    return out


def adjacency(block: str) -> dict[str, set[str]]:
    """Each node to the nodes it can reach in one step."""
    out: dict[str, set[str]] = {}
    for source, _label, target in edges_in(block):
        out.setdefault(source, set()).add(target)
    return out


def condition_nodes(block: str) -> set[str]:
    """Nodes that branch on a decision, as opposed to fanning out or converging.

    A fork alone is not a decision: handing one input to several sub-flows, or
    gathering several outcomes before continuing, both draw as process nodes
    (`LIST_RESOURCES` in `feature-flow.md` is the first, `RUN_STOP` in
    `tests-live-layer.md` the second). What marks a condition is that the graph
    asks something there — its outgoing edges carry decision labels, or its own
    label is a question.
    """
    labels = dict(LABELLED.findall(block))
    by_source: dict[str, list[str]] = {}
    for source, label, _target in edges_in(block):
        by_source.setdefault(source, []).append(label)

    conditions = set()
    for name, edge_labels in by_source.items():
        if len(edge_labels) < 2:
            continue
        if sum(1 for label in edge_labels if label) >= 2:
            conditions.add(name)
        elif str(labels.get(name, "")).rstrip().endswith(("?", "？")):
            conditions.add(name)
    return conditions
