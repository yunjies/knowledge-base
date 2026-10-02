"""The per-project deploy documents: present, migrated, usable, and clean.

`assets/projects/<project>/deploy.md` is the knowledge base's statement of how a
reader gets one included project installed and used. It sits **beside** the
project's checkout, in the same layer as `feature-flow.md`, which is why it is in
this suite's scope while the documents inside the checkout are not: what is
judged here is the knowledge base's own record, not any project's repository.

Five properties are checked, and they fail differently.

**Presence** is the cheapest and the one everything else depends on: a project
whose deploy document is missing has no stated deployment path at all, and the
absence is silent because a missing file raises nothing.

**Migration** is a *move*, not a copy. `assets/notes/` admits a note only where
it has nowhere else to live, and a note recording one project's deployment facts
fails that clause once that project has a deploy document. Keeping both would be
two authorities for one set of facts, diverging from the day the second is
written. What is decidable is the pair: the note is gone, *and* the practices it
carried are readable at the destination. Either alone is satisfied by a defect —
deleting the note without migrating loses the content, and the destination
existing while the note still sits in `assets/notes/` leaves the duplicate.

**Recoverable commands** decide whether the document is usable rather than merely
plausible. Every build/test/deploy entry point it names must exist in that
project's checkout. The criterion is **the entry point exists**, never that the
command runs: running it needs a registry, a browser GUI, a container runtime or
`root`, and that evidence belongs to the project's own test layer, not here. A
document that names a script the `package.json` never declared sends its reader
to an error the document itself caused.

**No credentials** is a security property with a false-positive cost that is easy
to ignore. A pattern widened until it fires on `<主机IP>` or `0.0.0.0` would have
authors delete the check, and a check deleted for noise protects nothing — so the
rule is pinned in both directions below, with the private ranges that must fire
and the placeholders that must not.

**Configuration through `.env`** is the one property here that fails *silently*,
and that is why it is checked rather than left to the human-read list at the end
of this docstring. A deployment document that states its host-varying values
through an `.env` file has moved those values out of the document and into a file
the document no longer fully shows; the two then have to agree on *names*, and
when they do not, nothing errors. An environment variable name accepts letters,
digits and underscores, so a key written in Chinese is not a key: Compose reads
nothing for it, `${...}` falls back to the default it was given, and the stack
comes up looking healthy while the value the author intended never arrived. YAML
parses, every command runs, the container reports `healthy` — the only evidence
is the wrong value, later, somewhere else. Two things are therefore asserted: the
keys of the sample are names a variable can have, and the sample's key set and
the Compose document's `${...}` references are the same set in both directions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from _harness import paths

PROJECTS = ("dsh-credentials", "dsh-cronjob", "home-media-pilot")

# The note the migration absorbed. Named literally rather than derived: the point
# is that *this* note left `assets/notes/`, and a rule keyed on a pattern would
# stop applying the moment the file is renamed rather than migrated.
MIGRATED_NOTE = "assets/notes/deploy-home-media-pilot.md"

# The destination of that migration, and the practices the note carried. Each is
# a property the note stated in its own words, not a string it used: an upgrade
# that pulls and recreates, a `/health` endpoint the reader can hit, and the
# version check that tells an upgrade apart from a no-op.
MIGRATION_DESTINATION = "assets/projects/home-media-pilot/deploy.md"
MIGRATED_PRACTICES = (
    ("pull-based upgrade", re.compile(r"docker\s+compose\s+pull|docker\s+pull")),
    ("health verification", re.compile(r"/health")),
    ("compose configuration", re.compile(r"^```yaml\s*$", re.MULTILINE)),
)

# ---------------------------------------------------------------------------
# Credential detection.
#
# Three independent shapes, kept apart so each can be pinned on its own. A
# single combined pattern would make a failure unattributable and would tempt a
# widening of one shape to hide a miss in another.
# ---------------------------------------------------------------------------

# A private IPv4 literal. The ranges are RFC 1918 plus the three that are private
# by other standards and leak host topology just as effectively: loopback,
# link-local, and CGNAT. `127.0.0.1` is *not* in this set despite being
# loopback — see `PUBLIC_HOSTS` for why the distinction is made by value and not
# by class.
PRIVATE_IPV4 = re.compile(
    r"(?<![\d.])("
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|169\.254\.\d{1,3}\.\d{1,3}"
    r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"
    r")(?![\d.])"
)

# A loopback or unspecified address. Loopback is *documentation*: every Compose
# healthcheck and every local smoke test writes `127.0.0.1`, and flagging it
# would push authors to delete the check.
LOOPBACK_IPV4 = re.compile(
    r"(?<![\d.])(?:127\.\d{1,3}\.\d{1,3}\.\d{1,3}|0\.0\.0\.0)(?![\d.])"
)

# A credential *prefix*. These are issued in a fixed form, so the prefix plus a
# plausible body distinguishes a leaked token from the words `sk-` or `ghp_`
# appearing in prose about token formats.
TOKEN_PREFIX = re.compile(
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{16,}"
    r"|\bsk-[A-Za-z0-9_-]{16,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}"
)

# An assignment that puts a literal where a secret belongs: `password: hunter2`,
# `TOKEN=abc`, and the Chinese equivalents a prose document would use. The value
# must be a plain word rather than a placeholder, an environment lookup, or a
# sentence, which is what keeps this off ordinary configuration prose.
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|密码|口令|凭据|令牌)"
    r"\s*[:=]\s*[\"']?([^\s\"'`,;)\]}#]+)",
    re.IGNORECASE,
)

# A credential embedded in a URL's authority: `scheme://user:secret@host`. This
# is the shape a leaked database or registry URL takes, and it carries no key
# word for the assignment rule above to match, so it is its own shape.
URL_CREDENTIAL = re.compile(r"://[^\s/:@`]+:([^\s/@`]+)@")

# A value that is not a secret, whatever key it sits under. Each alternative is a
# form the deploy documents legitimately use. Without this list the assignment
# rule above fires on `凭据形态是硬约束` and on every `token` that appears in a
# sentence, which is the failure mode that gets a check deleted.
NOT_A_SECRET = (
    "<...>",  # an angle placeholder
    "...",
    "${",  # an environment interpolation
    "$",
    "{{",  # a compose/template interpolation
    "(",
    "'",
    '"',
    "，",
    "。",
    "、",
    "是",
    "为",
    "指",
    "见",
    "由",
    "按",
    "缺失",
    "形态",
    "本身",
)


def deploy_documents() -> dict[str, Path]:
    """The deploy document of each included project, regardless of existence.

    Keyed by project so an absence is visible as a missing key rather than
    silently dropped from a list — the check that iterates this dict is the one
    that must report a deletion.
    """
    root = paths.repository_root() / "assets" / "projects"
    return {project: root / project / "deploy.md" for project in PROJECTS}


def text_of(path: Path) -> str:
    """Read a document, tolerating absence so callers can report it themselves."""
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def missing_or_empty() -> list[str]:
    """Deploy documents that are absent or carry no content."""
    offenders = []
    for project, path in sorted(deploy_documents().items()):
        if not path.is_file():
            offenders.append(f"{paths.relative(path)}: missing")
        elif not path.read_text(encoding="utf-8").strip():
            offenders.append(f"{paths.relative(path)}: empty")
    return offenders


def leaks(text: str) -> list[str]:
    """Every credential-shaped or private-topology string in `text`."""
    found = []
    for match in PRIVATE_IPV4.finditer(text):
        if not LOOPBACK_IPV4.fullmatch(match.group(0)):
            found.append(f"private address {match.group(0)}")
    for match in TOKEN_PREFIX.finditer(text):
        found.append(f"token prefix {match.group(0)[:12]}…")
    for match in CREDENTIAL_ASSIGNMENT.finditer(text):
        value = match.group(1)
        if any(value.startswith(prefix) for prefix in NOT_A_SECRET):
            continue
        key = match.group(0).split(":")[0].split("=")[0]
        found.append(f"literal credential for {key}")
    for match in URL_CREDENTIAL.finditer(text):
        found.append(f"credential embedded in a URL near {text[max(0, match.start() - 12):match.start()]!r}")
    return found


def backticked_paths(text: str) -> list[str]:
    """Checkout-relative paths a document writes in inline code.

    Only spans that read as a *checkout-relative* path count. Three families are
    excluded, each because flagging it would report a correct document as
    defective rather than report a defect:

    - Notation: spans containing `{`, `}`, `<`, `>`, `*`, `$` or a space. A brace
      form like `dist/bundle/{index.mjs,client.js}` needs brace expansion to
      resolve, and guessing at the expansion would judge the document's notation.
    - Host and deployment paths: an absolute path, `~`, or a bare directory name
      such as `profiles/` or `bundle/`. These name places on the deployment host
      or inside a built artifact, not entries of the checkout, and the document
      says so in its own prose. A reference only counts here when it descends at
      least two segments from the checkout root, which is the shape a citation of
      the checkout actually takes.
    - The project's own root, written the same way the document defines its
      shorthand (`assets/projects/<项目>/<repository>/`). That span *is* the
      checkout root, so joining it to the checkout would look for it inside
      itself.
    """
    out = []
    for raw in re.findall(r"`([^`\n]+)`", text):
        candidate = raw.strip()
        if any(char in candidate for char in "{}<>*$ "):
            continue
        if candidate.startswith(("/", "~", ".")):
            continue
        if candidate.startswith("assets/projects/"):
            continue
        if "/" not in candidate:
            continue
        if not re.search(r"/$|\.[A-Za-z0-9]{1,8}$", candidate):
            continue
        if len(candidate.rstrip("/").split("/")) < 2:
            # A single-segment directory name is a name, not a checkout citation.
            continue
        out.append(candidate)
    return out


def workflow_entries(project_root: Path) -> set[str]:
    """The workflow files the checkout actually declares, by basename."""
    directory = project_root / ".github" / "workflows"
    if not directory.is_dir():
        return set()
    return {entry.name for entry in directory.iterdir() if entry.is_file()}


def gitignore_patterns(project_root: Path) -> list[str]:
    """The pattern lines of the checkout's `.gitignore`, comments dropped."""
    path = project_root / ".gitignore"
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def is_generated(path: str, project_root: Path) -> bool:
    """Report whether a path is a build output the project keeps out of git.

    A document citing `dist/bundle/index.mjs` is citing a build product: the
    fact it states is that the build writes there, and the artifact is absent
    until someone builds — so requiring it on disk would report a correct
    document as defective. That the path is generated is decided by the
    project's own `.gitignore`, which is its statement about what it does not
    track, rather than by this file assuming `dist/` means "generated".
    """
    segments = path.rstrip("/").split("/")
    patterns = gitignore_patterns(project_root)
    for index in range(len(segments)):
        prefix = "/".join(segments[: index + 1])
        for pattern in patterns:
            bare = pattern.lstrip("/").rstrip("/")
            if bare in (prefix, prefix + "/", segments[index]) and (
                "/" not in bare or bare == prefix
            ):
                return True
    return False


def unresolvable_entries() -> list[str]:
    """Every checkout entry point a deploy document names and the checkout lacks."""
    offenders = []
    for project, document in sorted(deploy_documents().items()):
        text = text_of(document)
        if not text:
            continue
        project_root = document.parent / project
        if not project_root.is_dir():
            continue
        for reference in sorted(set(backticked_paths(text))):
            if reference.startswith(".github/workflows/"):
                if reference.rsplit("/", 1)[1] not in workflow_entries(project_root):
                    offenders.append(f"{paths.relative(document)}: `{reference}` not in the checkout")
                continue
            if is_generated(reference, project_root):
                continue
            if not (project_root / reference.rstrip("/")).exists():
                offenders.append(f"{paths.relative(document)}: `{reference}` not in the checkout")
    return offenders


# ---------------------------------------------------------------------------
# `.env` configuration: the sample block, and the Compose references to it.
# ---------------------------------------------------------------------------

# A fenced block's opening or closing line. The info string is captured because
# it is what distinguishes the sample from every other fence in the document,
# including the indented fences a list item or a numbered step nests inside it.
FENCE_MARK = re.compile(r"^(`{3,})[ \t]*([A-Za-z0-9_+.-]*)[ \t]*$", re.MULTILINE)

# An environment variable assignment. Restricted to `NAME=`, so a `KEY: value`
# line — Compose's mapping form, YAML in general — is not read as one, and
# anchored to the start of a line, so the indented mapping keys inside the
# Compose document are not mistaken for assignments either. The name is taken
# verbatim rather than matched against the legal shape above: a key that cannot
# be a variable name is exactly the defect the first case below exists to report,
# and a pattern that could not match it would hide it.
ENV_ASSIGNMENT = re.compile(r"^[ \t]*(?:export[ \t]+)?([^\s=#]+)[ \t]*=(.*)$")

# A shell expansion inside a Compose document: the bracketed `${NAME}` form, both
# with and without a default. The bare `$NAME` form is deliberately excluded —
# Compose itself accepts only the bracketed one, so a bare `$NAME` in a Compose
# file is literal text (an in-container command, an allowed IP list); reading it
# as an interpolation would report the container's own path and shell variables
# as unassigned references. The default, if any, is captured and used below.
COMPOSE_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}")

# An interpolation inside the document's own prose, on a line that is not a
# command and not an assignment. `$DSH_HOME` in a sentence about the harness is
# neither, and requiring it to be resolvable would report correct prose.
PROSE_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")

# Names defined by the shell or by Compose itself rather than by a project's
# `.env`. `${HOME:-/root}` in an in-container command is the case that forced
# this list: it is a reference, it resolves, and demanding that the document's
# sample assign `HOME` would report a correct document.
SHELL_PROVIDED = frozenset({"HOME", "PATH", "PWD", "TMPDIR", "USER", "SHELL", "COMPOSE_PROJECT_NAME"})

# The two forms that make prose or a command line a *claim* rather than a
# mention: a doubled dollar is an escape (`$$` renders as `$`), a preceding
# backslash escapes the expansion, and a preceding `$` is the shell's positional
# parameter idiom `${1:-x}`. None of the three asks the document's `.env` for a
# name, so none of them is a claim about that file.
REFERENCE_ESCAPES = ("$$", "\\", "$")


def fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Every fenced block in `text`, as `(info string, body)` pairs.

    The info string is lowercased and the body has its trailing newline removed.
    Fences pair in order, which is what markdown itself does; an unclosed fence
    therefore swallows the rest of the document into one block rather than
    silently shifting every later pairing by one.
    """
    marks = list(FENCE_MARK.finditer(text))
    blocks = []
    for index in range(0, len(marks) - 1, 2):
        info = marks[index].group(2).lower()
        body = text[marks[index].end() : marks[index + 1].start()]
        blocks.append((info, body.strip("\n")))
    return blocks


def env_sample_keys(text: str) -> tuple[list[str], list[str]]:
    """The keys of the document's `.env` sample, and the lines that are not keys.

    The block is located by hitting two independent marks rather than by picking
    the first `bash` fence: at least half its lines must be assignments, *and* at
    least one line must use the `NAME=<placeholder>` form, where the unquoted
    value is an angle placeholder and the name is a legal variable name. The pair
    is what separates a sample from a command list — the latter has assignments
    too (`cd <目录>` aside, a shell variable could appear), but its commands take
    arguments and are not bare placeholders. Markdown cannot express a fence
    inside a fence, so the sample cannot be a block nested in prose either.

    Keys are returned in file order and **not** deduplicated: the callers that
    compare key sets build their own sets, and a duplicate key in the sample is
    not something this function has an opinion about. The second element is every
    line the block gave that is neither blank, nor a comment, nor a parseable
    assignment, so a malformed sample is reported rather than read as empty.
    """
    for info, body in fenced_blocks(text):
        if info not in ("", "bash", "sh", "shell", "dotenv", "env"):
            continue
        lines = [line for line in body.splitlines() if line.strip()]
        if not lines:
            continue
        parsed = [ENV_ASSIGNMENT.match(line) for line in lines]
        assignments = [match for match in parsed if match]
        if len(assignments) * 2 < len(lines):
            continue
        placeholder = any(
            re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]*$", match.group(1))
            and re.fullmatch(r"<[^<>]*>", match.group(2).strip())
            for match in assignments
        )
        if not placeholder:
            continue
        keys = [match.group(1) for match in assignments]
        residues = [
            line
            for line, match in zip(lines, parsed)
            if match is None and not line.strip().startswith("#")
        ]
        return keys, residues
    return [], []


def compose_documents(text: str) -> list[str]:
    """The bodies of the document's `yaml` fenced blocks.

    The info string is the discriminator, and it is the right one: a Compose
    document written in this knowledge base is always fenced as `yaml`, and an
    unlabelled fence in these documents is a command list, not data.
    """
    return [body for info, body in fenced_blocks(text) if info == "yaml"]


def compose_references(text: str) -> list[str]:
    """Every `${NAME}` interpolation the document's Compose blocks use, in order."""
    return [
        match.group(1)
        for body in compose_documents(text)
        for match in COMPOSE_REFERENCE.finditer(body)
    ]


def prose_references(text: str) -> list[str]:
    """Names the document's own prose interpolates, excluding the Compose blocks.

    Only lines that are neither a command nor an assignment are read: a line
    starting with `$` or with `export` is a shell line, where `$DSH_HOME` is a
    variable the environment is expected to provide and not a claim about the
    document's `.env`. Fenced blocks of any other language are skipped with them,
    except the `.env` sample, whose assignments and comments are prose about the
    file rather than commands run with it.
    """
    sample = env_sample_keys(text)[0]
    found: list[str] = []
    for info, body in fenced_blocks(text):
        if info in ("bash", "sh", "shell"):
            continue
        in_sample = info in ("dotenv", "env")
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "$", "export")):
                continue
            for match in PROSE_REFERENCE.finditer(line):
                name = match.group(1) or match.group(4)
                if name in SHELL_PROVIDED:
                    continue
                if in_sample and name in sample:
                    continue
                if match.group(2) is not None:
                    # A `${NAME:-…}` states, in the same breath, what happens
                    # when nobody sets the name. That is an account, and this
                    # reader is looking for claims without one.
                    continue
                prefix = line[max(0, match.start() - 2) : match.start()]
                if any(prefix.endswith(escape) for escape in REFERENCE_ESCAPES):
                    continue
                found.append(name)
    return found


def unresolvable_interpolations(text: str) -> list[str]:
    """Every name a document interpolates without stating where its value comes from.

    A name reaches a Compose file from one of four places, and a document that
    states the `.env` form owes an account of the last one: the host shell has
    it, Compose's own environment has it, the interpolation carries its own
    `:-default`, or the document's `.env` sample assigns it. A name in none of
    the four is not a value the reader can supply — it is either a typo in the
    reference or a key the sample forgot, and either way the reader is left
    holding a blank.

    A defaulted `${NAME:-…}` **is** an account: the document has stated what
    happens when nobody sets the name, which is exactly the question this rule
    asks. Requiring an assignment on top of it would report every correctly
    defaulted variable as a defect, and that is the failure mode that gets a
    check deleted.

    The reading is deliberately narrow on the *other* axis too: inside a Compose
    document only the bracketed `${NAME}` form counts, because Compose expands
    nothing else there and a bare `$NAME` is literal text.
    """
    keys, _ = env_sample_keys(text)
    known = set(keys) | SHELL_PROVIDED
    offenders = []
    for match in COMPOSE_REFERENCE.finditer("\n".join(compose_documents(text))):
        if match.group(2) is None and match.group(1) not in known:
            offenders.append(
                f"Compose interpolates ${{{match.group(1)}}} and nothing in the document accounts "
                "for it"
            )
    for reference in prose_references(text):
        if reference not in known:
            offenders.append(
                f"the prose interpolates ${reference} and nothing in the document accounts for it"
            )
    return offenders


def env_samples_validated_against_compose(text: str) -> list[str]:
    """Every way a document's `.env` sample and its Compose references disagree.

    The pairing is what makes the rule decidable at all: a key is never wrong on
    its own, only against the interpolation that was supposed to read it. Four
    failures come out of the pairing, and each is a distinct way for the reader
    to be handed a value that never arrives. Asserted over a literal document
    rather than over the corpus, so the property outlives whichever documents
    happen to exist today.
    """
    offenders = []
    keys, residues = env_sample_keys(text)
    if not keys:
        if re.search(r"^\s*env_file\s*:", text, re.MULTILINE):
            offenders.append(
                "points Compose at a `.env` file but carries no `.env` sample, so no reader can "
                "know which keys it must set"
            )
        return offenders

    illegal = [key for key in keys if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)]
    if illegal:
        offenders.append(
            f"`.env` sample keys {illegal} are not variable names — an environment variable name "
            "accepts only letters, digits and underscores, so a key written otherwise is read by "
            "nobody and any `${NAME:-default}` silently falls back to its default"
        )
    if residues:
        offenders.append(
            f"`.env` sample lines {residues} are neither a comment nor a `NAME=value` assignment, "
            "so the file they describe would not parse as one"
        )

    legal = [key for key in keys if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)]
    references = compose_references(text)
    # Every key must be read by something: a key nobody interpolates states a
    # configuration option that does not exist, and the reader who sets it
    # changes nothing.
    orphans = sorted(set(legal) - set(references))
    if orphans:
        offenders.append(
            f"`.env` sample keys {orphans} are interpolated nowhere in the Compose document, so "
            "setting them changes nothing"
        )
    # Every reference without a default of its own must be a key: Compose aborts
    # on an unset variable, and a document that shows the file and the Compose
    # document together is showing a stack that will not start.
    unassigned = sorted(
        {
            match.group(1)
            for match in COMPOSE_REFERENCE.finditer("\n".join(compose_documents(text)))
            if match.group(2) is None
        }
        - set(legal)
        - SHELL_PROVIDED
    )
    if unassigned:
        offenders.append(
            f"the Compose document interpolates {unassigned} without a default and the `.env` "
            "sample does not assign them, so Compose stops on an unset variable"
        )
    return offenders


# ---------------------------------------------------------------------------
# The `.env` rule's own controls: literal samples, pinned in both directions.
# ---------------------------------------------------------------------------

# The sample this rule was written for. Every key is a legal name, every key is
# interpolated by the Compose document beside it, and every reference the Compose
# document makes without a default is assigned here.
WELL_FORMED_CONFIG = "\n".join(
    [
        "# 环境信息的配置方式",
        "",
        "部署机上的取值放在 `.env` 里。",
        "",
        "```bash",
        "HOST_PORT=<宿主端口>",
        "HOST_DATA_DIR=/<主机数据目录>/pilot",
        "LOGICAL_PATHS=<逻辑根到容器内路径的 JSON 映射>",
        "```",
        "",
        "```yaml",
        "services:",
        "  pilot:",
        "    env_file:",
        "      - .env",
        "    environment:",
        "      DATABASE_URL: sqlite:////app/data/pilot.db",
        "      LOGICAL_PATHS: ${LOGICAL_PATHS}",
        "      MEDIA_ROOT: ${MEDIA_ROOT:-/media}",
        "    ports:",
        '      - "${HOST_PORT:-8000}:8000"',
        "    volumes:",
        "      - ${HOST_DATA_DIR:-./data}:/app/data",
        "```",
    ]
)

# Each case states exactly one property the rule must catch, and its two blocks
# are consistent with each other apart from that one injected fault. They are
# separate cases rather than one, because a single combined sample would make a
# failure unattributable: it would not say which clause of the rule had stopped
# working. `sample` replaces the `.env` block and `compose` the Compose block,
# always together.
CONFIG_DEFECTS = {
    "a key written in Chinese": {
        "sample": ["HOST_PORT=<宿主端口>", "部署机IP=<部署机IP>"],
        "compose": [
            '      - "${HOST_PORT:-8000}:8000"',
            "      CORS_ORIGINS: http://${部署机IP:-localhost}:${HOST_PORT:-8000}",
        ],
        "expects": "not variable names",
    },
    "a key no interpolation reads": {
        "sample": ["HOST_PORT=<宿主端口>", "UNUSED_KEY=<未使用的键>"],
        "compose": ['      - "${HOST_PORT:-8000}:8000"'],
        "expects": "interpolated nowhere",
    },
    "an interpolation with no default and no key": {
        "sample": ["HOST_PORT=<宿主端口>"],
        "compose": ["      LOGICAL_PATHS: ${LOGICAL_PATHS}", '      - "${HOST_PORT:-8000}:8000"'],
        "expects": "without a default",
    },
    "a line that is not an assignment": {
        "sample": ["HOST_PORT=<宿主端口>", "HOST_DATA_DIR /<主机数据目录>/pilot"],
        "compose": ['      - "${HOST_PORT:-8000}:8000"'],
        "expects": "neither a comment nor a `NAME=value` assignment",
    },
    "a Compose document that reads no `.env` at all": {
        "sample": [],
        "compose": [
            "    env_file:",
            "      - .env",
            "    environment:",
            "      DATABASE_URL: sqlite:////app/data/pilot.db",
        ],
        "expects": "carries no `.env` sample",
    },
}

# References that are not claims about the document's `.env`. Each is a form the
# documents legitimately contain, and requiring any of them to be assigned would
# report a correct document — the failure mode that gets a check deleted. The
# first two are prose about a host the document does not configure, the third is
# a command line, and the last two are Compose text where a bare `$NAME` is
# literal because Compose expands only the bracketed form.
SPARED_REFERENCES = {
    "harness root is $DSH_HOME": "a shell variable the environment provides",
    "harness root is ${DSH_HOME:-$HOME/.dsh}": "a shell expansion carrying its own default",
    "cloned into $HOME/.dsh/plugins.": "a path under the shell's own home",
    "    user: ${USER:-pilot}": "a Compose variable with its own default",
    "    command: [$PWD, ${PWD}]": "the bare form inside a Compose document",
}


def with_compose(document: str, compose_lines: list[str]) -> str:
    """`document` with the body of its `yaml` block replaced.

    Kept separate from `with_sample` because a defect case must be able to move
    either side of the pairing on its own; the two are then composed in the order
    that leaves the fixture with exactly one injected fault.
    """
    return document.replace(_compose_body(document), "\n".join(compose_lines))


def with_sample(sample_lines: list[str]) -> str:
    """The well-formed document with its `bash` sample block replaced.

    Built by substitution on the fence bodies rather than by line numbers: the
    replacement samples differ in length, and an index computed from one would
    address the other.
    """
    return WELL_FORMED_CONFIG.replace(_sample_body(WELL_FORMED_CONFIG), "\n".join(sample_lines))


def _sample_body(document: str) -> str:
    """The body of `document`'s `.env` sample block, as `env_sample_keys` finds it."""
    return next(body for info, body in fenced_blocks(document) if info == "bash")


def _compose_body(document: str) -> str:
    """The body of `document`'s Compose block."""
    return next(body for info, body in fenced_blocks(document) if info == "yaml")


# ---------------------------------------------------------------------------
# Credentials: the pairs the rule must catch and the prose it must spare.
# ---------------------------------------------------------------------------

LEAK_SAMPLES = {
    "ghp_0123456789abcdefghijkl": "a GitHub personal access token",
    "sk-abcdefghijklmnopqrstuvwx": "an API key in the vendor's issued form",
    "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz": "a fine-grained token",
    "rclone address 192.168.1.24:5572": "a LAN host address",
    "unraid at 10.0.0.5": "a private range address",
    "host 172.16.4.9": "the lower half of the 172.16/12 range",
    "host 172.31.255.254": "the upper half of the 172.16/12 range",
    "camera at 169.254.10.1": "a link-local address",
    "peer 100.64.3.7": "a CGNAT address",
    "password: hunter2": "a literal password",
    "DATABASE_URL=postgres://pilot:s3cret@db/prod": "a literal password in a URL",
    "sqlite://user:hunter2@host/db": "a credential embedded in a URL authority",
}

SPARED_SAMPLES = {
    "部署机 IP 填 `<部署机IP>`，端口填 `<宿主端口>`。": "an angle placeholder",
    "healthcheck 打 `http://127.0.0.1:8000/health`。": "loopback in a healthcheck",
    "监听 `0.0.0.0` 以接受外部连接。": "the unspecified address",
    "`CORS_ORIGINS: http://<部署机IP>:<宿主端口>`": "placeholders inside a URL",
    "image: ghcr.io/<registry-owner>/home-media-pilot:main": "a placeholder registry owner",
    "只要读权限时用 `https://github.com/settings/tokens/new?scopes=read:packages`。": "a scope URL",
    "凭据形态是硬约束：GitHub Packages 只接受 classic token。": "prose about token kinds",
    "`DATABASE_URL: sqlite:////app/data/home_media_pilot.db`": "a local sqlite URL",
    "把 token 放在环境变量里，不写进任何随仓库分发的文件。": "an instruction",
    "`CORS_ORIGINS: http://<部署机IP>:<宿主端口>`": "a URL whose host is a placeholder",
}


def test_every_project_has_a_nonempty_deploy_document(repo) -> None:
    """Each included project must carry a deploy document with content in it.

    The document is the knowledge base's only stated answer to "how do I get this
    installed and used"; without it the deployment facts are back to living in
    the checkout's README, which is exactly what the per-project layer exists to
    replace.
    """
    offenders = missing_or_empty()
    assert offenders == [], (
        "every project under assets/projects/ needs a deploy.md stating its deployment path: "
        f"{offenders}"
    )


def test_the_migrated_note_is_gone_and_its_practices_survived(repo) -> None:
    """The deployment note must be absent *and* its content readable at its new home.

    Both halves are asserted because either alone is satisfied by a defect.
    Deleting the note without migrating loses the content; leaving the note in
    place while the destination exists leaves two authorities for one set of
    facts, diverging from the day the second is written.
    """
    root = paths.repository_root()
    stale = root / MIGRATED_NOTE
    assert not stale.exists(), (
        f"{MIGRATED_NOTE} still exists: the note describes one project's deployment facts, which "
        f"{MIGRATION_DESTINATION} now owns — keeping both makes two authorities for one set of "
        "facts, so the note is deleted after its content moves"
    )

    destination = root / MIGRATION_DESTINATION
    text = text_of(destination)
    assert text.strip(), (
        f"{MIGRATION_DESTINATION} is missing or empty, so the note's content moved nowhere"
    )
    absent = [
        name for name, pattern in MIGRATED_PRACTICES if not pattern.search(text)
    ]
    assert absent == [], (
        f"{MIGRATION_DESTINATION} does not carry the practices the note recorded {absent} — the "
        "note was deleted rather than migrated, and the deployment procedure is now written "
        "nowhere"
    )


def test_dsh_credentials_documents_the_bundle_landing_path_only(repo) -> None:
    """The deploy guide must state the supported source-to-plugin route.

    Build and official installation are separate claims: requiring both prevents
    a mention of bundle from standing in for a usable deployment procedure. The
    retired Dynamic Cordis command and UI route must not remain as alternate
    instructions, since that would make readers choose between incompatible
    delivery paths.
    """
    document = paths.repository_root() / "assets" / "projects" / "dsh-credentials" / "deploy.md"
    text = text_of(document)
    assert text.strip(), f"{paths.relative(document)} is missing or empty"

    required = {
        "bundle build": re.compile(r"npm\s+run\s+build:bundle"),
        "official mount": re.compile(r"dsh\s+plugin\s+add"),
    }
    absent = [name for name, pattern in required.items() if not pattern.search(text)]
    assert absent == [], f"dsh-credentials/deploy.md omits required bundle steps: {absent}"

    retired = re.compile(r"Dynamic Cordis|dynamic-cordis|build:dynamic-cordis", re.IGNORECASE)
    assert not retired.search(text), "dsh-credentials/deploy.md still advertises the retired Dynamic Cordis route"


def test_every_named_entry_point_exists_in_its_checkout(repo) -> None:
    """A named build/test/deploy entry point must exist where the document says it does.

    The criterion is existence, not executability. Running `npm run test:e2e` needs
    a live GUI, running `docker compose pull` needs a registry and a container
    runtime, and mounting a bundle needs `root`; none of that is this repository's
    to provide, and demanding it here would replace a real check with a flaky one.
    What this does decide is that the reader who follows the command is sent to a
    path that is there.
    """
    offenders = unresolvable_entries()
    assert offenders == [], (
        "a deploy document must name entry points that exist in its project's checkout — the "
        f"checkout is the authority for its own layout: {offenders}"
    )


def test_the_entry_point_rule_separates_a_real_path_from_a_generated_one(tmp_path: Path) -> None:
    """The rule must flag a path the checkout lacks, and spare a generated one.

    Asserted over literal text so the property outlives the corpus, and in both
    directions because each alone is satisfied by a broken rule: a rule flagging
    everything would report every correct document, and a rule flagging nothing
    would let a document name a file that does not exist anywhere.

    The checkout is a FIXTURE BUILT HERE, not a real project directory. Every
    project checkout this suite inspects is git-ignored (each is an independent
    clone or a source tree outside the knowledge base), so none of them exists
    in a fresh clone — and a control that asserted one into existence would
    pass on a developer's machine and fail in CI, which is the one place the
    guard actually has to hold. Building the fixture makes the control depend
    on nothing but this file, so it proves the rule in both environments.
    """
    checkout = tmp_path / "checkout"
    (checkout / "tests").mkdir(parents=True)
    (checkout / "dist" / "bundle").mkdir(parents=True)
    (checkout / "tests" / "README.md").write_text("fixture\n", encoding="utf8")
    (checkout / ".gitignore").write_text("dist/\n", encoding="utf8")
    assert checkout.is_dir(), "the fixture checkout could not be built"

    # A path that is there, a path that is not, and a build output the project
    # deliberately does not track.
    assert backticked_paths("见 `tests/README.md`") == ["tests/README.md"], (
        "a relative path in inline code must be read as a path claim"
    )
    assert backticked_paths("形如 `dist/bundle/{index.mjs,client.js}` 的产物") == [], (
        "a brace-expansion form is notation, not a path claim, and must not be reported"
    )
    assert backticked_paths("写入 `~/.ssh`；落在 `/app/data`；见 `profiles/`、`bundle/`") == [], (
        "host paths, in-container paths and bare directory names are not checkout citations"
    )
    assert backticked_paths("工程根即 `assets/projects/dsh-cronjob/dsh-cronjob/`") == [], (
        "the span naming the checkout root itself must not be joined to that root"
    )
    assert not is_generated("tests/README.md", checkout), (
        "a tracked source path must not be excused as generated"
    )
    assert is_generated("dist/bundle/index.mjs", checkout), (
        "a build output the checkout gitignores must be spared: it is absent until someone builds"
    )
    assert not (checkout / "examples" / "nonexistent-entry.yml").exists(), (
        "the negative half must name a path the fixture lacks"
    )


def test_the_credential_rule_fires_on_secrets_and_spares_placeholders(repo) -> None:
    """The credential rule must catch each leak shape and spare ordinary prose.

    Both halves are asserted because either alone is satisfied by a broken rule:
    a pattern matching everything catches every leak, and one matching nothing
    spares every placeholder. The sparing half is not a courtesy — a rule that
    fires on `127.0.0.1` in a healthcheck or on `<部署机IP>` in a template is a
    rule authors delete, and a deleted rule protects nothing.
    """
    missed = {sample: why for sample, why in LEAK_SAMPLES.items() if not leaks(sample)}
    assert missed == {}, (
        f"the credential rule misses these leak shapes, so a document could carry them and pass: "
        f"{missed}"
    )
    false_alarms = {
        sample: reasons
        for sample, reasons in (
            (sample, leaks(sample)) for sample in SPARED_SAMPLES
        )
        if reasons
    }
    assert false_alarms == {}, (
        "the credential rule fires on ordinary documentation, which would train authors to delete "
        f"it: {false_alarms}"
    )


def test_no_deploy_document_carries_a_credential_or_private_address(repo) -> None:
    """No deploy document may contain a secret or an internal network address.

    These documents are committed and read by anyone with the repository, so a
    token pasted into one is disclosed by the act of writing it. The private
    ranges matter for the same reason at lower severity: they expose a host's
    topology, and the correct form is the placeholder the documents already use.
    """
    offenders = []
    for project, document in sorted(deploy_documents().items()):
        text = text_of(document)
        if not text:
            continue
        for finding in leaks(text):
            offenders.append(f"{paths.relative(document)}: {finding}")
    assert offenders == [], (
        "a deploy document is committed and public to every reader of this repository; state "
        f"credentials and internal addresses as placeholders instead: {offenders}"
    )


def test_each_project_flow_document_links_to_its_deploy_document(repo) -> None:
    """A project's flow document must point at its deploy document.

    `feature-flow.md` states what a project does; `deploy.md` states how to stand
    it up. A reader who enters through the flow document — the documented entry
    layer — never learns the deploy document exists unless the flow document
    names it. The link is asserted from the flow side because that is the side
    with a reader; a deploy document nobody is routed to is a document nobody
    reads.
    """
    offenders = []
    for project in PROJECTS:
        flow = paths.repository_root() / "assets" / "projects" / project / "feature-flow.md"
        if not flow.is_file():
            offenders.append(f"{paths.relative(flow)}: missing, so nothing routes a reader to deploy.md")
            continue
        links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", flow.read_text(encoding="utf-8"))
        if "deploy.md" not in links:
            offenders.append(f"{paths.relative(flow)}: carries no link to deploy.md")
    assert offenders == [], (
        "each project's feature-flow.md is the entry layer for that project, so it must link its "
        f"same-directory deploy.md: {offenders}"
    )


def test_every_env_sample_key_is_a_variable_name(repo) -> None:
    """A `.env` sample may only use keys an environment variable can have.

    This is the case the rest of the `.env` rules were written after. A key is a
    *name*, and a name outside `[A-Za-z_][A-Za-z0-9_]*` is not an exotic key —
    it is not a key. Compose reads nothing for it, so the interpolation that was
    meant to use it falls back to whatever default it was given, and the
    deployment comes up healthy while carrying a value nobody chose. Nothing
    along the way errors: the YAML parses, the container starts, the healthcheck
    passes. The only signal is the wrong behaviour, later, and somewhere else.

    `$DSH_HOME` and `${HOST_PORT:-8000}` in the surrounding prose are not sample
    keys and are not read as any: the sample is located as a block, by the two
    independent marks `env_sample_keys` documents.
    """
    offenders = []
    for project, document in sorted(deploy_documents().items()):
        text = text_of(document)
        if not text:
            continue
        keys, residuals = env_sample_keys(text)
        illegal = [key for key in keys if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)]
        if illegal:
            offenders.append(
                f"{paths.relative(document)}: keys {illegal} are not variable names, so Compose "
                "reads no value for them and any `${NAME:-default}` silently keeps its default"
            )
        if residuals:
            offenders.append(
                f"{paths.relative(document)}: sample lines {residuals} are not `NAME=value`, so the "
                "file the document shows would not parse as one"
            )
    assert offenders == [], (
        "a `.env` sample is the list of names the reader must set; a line that is not a variable "
        f"name is a setting that will never take effect: {offenders}"
    )


def test_env_sample_keys_and_compose_interpolations_correspond(repo) -> None:
    """The sample's keys and the Compose document's `${...}` references must be the same set.

    A document that states the `.env` form and then shows a Compose document is
    making a claim about the two *together*: this file, read by that document.
    The claim is checkable even though the values are not, because names are what
    the two sides exchange. Three disagreements are possible and all three are
    reported by one function, so the failure message names the side that is
    wrong:

    - a key the Compose document never interpolates is an option that does not
      exist, and the reader who sets it changes nothing;
    - a `${NAME}` with no default that the sample does not assign stops Compose,
      which aborts on an unset variable rather than starting with a blank;
    - a key that is not a variable name is read by nobody.

    A `${NAME:-default}` carries its own fallback, so it is allowed to have no
    key. A line of the Compose document that is *not* `${...}` — a literal like
    `DATABASE_URL: sqlite:////app/data/…` or `MEDIA_READ_ONLY: "true"` — is a
    deployment invariant of the container rather than a `.env` key, and is not
    counted as an unassigned reference: only the bracketed form is read.
    """
    offenders = []
    for project, document in sorted(deploy_documents().items()):
        text = text_of(document)
        if not text:
            continue
        for finding in env_samples_validated_against_compose(text):
            offenders.append(f"{paths.relative(document)}: {finding}")
    assert offenders == [], (
        "a deploy document that configures its host-varying values through `.env` must keep the "
        f"sample and the Compose document in agreement on names: {offenders}"
    )


def test_no_document_interpolates_a_name_it_never_accounts_for(repo) -> None:
    """Every name a document interpolates must be one the reader can supply.

    The same rule as the pairing above, seen from the other side. A name reaches
    a Compose file from the host shell, from Compose's own environment, or from
    the document's `.env` sample; a name from none of the three is not something
    the reader can supply, and the `${...}` that reads it is either a typo or a
    key the sample forgot.

    The reading is deliberately narrow, because the false-positive cost here is
    paid in deleted checks rather than in missed defects. Only the bracketed
    `${NAME}` form counts inside a Compose document — Compose expands nothing
    else there, so a bare `$NAME` is literal text. Lines that are commands or
    assignments are not read at all, which is what spares `$DSH_HOME` in a
    sentence about the harness and the shell's own variables in an example.
    """
    offenders = []
    for project, document in sorted(deploy_documents().items()):
        text = text_of(document)
        if not text:
            continue
        for finding in unresolvable_interpolations(text):
            offenders.append(f"{paths.relative(document)}: {finding}")
    assert offenders == [], (
        "an interpolation is a claim that a value arrives from somewhere; a name the document "
        f"never states the source of leaves the reader a blank or an unchosen default: {offenders}"
    )


def test_the_env_key_rule_catches_broken_samples_and_spares_real_ones() -> None:
    """The `.env` rule must fire on each disagreement and spare each legitimate reference.

    Asserted over a literal document rather than over the corpus, and in both
    directions, because each direction alone is satisfied by a broken rule. A
    rule that fired on everything would report every correct document; a rule
    that fired on nothing would let a document ship a key no one reads and pass.

    Each defect is one clause of the rule and one clause only, so a failure names
    the clause that stopped working rather than merely reporting that something
    did. Each case therefore replaces **both** blocks — its sample and the
    Compose document that reads it — so that the single injected fault is the
    only disagreement left in the fixture. The defect named for the Chinese key
    is the real one this rule was written for: it was in this very document, it
    parsed, it linted green, and it silently reverted the CORS origin to
    `localhost`.
    """
    assert env_samples_validated_against_compose(WELL_FORMED_CONFIG) == [], (
        "the rule reports a correct document, which would train authors to delete it"
    )

    missed = {}
    for name, case in CONFIG_DEFECTS.items():
        document = with_compose(with_sample(case["sample"]), case["compose"])
        findings = env_samples_validated_against_compose(document)
        if not any(case["expects"] in finding for finding in findings):
            missed[name] = {"expected": case["expects"], "found": findings}
    assert missed == {}, (
        f"the `.env` rule misses these defects, so a document could carry them and pass: {missed}"
    )

    false_alarms = {}
    for line, why in SPARED_REFERENCES.items():
        document = "\n".join([WELL_FORMED_CONFIG, "", line])
        findings = [
            finding
            for finding in unresolvable_interpolations(document)
            if "nothing in the document accounts for it" in finding
        ]
        if findings:
            false_alarms[line] = {"expected": why, "found": findings}
    assert false_alarms == {}, (
        "the rule fires on references that are not claims about the document's `.env`, which would "
        f"train authors to delete it: {false_alarms}"
    )
