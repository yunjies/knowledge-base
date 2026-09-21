"""F05: cycles are allowed, but every node must still reach a completion node.

A retry, a poll or a rollback is a legitimate back-edge. What the rule forbids
is a node that can only go round: a cycle with no exit, or a dead end with no
outgoing edge at all. For each node the check walks the outgoing edges and asks
whether any completion node is reachable.
"""

from __future__ import annotations

from _harness import mermaid, paths


def completion_nodes(block: str) -> set[str]:
    """The nodes drawn as terminals: a start or an end.

    Both count. The rule asks that a node can reach *a* completion node, and a
    start node is one — a graph does not require every path to end at an end
    node, only that no node is trapped.
    """
    return {name for name, shapes in mermaid.nodes_in(block).items() if "terminal" in shapes}


def reaches_completion(node: str, adjacency: dict[str, set[str]], completions: set[str]) -> bool:
    """Report whether `node` can reach a completion node along the directed edges."""
    seen: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current in completions:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, ()))
    return False


def test_every_node_reaches_a_completion_node(repo) -> None:
    """F05: no node may be trapped in a cycle or stranded without an exit.

    The traversal follows directed edges and tolerates revisits, so a cycle that
    carries an exit passes and a cycle that does not is caught. A node with no
    outgoing edge fails the same way.
    """
    offenders = []
    for path in paths.flow_documents():
        for index, block in enumerate(mermaid.graph_blocks(path.read_text(encoding="utf-8")), start=1):
            adjacency = mermaid.adjacency(block)
            completions = completion_nodes(block)
            if not completions:
                offenders.append(f"{paths.relative(path)} graph {index}: has no completion node")
                continue
            for name in sorted(mermaid.nodes_in(block)):
                if not reaches_completion(name, adjacency, completions):
                    offenders.append(f"{paths.relative(path)} graph {index}: {name}")
    assert offenders == [], (
        "every node must be able to reach a completion node; a cycle with an exit is fine, a node "
        f"that can only go round or that stops with no way out is not: {offenders}"
    )


def test_the_traversal_accepts_a_cycle_with_an_exit_and_rejects_one_without() -> None:
    """The rule must separate an escapable cycle from a closed one.

    Stated over literal graphs so the failure branch is exercised whatever the
    documents currently contain: a rule only ever run against well-formed graphs
    has never been shown to catch a trapped node.
    """
    escapable = '\n'.join([
        'START(["起"]) --> TRY["试"]',
        'TRY --> JUDGE{"可退？"}',
        'JUDGE -- 否 --> TRY',
        'JUDGE -- 是 --> STOP(["止"])',
    ])
    assert reaches_completion("TRY", mermaid.adjacency(escapable), completion_nodes(escapable)), (
        "a retry loop that can leave through its exit must be accepted"
    )

    closed = '\n'.join([
        'START(["起"]) --> TRY["试"]',
        'TRY --> JUDGE{"可退？"}',
        'JUDGE -- 否 --> TRY',
    ])
    assert not reaches_completion("TRY", mermaid.adjacency(closed), completion_nodes(closed)), (
        "a cycle with no way out must be reported, otherwise the rule cannot fail"
    )
