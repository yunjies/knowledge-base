"""D02 and D03: the mechanically decidable part of the prose constraints.

D02 forbids stating a fact the reader can retrieve themselves; D03 forbids
citing an entry of another record. Both are semantic rules, so only a subset can
be decided by pattern: D02's **counts carrying a unit**, and D03's **references
to a numbered entry**. Which counts carry a unit is decidable; whether a
sentence is a transcription in general is not, and `README.md` records that gap
rather than letting a green run imply compliance.

The rules are stated with their own negative controls — the historical samples
that must keep firing, and the ordinary prose that must never fire. A rule
widened until nothing trips it is a dead rule, and a rule narrowed until it
trips on normal writing pushes authors to delete the check.
"""

from __future__ import annotations

import re

from _harness import paths

UNITS = "项|个文件|条|处|份|字节|KB|MB|GB"
DIGITS = "(?:[0-9]+|[零一二三四五六七八九十百千两]+)"

RULES = [
    ("current-state quantity", re.compile(r"(?:当前|目前|现在)(?:为|有|是)?[^\S\n]*" + DIGITS + r"\s*(?:" + UNITS + r")")),
    ("measured quantity", re.compile(r"实[测证][^\n]{0,6}?" + DIGITS + r"\s*(?:" + UNITS + r")")),
    ("approximate quantity", re.compile(r"(?:约为?|大约)[^\S\n]*" + DIGITS + r"\s*(?:" + UNITS + r")")),
    ("parenthesised count", re.compile(r"（\s*" + DIGITS + r"\s*项\s*）")),
    ("tallied count", re.compile(r"(?:共|总计|合计)(?:有|为|是)?[^\S\n]*" + DIGITS + r"\s*(?:" + UNITS + r")")),
    ("approximate tally", re.compile(r"(?:共|总计|合计|目前|当前|现在|现有)(?:有|为|是)?[^\S\n]*" + DIGITS + r"\s*余\s*(?:" + UNITS + r")")),
    ("sole count", re.compile(r"(?:目前|当前|现在|现有)(?:只有|仅有|只|仅)[^\S\n]*" + DIGITS + r"\s*(?:" + UNITS + r")")),
    ("bare arabic count", re.compile(r"(?<![A-Za-z0-9_])[0-9][0-9,]{0,6}\s*(?:(?:项|个文件|条|处|份)(?![A-Za-z0-9]))")),
    ("arabic-counted collection", re.compile(r"(?<![A-Za-z0-9_])[1-9][0-9,]{0,6}\s*个(?:文件|门禁|模块|用例|测试|接口|条目|脚本|路径|缺陷|轮次)")),
]

# A citation into another record: a ledger name plus an entry number, or a
# pointer that names the ledger instead of the fact.
DEAD_POINTER = re.compile(r"(?:账本|ledger)\s*[:：]?\s*(?:R\d+[a-z]?\s+)?(?:MF|RF)-\d|(?:详见|参见|见)\s*(?:账本|ledger)")

HISTORICAL_SAMPLES = [
    "末尾必须是 `ALL CHECKS PASSED (...)`（当前为 23 项）。",
    "（实测打包 4 个文件：`bundle.patch.yml`、两个 dist 产物、`package.json`）",
    "npm test                    # 全部（host + client），当前 701 项",
    "本目录共 12 项用例。",
    "全库共 706 项断言。",
    "本目录共有十二条用例。",
    "当前约五十五个文件。",
    "tests/global 下 13 个门禁文件共 2615 行。",
]

ORDINARY_PROSE = [
    "计量单位与阈值等**契约性常量**（如 1MB 载荷上限、8 秒时间窗）不受此约束。",
    "两种形态都要先重建产物（cordis 走步骤 1→2→3，bundle 走 `npm run build`）。",
    "请求体有 1MB 上限，超限返回“载荷过大”。",
    "收集到 0 个用例时以非零退出码报错。",
    "以 20 个 `0` 的实测宽度得出列宽。",
    "这条链是 2026-09 加固的结果：绝对路径优先。",
]

DEAD_POINTER_SAMPLES = [
    "使全部宿主用例因等待超时而红（账本 RF-2026-09-16-007）。",
    "详见账本 RF-2026-09-17-066。",
]

GONE_ARTIFACT_PROSE = [
    "审计轮的确定性机器原在 workflows/、协议定义原在 audit-protocol/，二者已随重构清空。",
    "这份记录不复存在，其中的条目编号不再有对照物。",
    "编号是外部记录的索引，抄进正文即成第二事实源，必然分叉。",
]


def quantity_hits(text: str) -> list[str]:
    """Every line and rule that fires on a drifting count."""
    out = []
    for number, line in enumerate(text.split("\n"), start=1):
        for name, rule in RULES:
            if rule.search(line):
                out.append(f"line {number} [{name}] {line.strip()[:70]}")
    return out


# A quotation of the banned pattern is not the pattern. Naming it inside
# corner brackets or backticks is how a document explains the rule — including
# this file's own README and any report about it. Scanning for the phrase
# without allowing the quotation would forbid describing the constraint.
QUOTED = re.compile(r"[「『`][^」』`]*(?:账本|ledger)[^」』`]*[」』`]")


def pointer_hits(text: str) -> list[str]:
    """Every line that cites an entry of another record.

    A line that only *names* the pattern — quoted in 「」, 『』 or backticks — is
    exempt, since that is how the rule itself is stated and discussed.
    """
    out = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not DEAD_POINTER.search(line):
            continue
        residue = QUOTED.sub("", line)
        if DEAD_POINTER.search(residue):
            out.append(f"line {number} {line.strip()[:70]}")
    return out


def test_no_instruction_document_writes_a_drifting_count(repo) -> None:
    """D02's decidable subset: a count carrying a unit must cite its source.

    A count whose authority lives in the implementation is a copy this text owes
    nothing to: it goes stale the moment the code moves. Cite a re-runnable
    command, cite the single source, enumerate the members, or number the items.
    """
    offenders = []
    for path in paths.instruction_documents() + paths.flow_documents():
        for hit in quantity_hits(path.read_text(encoding="utf-8")):
            offenders.append(f"{paths.relative(path)}: {hit}")
    assert offenders == [], (
        "a count whose authority lives elsewhere is a copy that goes stale silently; write the path "
        f"that retrieves it instead: {offenders}"
    )


def test_no_document_cites_an_entry_of_another_record(repo) -> None:
    """D03: prose must state the fact, not index another record's entry.

    A citation makes the document an index copy of that record; when the record
    moves or is discarded the citation becomes an orphan, and the fact it stood
    for is lost with it.
    """
    offenders = []
    for path in paths.all_documents():
        for hit in pointer_hits(path.read_text(encoding="utf-8")):
            offenders.append(f"{paths.relative(path)}: {hit}")
    assert offenders == [], (
        "state the fact directly; a citation into another record forks from it as soon as either "
        f"side moves: {offenders}"
    )


def test_the_counting_rule_still_fires_on_the_historical_samples() -> None:
    """A rule weakened until the check is green is a dead rule.

    These samples are the ones the rule was written to catch; if any stops
    firing, the pattern has drifted and the check no longer does its job.
    """
    missed = [sample for sample in HISTORICAL_SAMPLES if not quantity_hits(sample)]
    assert missed == [], (
        f"the rule must keep firing on the samples it exists for: {missed}"
    )


def test_the_counting_rule_never_fires_on_ordinary_prose() -> None:
    """A rule that fires on normal writing trains authors to delete it.

    It must discriminate on the quantity, not on the presence of digits: a
    contract constant, a step reference and a guard described as "0 cases" are
    all legitimate.
    """
    flagged = [sample for sample in ORDINARY_PROSE if quantity_hits(sample)]
    assert flagged == [], (
        f"ordinary prose carrying numbers must not be flagged: {flagged}"
    )


def test_the_pointer_rule_fires_on_a_real_citation_and_spares_its_removal() -> None:
    """The pointer rule must catch a citation and not punish explaining a removal.

    Both directions matter: a rule that misses citations guards nothing, and one
    that fires on "that record no longer exists" forces authors to stop saying
    so — which is the honest thing to say.
    """
    missed = [sample for sample in DEAD_POINTER_SAMPLES if not pointer_hits(sample)]
    assert missed == [], f"a real citation must keep firing: {missed}"
    flagged = [sample for sample in GONE_ARTIFACT_PROSE if pointer_hits(sample)]
    assert flagged == [], (
        f"prose stating that an artifact is gone is not a citation: {flagged}"
    )

    quoted = ["断言其中不出现「详见账本 RF-xxx」这类外部记录条目引用。"]
    flagged = [sample for sample in quoted if pointer_hits(sample)]
    assert flagged == [], (
        "a document must be able to name the banned pattern in order to state the rule; quoting it "
        f"is not citing it: {flagged}"
    )


def test_the_counting_rule_covers_only_counts_that_carry_a_unit() -> None:
    """Record the rule's boundary as a verified fact, not a claim.

    The constraint governs any fact whose authority lives in the implementation,
    but the patterns can only decide counts carrying a unit. These samples slip
    past — recorded here so a green run is never read as compliance.
    """
    beyond_reach = [
        "本工程有两种落地形态。",
        "插件暴露七个 RPC 方法。",
        "工作台由四个视图组成。",
    ]
    caught = [sample for sample in beyond_reach if quantity_hits(sample)]
    assert caught == [], (
        "these counts carry no unit, so the patterns cannot decide them; if the rule starts firing "
        f"here it has widened past what a pattern can decide: {caught}"
    )
