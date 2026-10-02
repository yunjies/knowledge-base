'use strict'

const path = require('node:path')
const fs = require('node:fs')

const SPEC = path.join(__dirname, '..', 'reference', 'rule-card-writing-constraints.md')

const MARK = {
  fieldTableFrom: '### 0.1 标签 ↔ 字段对照',
  fieldTableTo: '### 0.2 子标签登记',
  subTagTableFrom: '### 0.2 子标签登记',
  subTagTableTo: '### 0.3 文档层定义的文本形态',
  docDefTableFrom: '### 0.3 文档层定义的文本形态',
  docDefTableTo: '### 0.4 撰写通则',
}

const HEADING_CELLS = new Set(['#', '字段', '父字段', '定义项'])

function section(text, from, to) {
  const i = text.indexOf(from)
  if (i < 0) throw new Error('规范中找不到章节起点：' + from)
  const j = text.indexOf(to, i + from.length)
  if (j < 0) throw new Error('规范中找不到章节终点：' + to)
  return text.slice(i, j)
}

function isDivider(row) {
  return /^\s*\|[\s:|-]+\|\s*$/.test(row)
}

function isHeader(row) {
  const cells = row.split('|').slice(1, -1)
  return cells.length > 0 && HEADING_CELLS.has(cells[0].trim())
}

// 以下四项均从规范文本提取，规范改动后自行跟随，不在代码里复制判据。
function fieldRows(specText) {
  const block = section(specText, MARK.fieldTableFrom, MARK.fieldTableTo)
  const out = []
  for (const row of block.split('\n')) {
    if (!/^\s*\|/.test(row) || isDivider(row) || isHeader(row)) continue
    const m = /^\s*\|\s*\d+\s*\|\s*`([^`]+)`\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|/.exec(row)
    if (m) out.push({ field: m[1], label: m[2], labelText: m[2], required: m[4].trim() })
  }
  return out
}

function subTagNames(specText) {
  const block = section(specText, MARK.subTagTableFrom, MARK.subTagTableTo)
  const out = []
  for (const row of block.split('\n')) {
    if (!/^\s*\|/.test(row) || isDivider(row) || isHeader(row)) continue
    const m = /^\s*\|\s*[^|]+\|\s*`([^`]+)`\s*\|/.exec(row)
    if (m) out.push(m[1])
  }
  return out
}

function docDefLabels(specText) {
  const block = section(specText, MARK.docDefTableFrom, MARK.docDefTableTo)
  const out = []
  for (const row of block.split('\n')) {
    if (!/^\s*\|/.test(row) || isDivider(row) || isHeader(row)) continue
    const cells = row.split('|').slice(1, -1)
    if (cells.length < 2) continue
    if (!/^(属性行|三列表格|封闭枚举)/.test(cells[1].trim())) continue
    for (const m of cells[1].matchAll(/\*\*([^*]+)\*\*/g)) out.push(m[1])
  }
  return out
}

function idPattern(specText) {
  const m = /正则 `\^\[A-Z\][^`]*`/.exec(specText)
  return m ? m[0].replace(/^正则 `|`$/g, '') : null
}

// ---- 卡片解析：标题行 + 属性行 + 缩进 2 空格的子标签行 ----

function parseCards(docText) {
  const lines = docText.split('\n')
  const cards = []
  let fence = false
  let cur = null
  lines.forEach((line, idx) => {
    if (/^\s*```/.test(line)) {
      fence = !fence
      return
    }
    if (fence) return
    const h = /^(#{1,6})\s+(.*)$/.exec(line)
    if (h) {
      const body = h[2].trim()
      const idm = /^([A-Z][A-Z0-9]{0,7}-[0-9]{2,4})(?:\s+(.*))?$/.exec(body)
      if (idm) {
        cur = { id: idm[1], title: (idm[2] || '').trim(), line: idx + 1, level: h[1].length, fields: [], subTags: [] }
        cards.push(cur)
      } else {
        // 形如 `<短码>-<数字> <标题>` 但 id 不合规者仍是一张卡片：不识别它会让该卡片被静默跳过。
        const near = /^([A-Za-z][A-Za-z0-9]{0,15}-[0-9]{1,4})(?:\s+(.*))?$/.exec(body)
        cur = near
          ? { id: near[1], title: (near[2] || '').trim(), line: idx + 1, level: h[1].length, fields: [], subTags: [] }
          : null
        if (near) cards.push(cur)
      }
      return
    }
    if (!cur) return
    const sub = /^\s{2,}- \*\*([^*]+)\*\*:\s*(.*)$/.exec(line)
    if (sub) {
      cur.subTags.push({ name: sub[1], value: sub[2], line: idx + 1 })
      return
    }
    const f = /^- \*\*([^*]+)\*\*:\s*(.*)$/.exec(line)
    if (f) cur.fields.push({ label: f[1], value: f[2], line: idx + 1 })
  })
  return cards
}

function checkCards(docText, specText) {
  const fields = fieldRows(specText)
  const subs = new Set(subTagNames(specText))
  const docLabels = new Set(docDefLabels(specText))
  const idRe = new RegExp(idPattern(specText))
  const labelToField = new Map(fields.map((f) => [f.label, f.field]))
  const problems = []
  const cards = parseCards(docText)

  if (cards.length === 0) {
    return { cards, problems, inconclusive: '文档中未发现任何形如 `<前缀>-<编号> <标题>` 的卡片标题行，校验无法定论' }
  }

  for (const card of cards) {
    if (!idRe.test(card.id)) problems.push(`行${card.line}：id \`${card.id}\` 不匹配 ${idPattern(specText)}`)

    const present = new Set(card.fields.map((f) => f.label))
    for (const name of present) {
      if (labelToField.has(name)) continue
      if (docLabels.has(name)) continue
      if (subs.has(name)) continue
      problems.push(`行${card.line} 卡片 ${card.id}：标签「${name}」不在 §0.1／§0.2／§0.3 的登记内`)
    }

    for (const f of fields) {
      if (f.required !== '必填') continue
      if (f.label === '标题行首段' || f.label === '标题行次段') continue
      if (f.label.startsWith('——')) continue
      if (!present.has(f.label)) problems.push(`行${card.line} 卡片 ${card.id}：缺少必填字段「${f.label}」`)
    }

    for (const st of card.subTags) {
      if (!subs.has(st.name)) problems.push(`行${st.line} 卡片 ${card.id}：子标签「${st.name}」不在 §0.2 的登记内`)
    }

    const hasRule = card.subTags.some((s) => s.name === '判定口径')
    const hasSemantic = card.subTags.some((s) => s.name === '语义判据')
    if (present.has('产出物') && !hasRule && !hasSemantic) {
      problems.push(`行${card.line} 卡片 ${card.id}：「判定口径」与「语义判据」须至少出现其一`)
    }
  }

  return { cards, problems, inconclusive: null }
}

function read(file) {
  return fs.readFileSync(file, 'utf8')
}

if (require.main === module) {
  const target = process.argv[2]
  const specText = read(SPEC)
  if (!target) {
    console.error('用法：node scripts/check-card.js <被校验的承载文档>')
    process.exit(2)
  }
  if (!fs.existsSync(target)) {
    console.error('被校验的文档不存在：' + target)
    process.exit(2)
  }
  const result = checkCards(read(target), specText)
  if (result.inconclusive) {
    console.error('无法定论：' + result.inconclusive)
    process.exit(2)
  }
  for (const p of result.problems) console.log('不合规：' + p)
  console.log(
    result.problems.length === 0
      ? `卡片校验通过（${result.cards.length} 张卡片；判据取自 reference/，未在脚本内复制）`
      : `卡片校验未通过（${result.cards.length} 张卡片，${result.problems.length} 处问题）`,
  )
  process.exit(result.problems.length === 0 ? 0 : 1)
}

module.exports = { SPEC, section, fieldRows, subTagNames, docDefLabels, idPattern, parseCards, checkCards }
