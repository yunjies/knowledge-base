"""Where a document belongs, as distinct from how it is written.

Every other check here judges **form** — a prologue's shape, a node's type, a
count's wording. None of them judges **layer**, and a document can satisfy every
form rule while sitting in the wrong directory: the constraints are read, the
prose is clean, and the information is still filed where its reader will not
look for it.

The distinction matters because the two failures have different costs. A form
defect is local and fixable in place. A placement defect means the record is a
copy of something that has an authority elsewhere, so it diverges from that
authority from the day it is written — and the divergence is invisible, because
both texts are individually well-formed.

`assets/notes/README.md` states the admission test: a note enters only when it
**stays true across sessions** *and* has **nowhere else to live**. The second
clause is the decidable one. A note that names a project's checkout paths is a
document about that project, and `assets/projects/<project>/feature-flow.md` is
where the knowledge base states that project's implemented flows. That is the
mechanical approximation this file decides.

**What this cannot decide**, recorded rather than left to a green run: a note
that describes one project's flow in prose without naming any of its paths. The
approximation keys on the path prefix because that is what a copy carries
verbatim; a paraphrase carries none, and no pattern separates it from a genuine
cross-session note about a project that happens to be mentioned. That gap is
`README.md`'s to state, not this file's to hide.
"""

from __future__ import annotations

import re

from _harness import paths

# The shape of a path inside an included project's checkout, as it would be
# written in prose: `assets/projects/<project>/<repository>/…`. Both a fenced
# command and an inline reference take this form, so one pattern covers both.
CHECKOUT_PATH = re.compile(r"assets/projects/[^/\s`]+/[^/\s`]+/")

# A note about the knowledge base's own layout may legitimately quote the
# directory convention without being about one project. Naming the *pattern*
# (`assets/projects/<项目>/<repository>/`) rather than a real pair is how the
# convention is stated, so a placeholder segment is exempt.
PLACEHOLDER_SEGMENT = re.compile(r"^<[^>]+>$|^\{[^}]+\}$|^\*+$|^项目$|^repository$")


def checkout_paths(text: str) -> list[str]:
    """Every reference to a concrete path inside a project's checkout."""
    out = []
    for match in CHECKOUT_PATH.finditer(text):
        reference = match.group(0)
        segments = reference.rstrip("/").split("/")[2:]
        if any(PLACEHOLDER_SEGMENT.match(segment) for segment in segments):
            continue
        out.append(reference)
    return out


def note_documents() -> list:
    """Every note in the long-term note area.

    Discovered by walking, not listed: a note nobody registers would otherwise
    escape the check, which is the failure mode the suite exists to prevent.
    """
    notes = paths.repository_root() / "assets" / "notes"
    return [path for path in paths._walk(notes) if path.name != "README.md"]


def test_notes_do_not_carry_a_projects_checkout_internals() -> None:
    """A note must not describe one project from inside its checkout.

    `assets/notes/README.md` admits a note only when it stays true across
    sessions *and* has nowhere else to live. A note citing
    `assets/projects/<project>/<repository>/…` fails the second clause: the
    knowledge base already states that project's implemented flows in
    `assets/projects/<project>/feature-flow.md`, so the note is a second
    authority for the same facts and diverges from it silently.

    The remedy is not deletion but relocation — fold the content into that
    project's flow document, and delete the note. `assets/notes/` keeps no
    "deprecated" record; a note that is no longer needed is removed whole.
    """
    offenders = []
    for path in note_documents():
        text = path.read_text(encoding="utf-8")
        references = checkout_paths(text)
        if references:
            named = ", ".join(sorted(set(references))[:3])
            offenders.append(f"{paths.relative(path)} cites {named}")
    assert offenders == [], (
        "a note describing one project from inside its checkout is a copy of that project's flow "
        "document; move it to assets/projects/<project>/feature-flow.md and delete the note: "
        f"{offenders}"
    )


# Negative controls. A rule widened until nothing trips it is a dead rule, and a
# rule narrowed until it trips on ordinary writing pushes authors to delete the
# check. Both directions are pinned here, with the historical sample that must
# keep firing and the ordinary notes that must never fire.
HISTORICAL_SAMPLE = """
## 构件

仓库克隆内（`assets/projects/home-media-pilot/home-media-pilot/`）：

- `cordis/host.js`：host 半。经 cordis 的 `shell` 服务启停服务进程。
- `cordis/client.js`：client 半，注册四个座位。
"""

ORDINARY_NOTES = [
    # A cross-session note about the knowledge base's own convention: it states
    # the path *pattern*, which is not a project.
    "项目产物在 `assets/projects/<项目>/<repository>/`，流程文档为 `<项目>/feature-flow.md`。",
    # A note that mentions a project by name without citing its internals: the
    # judgement this check deliberately does not make.
    "home-media-pilot 走容器路线部署，与 DSH 同机时另走 cordis 落地。",
    # A note about the harness, which is not an included project at all.
    "动态包的 client 半只允许注册 `tool.view.cordis` 的 `key: 'self'`。",
    # A note about another project's deployment, whose paths are not citations.
    "`docker-compose.yml` 里的 `api` 服务绑定 8000 端口。",
]


def test_the_placement_rule_fires_and_spares() -> None:
    """The rule must catch its historical sample and leave ordinary notes alone.

    Both halves are asserted because either alone is satisfied by a broken rule:
    a pattern matching everything catches the sample, and a pattern matching
    nothing spares the prose. Only both together pin a rule that discriminates.
    """
    assert checkout_paths(HISTORICAL_SAMPLE), (
        "the rule no longer fires on a note that cites a project's checkout internals — "
        "it has been widened into a dead rule"
    )
    spared = [note for note in ORDINARY_NOTES if checkout_paths(note)]
    assert spared == [], (
        "the rule fires on ordinary notes that cite no project internals, which would train "
        f"authors to delete the check: {spared}"
    )
