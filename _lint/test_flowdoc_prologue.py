"""F01 and F02: a flow document opens with prose, then a graph-only chapter.

F01 requires the first content block after the H1 to be a paragraph stating the
graph's purpose — not the graph itself, not a list. F02 requires the first `##`
chapter to hold nothing but the main flow graph: a reader who opens that chapter
gets one graph, undiluted by sub-flow detail.
"""

from __future__ import annotations

from _harness import paths


def _lines(path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def _first_content_index(lines: list[str]) -> int:
    """The index of the first line that is neither the H1 nor blank."""
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# "):
            continue
        return index
    return -1


def test_every_flow_document_opens_with_a_prose_paragraph(repo) -> None:
    """F01: the block after the H1 must be a paragraph, not a graph or a list.

    Only the H1 and blank lines may precede it. A document that opens with its
    graph forces the reader through the whole picture before learning whether it
    answers their question.
    """
    offenders = []
    for path in paths.flow_documents():
        lines = _lines(path)
        index = _first_content_index(lines)
        if index < 0:
            offenders.append(f"{paths.relative(path)}: no content after the H1")
            continue
        first = lines[index]
        if first.lstrip().startswith(("#", "```", "-", "*", "|", ">")):
            offenders.append(f"{paths.relative(path)}:{index + 1} opens with {first[:40]!r}")
    assert offenders == [], (
        "a flow document must state its purpose in prose immediately after the H1, so a reader can "
        f"decide whether the graph concerns them before reading it: {offenders}"
    )


def test_the_main_graph_chapter_holds_only_the_graph(repo) -> None:
    """F02: the first `##` chapter's body must be the graph and nothing else.

    An entry node stays in the main graph, but a sub-flow's internal steps do
    not; their presence is what makes a main graph unreadable on its own.
    """
    offenders = []
    for path in paths.flow_documents():
        lines = _lines(path)
        heads = [index for index, line in enumerate(lines) if line.startswith("## ")]
        if not heads:
            offenders.append(f"{paths.relative(path)}: carries a graph but no h2 chapter")
            continue
        start = heads[0]
        end = heads[1] if len(heads) > 1 else len(lines)
        body = [line for line in lines[start + 1 : end] if line.strip()]
        if not body:
            offenders.append(f"{paths.relative(path)}: the first h2 chapter is empty")
            continue
        if not body[0].startswith("```mermaid"):
            offenders.append(
                f"{paths.relative(path)}:{start + 2} first h2 chapter opens with {body[0][:40]!r}"
            )
            continue
        closing = next((i for i, line in enumerate(body[1:], start=1) if line.startswith("```")), None)
        if closing is None:
            offenders.append(f"{paths.relative(path)}: the main graph fence is never closed")
            continue
        trailing = body[closing + 1 :]
        if trailing:
            offenders.append(
                f"{paths.relative(path)}: the main graph chapter carries {len(trailing)} line(s) "
                f"beyond the graph, starting {trailing[0][:40]!r}"
            )
    assert offenders == [], (
        "the first h2 chapter carries the main graph alone, so a reader gets one picture without "
        f"sub-flow detail woven through it: {offenders}"
    )
