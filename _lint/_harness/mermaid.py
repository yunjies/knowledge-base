"""Parse the parts of a mermaid graph the writing constraints talk about.

Two edge spellings are in active use across the corpus and both must be read:
`A -->|label| B`, and the label between the dashes as `A -- label --> B`. A
parser that knows only one silently drops half the edges, and a reachability
check over half a graph reports nodes as trapped when they are not.

Node discovery is **additive** over two sources. Shape syntax (`A([...])`,
`A{...}`, `A[[...]]`, `A[...]`) declares a node and its role, and it is what
the shape-dependent constraints read. An edge declares its endpoints as nodes
too, and mermaid draws them: `A --> B` renders both `A` and `B` as nodes even
when neither was ever given a shape. Reading only the shapes leaves such a node
invisible to every constraint, so a graph can carry an unlabelled, unstyled,
unreachable node that no check ever sees — which is why both ends of every edge
are folded in here.

Both ends, not just the targets: `X --> Y` makes `X` a node just as much as
`Y`, and in `X --> Y --> Z` the head `X` is nothing but a source. Reading
targets alone leaves `X` invisible whenever it carries no shape.

Discovery runs over `structure_only` and reads solid and dotted arrows alike, so
a label or a comment cannot donate a node and a dotted edge cannot hide one.
`edges_in` deliberately stays on the narrower `prose_free`: its labels are part
of what it reports, and blanking them would move the constraints that read edges.
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

# `%% ...` to end of line: a mermaid comment, and not part of the graph.
COMMENT = re.compile(r"%%.*$", re.MULTILINE)

# `::: class` — an inline style assignment attached to a node.
INLINE_CLASS = re.compile(r":::+\s*[A-Za-z_][A-Za-z0-9_]*")

# A quoted string: a node's display label or an edge's label. It is text the
# author wrote for a reader, never graph structure, but it may contain anything —
# `B["X --> Y"]` is a legitimate label naming no nodes at all.
QUOTED = re.compile(r'"[^"]*"')

# A dotted edge and the identifiers on both sides: `A -.-> B`, and the piped
# `A -.->|label| B`. The source may carry a shape suffix (`A(["a"]) -.-> B`), so
# the shape is allowed for and skipped. Read for node discovery only — see
# `dashed_endpoints`.
DASHED_ENDS = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*"          # source
    r"(?:\(\[[^\]]*\]\)|\[\[[^\]]*\]\]|\[[^\]]*\]|\{[^}]*\})?\s*"  # optional shape
    r"-\.+->?\s*"                           # `-.->`, `-.-`, `-.>`
    r"(?:\|[^|]*\|\s*)?"                    # optional |label|
    r"([A-Za-z_][A-Za-z0-9_]*)"             # target
)


def prose_free(block: str) -> str:
    """The block with the parts that are not graph structure removed.

    A mermaid comment may contain anything at all, arrows included: prose such as
    `%% explain how X --> Y resolves` reads as an edge to a parser that scans the
    raw text, which turns the words into phantom nodes. Those phantoms then fail
    constraints that the real graph satisfies, so a correctly written document
    reports red for a sentence in a comment. Inline `:::` styling is stripped for
    the same reason: its class name is not a node.

    Stripping happens before any regex reads the block, so edge and node
    discovery agree about what the graph contains.
    """
    return INLINE_CLASS.sub(" ", COMMENT.sub("", block))


def structure_only(block: str) -> str:
    """The block with quoted labels blanked as well as prose stripped.

    A label is display text, so it may hold anything — `B["X --> Y"]` is a
    legitimate node whose label mentions an arrow, and reading that text as an
    edge invents two nodes that the graph does not draw. Blanking the quoted
    spans removes that whole class of phantom rather than enumerating the noise
    that happens to appear today.

    Used for **node** discovery only. An edge's label is quoted too, and
    `edges_in` reports it, so blanking quotes there would replace every label
    with an empty string and change what the edge-reading constraints see. Node
    discovery has no such coupling: it asks which identifiers the graph draws,
    and a label is never one.

    The seam this leaves: `edges_in` still reads a quoted label as text, so a
    label containing an arrow yields a phantom edge. That is harmless today —
    the only reader of edges is the reachability check, which walks the node set,
    and a phantom node is not in it. It would stop being harmless if `edges_in`
    were switched to this function while some other check started reading edges
    without intersecting them against `nodes_in`.
    """
    return QUOTED.sub('""', prose_free(block))


def dashed_endpoints(block: str) -> set[str]:
    """Identifiers joined by a dotted arrow, which `EDGE` does not read.

    Mermaid spells a dotted edge `-.->`, and the corpus uses it — the demand
    template draws its blocking exit that way. `EDGE` matches the solid forms
    only, so a dotted edge contributes no endpoint and a bare dotted node stays
    invisible to node discovery.

    Read here rather than by widening `EDGE`: `edges_in` feeds reachability and
    the condition-role checks, where a changed edge set moves results that are
    already correct. Node discovery only asks which identifiers the graph draws,
    so it can take these endpoints without touching what `edges_in` reports.
    """
    ends: set[str] = set()
    for source, target in DASHED_ENDS.findall(structure_only(block)):
        ends.add(source)
        ends.add(target)
    return ends


def graph_blocks(text: str) -> list[str]:
    """Every mermaid graph body in the document."""
    return GRAPH.findall(text)


def main_graph(text: str) -> str:
    """The first graph, which the document's main flow occupies."""
    blocks = graph_blocks(text)
    return blocks[0] if blocks else ""


def nodes_in(block: str) -> dict[str, set[str]]:
    """Map each identifier to the set of shapes it was declared with.

    A node introduced only by an edge carries the empty set: it is drawn by
    mermaid, so it must be visible to the constraints, but it has no shape of
    its own for a shape-dependent constraint to read.

    Read over `structure_only`, so a label's text cannot masquerade as a node.
    """
    block = structure_only(block)
    found: dict[str, set[str]] = {}
    for shape, pattern in NODE_SHAPES.items():
        for name in pattern.findall(block):
            found.setdefault(name, set()).add(shape)
    for match in EDGE.finditer(block):
        found.setdefault(match.group(1), set())
        found.setdefault(match.group(4), set())
    for name in dashed_endpoints(block):
        found.setdefault(name, set())
    return found


def labels_in(block: str) -> list[str]:
    """Every human-readable label declared in the block, in order."""
    return [label for _, label in LABELLED.findall(prose_free(block))]


def edges_in(block: str) -> list[tuple[str, str, str]]:
    """Every edge as (source, label, target), covering both spellings."""
    out = []
    for match in EDGE.finditer(prose_free(block)):
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
    labels = dict(LABELLED.findall(prose_free(block)))
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
