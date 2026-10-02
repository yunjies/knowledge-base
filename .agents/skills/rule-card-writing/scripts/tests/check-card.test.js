'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const fs = require('node:fs')

const check = require('../check-card.js')

const SPEC = check.SPEC

function specText() {
  return fs.readFileSync(SPEC, 'utf8')
}

// 工程内真实卡片文档：校验器必须有真素材可跑，否则测试只是自说自话。
const REAL = path.join(__dirname, '..', '..', '..', '..', '..', 'knowledge-repository', 'agent-constraints.md')

const MINIMAL = [
  '# 示例册',
  '',
  '## R-01 一条规则',
  '- **动作**: 核对变更',
  '- **产出物**: 核对记录',
  '  - **形态**: 逐条记录',
  '  - **判定口径**: 每条都有结论',
  '',
].join('\n')

test('卡片校验：判据取自规范文本，不得在脚本内复制', () => {
  const spec = specText()
  const fields = check.fieldRows(spec)
  assert.ok(fields.length > 0, '§0.1 的字段行必须能被提取，否则整个校验是空转的')
  assert.ok(
    fields.some((f) => f.field === 'action' && f.required === '必填'),
    'action 的必填性必须从规范读出：' + JSON.stringify(fields.slice(0, 3)),
  )
  assert.match(check.idPattern(spec), /^\^\[A-Z\]/, 'id 正则必须从规范读出')
  assert.ok(check.subTagNames(spec).includes('判定口径'), '§0.2 的子标签必须能被提取')
})

test('卡片校验：合规的最小卡片通过', () => {
  const result = check.checkCards(MINIMAL, specText())
  assert.equal(result.inconclusive, null)
  assert.deepEqual(result.problems, [], JSON.stringify(result.problems, null, 1))
})

test('卡片校验：工程内真实卡片文档通过', () => {
  if (!fs.existsSync(REAL)) return
  const result = check.checkCards(fs.readFileSync(REAL, 'utf8'), specText())
  assert.equal(result.inconclusive, null, '真实文档必须能被解析为卡片')
  assert.ok(result.cards.length > 0, '真实文档必须解析出卡片：' + JSON.stringify(result))
  assert.deepEqual(result.problems, [], JSON.stringify(result.problems, null, 1))
})

test('卡片校验：缺必填字段必须被报出', () => {
  const broken = MINIMAL.replace('- **动作**: 核对变更\n', '')
  const result = check.checkCards(broken, specText())
  assert.ok(
    result.problems.some((p) => p.includes('动作')),
    '缺必填必须报出，否则「必填」形同虚设：' + JSON.stringify(result.problems, null, 1),
  )
})

test('卡片校验：id 不合规必须被报出，且不得静默跳过该卡片', () => {
  const broken = MINIMAL.replace('## R-01 ', '## r-1 ')
  const result = check.checkCards(broken, specText())
  assert.equal(result.cards.length, 1, 'id 不合规的卡片仍须被识别为卡片，静默跳过等于放过它')
  assert.ok(
    result.problems.some((p) => p.includes('不匹配')),
    'id 不合规必须报出：' + JSON.stringify(result.problems, null, 1),
  )
})

test('卡片校验：未登记的标签与子标签必须被报出', () => {
  const badLabel = check.checkCards(MINIMAL.replace('- **动作**:', '- **依据**:'), specText())
  assert.ok(badLabel.problems.some((p) => p.includes('依据')), JSON.stringify(badLabel.problems))
  const badSub = check.checkCards(MINIMAL.replace('  - **判定口径**:', '  - **说明**:'), specText())
  assert.ok(badSub.problems.some((p) => p.includes('说明')), JSON.stringify(badSub.problems))
})

test('卡片校验：产出物缺两种判据必须被报出', () => {
  const broken = MINIMAL.replace('  - **判定口径**: 每条都有结论\n', '')
  const result = check.checkCards(broken, specText())
  assert.ok(
    result.problems.some((p) => p.includes('至少出现其一')),
    '产出物没有任何判据时必须报出：' + JSON.stringify(result.problems, null, 1),
  )
})

test('卡片校验：无卡片的文档须判为无法定论，而不是通过', () => {
  const result = check.checkCards('# 只是标题\n\n一段正文。\n', specText())
  assert.notEqual(result.inconclusive, null, '发现不到卡片时必须判为无法定论，空转通过等于把校验关掉')
})

test('卡片校验：代码围栏内的样例标题不得被当成本文档的卡片', () => {
  const withFence = MINIMAL + '\n```markdown\n## R-99 围栏内的样例\n- **动作**: 样例\n```\n'
  const result = check.checkCards(withFence, specText())
  assert.equal(result.cards.length, 1, '围栏内的样例不是真卡片，计入即误报：' + JSON.stringify(result.cards.map((c) => c.id)))
})
