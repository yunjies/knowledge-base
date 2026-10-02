'use strict'

const path = require('node:path')
const fs = require('node:fs')

const SPEC = path.join(__dirname, '..', 'reference', 'rule-card-writing-constraints.md')
const SKILL = path.join(__dirname, '..', 'SKILL.md')

const MARK = {
  fieldTableFrom: '### 0.1 标签 ↔ 字段对照',
  fieldTableTo: '### 0.2 子标签登记',
  subTagTableFrom: '### 0.2 子标签登记',
  subTagTableTo: '### 0.3 文档层定义的文本形态',
  docDefTableFrom: '### 0.3 文档层定义的文本形态',
  docDefTableTo: '### 0.4 撰写通则',
  truthTableFrom: '### 0.5 判定真值源',
  truthTableTo: '## 1. 规则卡片模板',
}

const UNJUDGED = '不参与判定'

function readSpec(file) {
  return fs.readFileSync(file || SPEC, 'utf8')
}

function section(text, from, to) {
  const i = text.indexOf(from)
  if (i < 0) throw new Error('规范册中找不到章节起点：' + from)
  const j = text.indexOf(to, i + from.length)
  if (j < 0) throw new Error('规范册中找不到章节终点：' + to)
  return text.slice(i, j)
}

function tableRows(block) {
  return block.split('\n').filter((l) => /^\s*\|/.test(l))
}

function isDivider(row) {
  return /^\s*\|[\s:|-]+\|\s*$/.test(row)
}

const HEADER_CELLS = new Set(['#', '字段', '父字段', '定义项', '判定输入'])

function isHeader(row) {
  const cells = row.split('|').slice(1, -1)
  return cells.length > 0 && HEADER_CELLS.has(cells[0].trim())
}

function backticked(text) {
  return [...text.matchAll(/`([^`]+)`/g)].map((m) => m[1])
}

function cardFields(text) {
  const block = section(text, MARK.fieldTableFrom, MARK.fieldTableTo)
  const out = []
  for (const row of tableRows(block)) {
    const m = /^\s*\|\s*\d+\s*\|\s*`([^`]+)`/.exec(row)
    if (m) out.push(m[1])
  }
  return out
}

function subTagFields(text) {
  const block = section(text, MARK.subTagTableFrom, MARK.subTagTableTo)
  const out = []
  for (const row of tableRows(block)) {
    if (isDivider(row) || isHeader(row)) continue
    const m = /^\s*\|\s*[^|]+\|\s*`([^`]+)`\s*\|/.exec(row)
    if (m) out.push(m[1])
  }
  return out
}

function docDefItems(text) {
  const block = section(text, MARK.docDefTableFrom, MARK.docDefTableTo)
  const out = []
  for (const row of tableRows(block)) {
    if (isDivider(row) || isHeader(row)) continue
    const cells = row.split('|').slice(1, -1)
    if (cells.length < 2) continue
    const shape = cells[1].trim()
    if (!/^(属性行|三列表格|封闭枚举)/.test(shape)) continue
    out.push(cells[0].trim())
  }
  return out
}

function truthRows(text) {
  const block = section(text, MARK.truthTableFrom, MARK.truthTableTo)
  return tableRows(block).filter((l) => !isDivider(l) && !isHeader(l))
}

function unjudgedRow(text) {
  return truthRows(text).filter((l) => l.includes(UNJUDGED))
}

function allowedRows(text) {
  return truthRows(text).filter((l) => !l.includes(UNJUDGED))
}

function truthSourceFields(text) {
  const out = []
  for (const row of truthRows(text)) out.push(...backticked(row))
  return out
}

function checkForward(text) {
  const registered = cardFields(text)
  if (registered.length === 0) {
    return { registered, missing: [], inconclusive: '规范 §0.1 的字段表未被发现，解析器给出的通过是空转的' }
  }
  const sourced = new Set(truthSourceFields(text))
  return { registered, missing: registered.filter((f) => !sourced.has(f)), inconclusive: null }
}

function checkBackward(text) {
  const registered = new Set([...cardFields(text), ...subTagFields(text), ...docDefItems(text)])
  const sourced = truthSourceFields(text)
  if (sourced.length === 0) {
    return { sourced, unknown: [], inconclusive: '规范 §0.5 的表未点出任何字段，正向检查会空转通过' }
  }
  return { sourced, unknown: [...new Set(sourced)].filter((f) => !registered.has(f)), inconclusive: null }
}

function checkUnjudged(text) {
  const rows = unjudgedRow(text)
  if (rows.length !== 1) {
    return { rows, missing: [], reason: '"不参与判定"行必须恰有一行，实得 ' + rows.length + ' 行' }
  }
  const decorative = ['title', 'layer', 'overridable', 'why']
  const row = rows[0]
  const missing = decorative.filter((f) => !row.includes('`' + f + '`'))
  return { rows, missing, reason: missing.length ? '装饰性字段未落在"不参与判定"行内' : null }
}

function checkSubTags(text) {
  const registered = subTagFields(text)
  if (registered.length === 0) {
    return { registered, missing: [], inconclusive: '规范 §0.2 的子标签表未被发现，子标签层的通过是空转的' }
  }
  const sourced = new Set(truthSourceFields(text))
  return { registered, missing: registered.filter((f) => !sourced.has(f)), inconclusive: null }
}

function checkDocDefs(text) {
  const registered = docDefItems(text)
  if (registered.length === 0) {
    return { registered, missing: [], inconclusive: '规范 §0.3 的定义项表未被发现，文档层定义项的通过是空转的' }
  }
  const sourced = new Set(truthSourceFields(text))
  return { registered, missing: registered.filter((f) => !sourced.has(f)), inconclusive: null }
}

function checkMutualExclusion(text) {
  const rows = unjudgedRow(text)
  if (rows.length !== 1) {
    return { conflicts: [], reason: '"不参与判定"行必须恰有一行才能判定互斥，实得 ' + rows.length + ' 行' }
  }
  const unjudged = new Set(backticked(rows[0]))
  const conflicts = []
  for (const row of allowedRows(text)) {
    for (const name of backticked(row)) {
      if (unjudged.has(name)) conflicts.push(name)
    }
  }
  return { conflicts: [...new Set(conflicts)], reason: null }
}

function headingSlugs(text) {
  return new Set(
    text
      .split('\n')
      .filter((l) => /^#{1,6}\s/.test(l))
      .map((l) => l.replace(/^#{1,6}\s+/, '').trim().toLowerCase().replace(/[^\p{L}\p{N} _-]/gu, '').replace(/ /g, '-')),
  )
}

function checkLinks(text) {
  const slugs = headingSlugs(text)
  const broken = []
  text.split('\n').forEach((l, i) => {
    for (const m of l.matchAll(/\]\(#([^)]+)\)/g)) {
      if (!slugs.has(m[1])) broken.push('行' + (i + 1) + ' #' + m[1])
    }
  })
  return { broken }
}

function checkRoutingTable(skillText, specText) {
  const anchor = '## 路由表'
  const i = skillText.indexOf(anchor)
  if (i < 0) {
    return { pairs: [], missing: [], inconclusive: 'SKILL.md 中没有「路由表」章节，按任务取回的入口缺失（它是 LLM 在取回规范前唯一可见的文本）' }
  }
  const nextHeading = skillText.indexOf('\n## ', i + anchor.length)
  const block = skillText.slice(i, nextHeading > i ? nextHeading : undefined)
  const pairs = [...block.matchAll(/`([A-Za-z][A-Za-z0-9_]*)`→(F-\d{2})/g)].map((m) => [m[1], m[2]])
  if (pairs.length === 0) {
    return { pairs, missing: [], inconclusive: '路由表未给出「字段→条目编号」对照，定位入口形同虚设' }
  }
  const missing = []
  for (const [field, id] of pairs) {
    if (!new RegExp('^### ' + id + ' `' + field + '`', 'm').test(specText)) missing.push(field + '→' + id)
  }
  const specSlugs = headingSlugs(specText)
  for (const m of block.matchAll(/\]\(reference\/[^)#]*#([^)]+)\)/g)) {
    if (!specSlugs.has(m[1])) missing.push('锚点不可解析 #' + m[1])
  }
  return { pairs, missing, inconclusive: null }
}

function checkSkillLinks(skillText, specText) {
  const specSlugs = headingSlugs(specText)
  const broken = []
  skillText.split('\n').forEach((l, i) => {
    for (const m of l.matchAll(/\]\(reference\/rule-card-writing-constraints\.md#([^)]+)\)/g)) {
      if (!specSlugs.has(m[1])) broken.push('SKILL.md 行' + (i + 1) + ' #' + m[1])
    }
    for (const m of l.matchAll(/\]\(#([^)]+)\)/g)) {
      if (!headingSlugs(skillText).has(m[1])) broken.push('SKILL.md 行' + (i + 1) + ' #' + m[1])
    }
  })
  return { broken }
}

function verify(file) {
  const text = readSpec(file)
  const skillText = fs.readFileSync(SKILL, 'utf8')
  const forward = checkForward(text)
  const backward = checkBackward(text)
  const unjudged = checkUnjudged(text)
  const subTags = checkSubTags(text)
  const docDefs = checkDocDefs(text)
  const exclusion = checkMutualExclusion(text)
  const links = checkLinks(text)
  const routing = checkRoutingTable(skillText, text)
  const skillLinks = checkSkillLinks(skillText, text)
  const problems = []
  if (forward.inconclusive) problems.push(forward.inconclusive)
  if (forward.missing.length) {
    problems.push('登记在 §0.1 却不落进 §0.5 真值源表的字段：' + forward.missing.join('、'))
  }
  if (backward.inconclusive) problems.push(backward.inconclusive)
  if (backward.unknown.length) {
    problems.push('§0.5 表点出但 §0.1 未登记的字段：' + backward.unknown.join('、'))
  }
  if (unjudged.reason) problems.push(unjudged.reason)
  if (subTags.inconclusive) problems.push(subTags.inconclusive)
  if (subTags.missing.length) {
    problems.push('登记在 §0.2 却不落进 §0.5 真值源表的子标签：' + subTags.missing.join('、'))
  }
  if (docDefs.inconclusive) problems.push(docDefs.inconclusive)
  if (docDefs.missing.length) {
    problems.push('登记在 §0.3 却不落进 §0.5 真值源表的定义项：' + docDefs.missing.join('、'))
  }
  if (exclusion.reason) problems.push(exclusion.reason)
  if (exclusion.conflicts.length) {
    problems.push(
      '同一构件同时落在"允许来源"与"不参与判定"两处，判定者得到互斥答案：' + exclusion.conflicts.join('、'),
    )
  }
  if (links.broken.length) {
    problems.push('文档内锚点不可解析（读者按链接取回会失败）：' + links.broken.join('、'))
  }
  if (routing.inconclusive) problems.push(routing.inconclusive)
  if (routing.missing.length) {
    problems.push('路由表的「字段→条目编号」与实际标题不符：' + routing.missing.join('、'))
  }
  if (skillLinks.broken.length) {
    problems.push('SKILL.md 的链接不可解析（入口指向不存在的章节即取回失败）：' + skillLinks.broken.join('、'))
  }
  return { problems, forward, backward, unjudged, subTags, docDefs, exclusion, links, routing, skillLinks }
}

module.exports = {
  SPEC,
  SKILL,
  MARK,
  UNJUDGED,
  readSpec,
  section,
  tableRows,
  isDivider,
  isHeader,
  backticked,
  cardFields,
  subTagFields,
  docDefItems,
  truthRows,
  unjudgedRow,
  allowedRows,
  truthSourceFields,
  checkForward,
  checkBackward,
  checkUnjudged,
  checkSubTags,
  checkDocDefs,
  checkMutualExclusion,
  checkLinks,
  checkSkillLinks,
  checkRoutingTable,
  headingSlugs,
  verify,
}

if (require.main === module) {
  const file = process.argv[2]
  const result = verify(file)
  for (const p of result.problems) console.log('不合规：' + p)
  console.log(
    result.problems.length === 0
      ? '规范册校验通过（§0.1／§0.2／§0.3 三类登记与 §0.5 双向完备，且互斥）'
      : '规范册校验未通过',
  )
  process.exit(result.problems.length === 0 ? 0 : 1)
}
