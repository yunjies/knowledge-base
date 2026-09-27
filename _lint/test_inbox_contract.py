"""The inbox contract: a demand's filename says which demand it is, its colours say where it stands.

`assets/inbox/README.md` states two things about a demand document that the
document's own content cannot state. Its **filename** is the demand's identity:
the three-segment form `req.<业务>.<时间>.md` is what makes the directory listing
read as a queue ordered by arrival, and `<时间>` is the moment the demand
arrived rather than the moment it advanced — which is why a demand is never
renamed while it is being worked on. Its **node colours** are the demand's
status: every node in every graph carries one of the three statuses, so a reader
opening the document can see what is done, what is pending and what is stuck
without reading a word of prose. The README keeps the state out of the prose
deliberately; a status that lives only in a sentence is unreadable at a glance,
which is the whole point of the colour.

Two decisions here are worth stating, because both were live alternatives:

The naming check accepts the dot form only, and that is the README's rule rather
than a convenience. Every demand in the corpus but one already writes
`req.<业务>.<时间>.md`; the single hyphenated file predates the README and is the
outlier, so the gate catches it instead of the rule being widened to admit it. A
gate written to accept both spellings would have no power over either — the
corpus could drift one file at a time and every run would stay green.

The colour check judges that each node carries *a* status, not that all three
appear. A demand with nothing blocked is a healthy demand, and requiring red
would make the honest document fail. What is forbidden is a node with no status
at all, since that node's reader cannot tell it apart from one nobody has
started.

`assets/archive/` is judged by the same two rules: an archived demand is the
inbox document moved, not rewritten, and the directory README says its form and
colours still bind it after the move. Applying the rules there too is also what
keeps the archive from becoming a place where a malformed demand can hide.
"""

from __future__ import annotations

import re

from _harness import mermaid, paths

# A demand's identity, per the directory README: `req.` + business segment +
# arrival stamp + extension. The business segment is a lowercase short name; the
# stamp is the arrival moment to the second in `YYYYMMDD-HHMMSS`.
DEMAND_NAME = re.compile(r"^req\.[a-z0-9]+\.[0-9]{8}-[0-9]{6}\.md$")

# Both directories hold demands under the same contract. The archive is included
# on purpose: an archived demand keeps its name and colours.
DEMAND_DIRECTORIES = ("assets/inbox", "assets/archive")

# Files in a demand directory that are not demands: the boundary statement, and
# the skeleton readers copy. The skeleton is named `template.md` precisely so it
# does not claim to be a demand, so judging it by the demand rules would report
# the skeleton as a defective demand rather than as a skeleton.
NON_DEMAND_FILES = {"README.md", "template.md"}

# The three statuses the directory README fixes, as a colour's *role* rather than
# its value: the class name a `class` statement assigns. The README leaves the
# literal colours to each document's own contract chapter, so naming a hex value
# here would invent a rule the README does not make. What the README does fix is
# that three statuses exist and that colour carries them.
STATUS_CLASSES = ("todo", "done", "stuck")

# `classDef name fill:...` — a style declaration, keyed by class name.
CLASS_DEF = re.compile(r"^\s*classDef\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)
# `class A,B,C name` — a node-to-status assignment, and the form that carries
# status. The identifiers before the trailing class name are the nodes.
CLASS_ASSIGNMENT = re.compile(r"^\s*class\s+([A-Za-z0-9_,\s]+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", re.MULTILINE)


def demand_documents() -> list:
    """Every demand document under the inbox and the archive, READMEs excluded.

    Discovered by walking rather than listed: a demand nobody registers would
    otherwise escape every check here, which is the failure these checks exist to
    prevent.
    """
    root = paths.repository_root()
    out = []
    for directory in DEMAND_DIRECTORIES:
        base = root / directory
        if not base.is_dir():
            continue
        out.extend(path for path in paths._walk(base) if path.name not in NON_DEMAND_FILES)
    return sorted(out)


def misnamed(documents: list) -> list[str]:
    """Demand documents whose filename does not match `req.<业务>.<时间>.md`."""
    return [
        f"{paths.relative(path)}: `{path.name}` is not `req.<业务>.<时间>.md`"
        for path in documents
        if not DEMAND_NAME.match(path.name)
    ]


def status_assignments(block: str) -> dict[str, str]:
    """Node to status class, for the assignments that name a status class.

    Only the three status classes count. A graph may define further classes of
    its own for styling, and assigning a node to one of those says nothing about
    its status.
    """
    assigned: dict[str, str] = {}
    for names, class_name in CLASS_ASSIGNMENT.findall(block):
        if class_name not in STATUS_CLASSES:
            continue
        for node in (part.strip() for part in names.split(",")):
            if node:
                assigned[node] = class_name
    return assigned


def statused_nodes(block: str) -> set[str]:
    """Nodes the graph assigns to a status class via `class ...`."""
    return set(status_assignments(block))


def declared_status_classes(block: str) -> set[str]:
    """Status classes the graph defines a style for, via `classDef`."""
    return {name for name in CLASS_DEF.findall(block) if name in STATUS_CLASSES}


def unstamped_graphs(text: str) -> list[str]:
    """Graphs carrying a node with no status, described by defect.

    A graph is reported when it draws nodes but leaves some of them unassigned,
    or when it assigns a status class it never defined. The second is the quieter
    defect: mermaid renders an undefined class as unstyled, so the node appears
    with no colour and reads as statusless while the document looks like it
    declared one.

    Nodes and classes are kept apart deliberately: what a node is *assigned to*
    is a class, so the undefined-class defect compares classes used against
    classes defined, never node names against class names.

    A graph drawing no nodes is passed over: this check asks whether each drawn
    node carries a status, and a graph with nothing in it has nothing to answer
    for. Whether a demand's graph must draw anything at all is a different
    question, owned by the flow-document constraints (F01-F08), not by this one.
    """
    defects = []
    for index, block in enumerate(mermaid.graph_blocks(text)):
        nodes = set(mermaid.nodes_in(block))
        if not nodes:
            continue
        assigned = statused_nodes(block)
        declared = declared_status_classes(block)
        unassigned = sorted(nodes - assigned)
        used_classes = set(status_assignments(block).values())
        undefined = sorted(used_classes - declared)
        if unassigned:
            defects.append(f"graph {index + 1}: node(s) with no status {unassigned}")
        if undefined:
            defects.append(
                f"graph {index + 1}: status class(es) used with no classDef {undefined}"
            )
    return defects


def test_every_demand_filename_matches_the_naming_rule(repo) -> None:
    """A demand's filename must be its identity in the README's three-segment form.

    The name is how a demand is referenced and how the directory sorts by
    arrival; a file outside the form is not addressable as a demand and breaks
    the reading of the directory as a queue. The stamp's *truth* is not judged —
    nothing in the file can date its own arrival — only its shape.
    """
    offenders = misnamed(demand_documents())
    assert offenders == [], (
        "a demand file must be named `req.<业务>.<时间>.md` with a `YYYYMMDD-HHMMSS` arrival "
        f"stamp, so the directory reads as a queue ordered by arrival: {offenders}"
    )


def test_every_demand_node_carries_one_of_the_three_statuses(repo) -> None:
    """Every node of every graph in a demand must carry a status.

    The directory README puts the demand's state in colour rather than prose, so
    a node with no assigned status is a node whose state cannot be read. The
    check is that each node carries *one of the three* statuses — a wholly green
    demand is a finished demand, not a defective one, so the three are not
    required to appear together.
    """
    offenders = []
    for path in demand_documents():
        defects = unstamped_graphs(path.read_text(encoding="utf-8"))
        if defects:
            offenders.append(f"{paths.relative(path)}: {'; '.join(defects)}")
    assert offenders == [], (
        "every node in a demand's graphs must carry one of the three statuses (`class` with a "
        f"`classDef`-defined todo/done/stuck), so its state reads without the prose: {offenders}"
    )


def test_the_naming_rule_tells_a_demand_from_a_lookalike() -> None:
    """The name pattern must accept the real form and reject near misses.

    Asserted over literal names so the property outlives the corpus: a pattern
    loosened until everything matches would leave the first check green over any
    filename at all, and the rejection half is what stops that.
    """
    accepted = [
        "req.lint.20260926-002731.md",
        "req.hmp.20260927-062907.md",
        "req.credential.20260927-041050.md",
    ]
    for name in accepted:
        assert DEMAND_NAME.match(name), f"{name} is the README's form and must be accepted"
    rejected = {
        "req.lint-20260926-002731.md": "the business segment and stamp are joined by a dot",
        "req.lint.20260926.md": "the stamp carries both date and time",
        "req.lint.20260926-0027.md": "the stamp reaches seconds",
        "req.Lint.20260926-002731.md": "the business segment is lowercase",
        "req.lint.20260926-002731.markdown": "a demand is markdown",
        "note.lint.20260926-002731.md": "a demand is prefixed `req`",
    }
    for name, reason in rejected.items():
        assert not DEMAND_NAME.match(name), f"{name!r} must be rejected: {reason}"


def test_the_status_reader_counts_nodes_and_rejects_an_unstamped_graph() -> None:
    """The reader must find a stamped graph and reject an unstamped one.

    Asserted over literal graphs so the property outlives the corpus. Reading
    `class` assignments leniently — as satisfied by any graph — would report
    every document compliant while checking nothing.
    """
    stamped = (
        "flowchart TB\n"
        '  A(["开始"]) --> B["做事"]\n'
        "  classDef todo fill:#f9d71c,stroke:#8a6d00,color:#000\n"
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
        "  class B todo\n"
    )
    unstamped = 'flowchart TB\n  A(["开始"]) --> B["做事"]\n'
    partial = (
        "flowchart TB\n"
        '  A(["开始"]) --> B["做事"]\n'
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
    )
    undefined = (
        "flowchart TB\n"
        '  A(["开始"]) --> B["做事"]\n'
        "  class A done\n"
        "  class B todo\n"
    )
    # Nodes introduced only by an edge: mermaid draws every endpoint, so an
    # unassigned one is exactly the defect this gate exists to catch. The bare
    # *source* is the case that escaped twice — a chain head `A --> B` makes `A`
    # a node, so reading targets alone leaves it invisible.
    bare_target = (
        "flowchart TB\n"
        '  A(["开始"]) --> B --> C(["结束"])\n'
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
        "  class C done\n"
    )
    bare_source = (
        "flowchart TB\n"
        '  A --> B(["结束"])\n'
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class B done\n"
    )

    def document(body: str) -> str:
        """A document carrying `body` as its mermaid graph."""
        return f"# 需求\n\n```mermaid\n{body}```\n"

    assert statused_nodes(stamped) == {"A", "B"}, "both assigned nodes must be read"
    assert declared_status_classes(stamped) == {"todo", "done"}, "both classDefs must be read"
    assert unstamped_graphs(document(stamped)) == [], "a fully stamped graph is not a defect"
    assert unstamped_graphs(document(bare_target)) == [
        "graph 1: node(s) with no status ['B']"
    ], (
        "a node drawn only as an edge target must still be discovered — reading shapes alone "
        "left it invisible, so a statusless bare node passed the whole suite"
    )
    assert unstamped_graphs(document(bare_source)) == [
        "graph 1: node(s) with no status ['A']"
    ], (
        "a node drawn only as an edge source must be discovered too — reading targets alone "
        "left a chain head invisible"
    )
    # The opposite direction, and the one that hurts most: a comment is prose, so
    # an arrow written inside one names no node. Reading the raw block turns those
    # words into phantoms and reports a correctly written document as defective —
    # a green-to-red failure, which no author can fix except by deleting prose.
    commented = (
        "flowchart TB\n"
        '  A(["开始"]) --> B(["结束"])\n'
        "  %% 这里说明 X --> Y 的语义\n"
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
        "  class B done\n"
    )
    styled = (
        "flowchart TB\n"
        '  A ::: done --> B(["结束"])\n'
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
        "  class B done\n"
    )
    assert unstamped_graphs(document(commented)) == [], (
        "an arrow inside a `%%` comment names no node — reporting its words as statusless nodes "
        "makes a correct document fail"
    )
    assert unstamped_graphs(document(styled)) == [], (
        "an inline `::: class` assignment is styling, not a node identifier"
    )
    # A dotted edge is used in this corpus — the demand template draws its
    # blocking exit that way — so a node introduced by one must be found too.
    dashed = (
        "flowchart TB\n"
        '  A(["开始"]) --> B(["结束"])\n'
        "  B -.-> GHOST\n"
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
        "  class B done\n"
    )
    assert unstamped_graphs(document(dashed)) == [
        "graph 1: node(s) with no status ['GHOST']"
    ], (
        "a node joined by a dotted edge must be discovered — the node parser read solid arrows "
        "only, so a statusless dotted node stayed invisible"
    )
    # The source of a dotted edge may carry a shape; the target is still a node.
    dashed_from_shaped = (
        "flowchart TB\n"
        '  A(["开始"]) -.-> GHOST\n'
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
    )
    assert unstamped_graphs(document(dashed_from_shaped)) == [
        "graph 1: node(s) with no status ['GHOST']"
    ], (
        "a dotted edge leaving a shaped node still draws its target — requiring the source to "
        "abut the arrow dropped the target"
    )
    # A label is display text: an arrow written inside one names no node.
    labelled_arrow = (
        "flowchart TB\n"
        '  A(["开始"]) --> B["按 X --> Y 的语义做事"]\n'
        "  classDef done fill:#2ea043,stroke:#0b4a1b,color:#fff\n"
        "  class A done\n"
        "  class B done\n"
    )
    assert unstamped_graphs(document(labelled_arrow)) == [], (
        "an arrow inside a node label is display text — reading it as an edge invents nodes and "
        "reports a correct document as defective"
    )
    assert unstamped_graphs(document(unstamped)), (
        "a graph with no status at all must be reported"
    )
    assert unstamped_graphs(document(partial)), (
        "a graph leaving one node unassigned must be reported"
    )
    assert unstamped_graphs(document(undefined)) == [
        "graph 1: status class(es) used with no classDef ['done', 'todo']"
    ], (
        "an undefined status class must be reported by class name — reporting node names here "
        "would flag every correctly stamped graph in the corpus"
    )
