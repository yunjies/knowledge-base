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


def _is_paragraph(line: str) -> bool:
    """Report whether a line opens a prose paragraph rather than another block."""
    return not line.lstrip().startswith(("#", "```", "-", "*", "|", ">"))


# A demand document under `assets/inbox/` opens with its provenance block
# instead of the paragraph: `target` / `output` / `prompt` tell the reader what
# the demand touches and where its result lands before the flow is read. That
# ordering is the directory's own declared relaxation of F01, stated in
# `assets/inbox/README.md`; the paragraph then follows the block. Every other
# flow document keeps the original form, so the exception is keyed on location
# rather than loosened globally.
#
# `assets/archive/` keeps the SAME form: an archived demand is the inbox
# document moved, not rewritten (its README says the contract travels with the
# document), so its provenance block leads there too. Keying the exception on
# both demand directories is what lets a document be archived without being
# falsified into a violation of the rule it still lives under.
DEMAND_PREFIXES = (f"{'assets'}/inbox/", f"{'assets'}/archive/")


def _opens_legally(path, lines: list[str]) -> str | None:
    """Return a defect description, or None when the opening satisfies F01."""
    index = _first_content_index(lines)
    if index < 0:
        return "no content after the H1"

    first = lines[index]
    relative = paths.relative(path)
    if not relative.startswith(DEMAND_PREFIXES):
        if not _is_paragraph(first):
            return f"{index + 1} opens with {first[:40]!r}"
        return None

    # The inbox form: a `yaml` fence, then the paragraph immediately after it.
    if not first.lstrip().startswith("```yaml"):
        return f"{index + 1} does not open with the provenance block, but with {first[:40]!r}"
    closing = next(
        (i for i in range(index + 1, len(lines)) if lines[i].startswith("```")),
        None,
    )
    if closing is None:
        return "the provenance block fence is never closed"
    after = next((i for i in range(closing + 1, len(lines)) if lines[i].strip()), None)
    if after is None:
        return "nothing follows the provenance block"
    if lines[after].startswith("# ") or lines[after].startswith("## "):
        return "the provenance block is not followed by the purpose paragraph"
    if not _is_paragraph(lines[after]):
        return f"{after + 1} follows the provenance block with {lines[after][:40]!r}"
    return None


def test_every_flow_document_opens_with_a_prose_paragraph(repo) -> None:
    """F01: the block after the H1 must be a paragraph, or the inbox block then one.

    Only the H1 and blank lines may precede it. A document that opens with its
    graph forces the reader through the whole picture before learning whether it
    answers their question.

    `assets/inbox/` documents lead with their provenance block, per that
    directory's declared relaxation; the paragraph still follows immediately, so
    the reader is never moved from the H1 straight into a graph.
    """
    offenders = []
    for path in paths.flow_documents():
        defect = _opens_legally(path, _lines(path))
        if defect is not None:
            offenders.append(f"{paths.relative(path)}: {defect}")
    assert offenders == [], (
        "a flow document must state its purpose in prose up front — immediately after the H1, or "
        "immediately after the inbox provenance block — so a reader can decide whether the graph "
        f"concerns them before reading it: {offenders}"
    )


def test_the_opening_rule_tells_the_two_forms_apart() -> None:
    """Both openings must be accepted, and every other opening rejected.

    Stated over literal source so the property holds whatever the corpus
    contains today. Without the negative half the exception could widen until a
    document opening straight into its graph reads as compliant, which is the
    failure F01 exists to catch.

    The cases run through `_opens_legally` itself rather than a reimplementation
    of its index arithmetic: a control that restates the rule can agree with a
    broken rule and still pass.
    """
    accepted = {
        "plain": ("assets/projects/x/feature-flow.md", ["# T", "", "目标段落。"]),
        "inbox block then paragraph": (
            "assets/inbox/req.x-20260101-000000.md",
            ["# T", "", "```yaml", "target: x", "```", "", "目标段落。"],
        ),
    }
    rejected = {
        "graph first": ("assets/projects/x/feature-flow.md", ["# T", "", "```mermaid", "flowchart TB", "```"]),
        "list first": ("assets/projects/x/feature-flow.md", ["# T", "", "- 一项"]),
        "inbox block with no paragraph": (
            "assets/inbox/req.x-20260101-000000.md",
            ["# T", "", "```yaml", "target: x", "```"],
        ),
        "inbox block then heading": (
            "assets/inbox/req.x-20260101-000000.md",
            ["# T", "", "```yaml", "target: x", "```", "", "## 主流程"],
        ),
        "inbox block unclosed": (
            "assets/inbox/req.x-20260101-000000.md",
            ["# T", "", "```yaml", "target: x"],
        ),
    }

    class _Doc:
        """The minimum a path must expose for the opening rule to judge it."""

        def __init__(self, relative: str, lines: list[str]) -> None:
            self._relative = relative
            self._lines = lines

        def read_text(self, encoding: str | None = None) -> str:
            return "\n".join(self._lines)

    real_relative = paths.relative

    def _relative(path):
        # Consult the stub's own attribute without invoking the real function:
        # passing it as `getattr`'s default would evaluate it eagerly on the
        # stub and raise before the attribute is ever looked up.
        if hasattr(path, "_relative"):
            return path._relative
        return real_relative(path)

    paths.relative = _relative
    try:
        for name, (relative, lines) in accepted.items():
            defect = _opens_legally(_Doc(relative, lines), lines)
            assert defect is None, f"{name} should be a legal opening, got {defect!r}"
        for name, (relative, lines) in rejected.items():
            defect = _opens_legally(_Doc(relative, lines), lines)
            assert defect is not None, f"{name} must not read as a legal opening"
    finally:
        paths.relative = real_relative


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
