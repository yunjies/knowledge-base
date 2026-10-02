'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

const verify = require('../verify.js')

const SPEC = verify.SPEC

test('规范册：§0.1 登记的每个字段都落进 §0.5 判据真值源表', () => {
  const result = verify.checkForward(verify.readSpec(SPEC))
  assert.equal(result.inconclusive, null, '解析器必须能发现 §0.1 的字段表，否则给出的是空转通过')
  assert.ok(result.registered.length > 0, '§0.1 字段表不得为空：' + JSON.stringify(result.registered))
  assert.deepEqual(
    result.missing,
    [],
    '登记在 §0.1 却不落进 §0.5 真值源表的字段是静默失效的：撰写者写下它期待它约束判定，判定者却只读 §0.5。' +
      '登记该字段的同一次改动里必须给它一行（或移入"不参与判定"行）：' +
      JSON.stringify(result, null, 1),
  )
})

test('规范册：§0.5 真值源表提及的每个字段都在 §0.1 登记', () => {
  const result = verify.checkBackward(verify.readSpec(SPEC))
  assert.equal(result.inconclusive, null, '§0.5 表必须至少点出一个字段，空表会让正向检查空转通过')
  assert.deepEqual(
    result.unknown,
    [],
    '§0.5 表点出了 §0.1 未登记的字段名——名字过期或拼错会让该行指向一个不存在的对象，从而约束不到任何东西：' +
      JSON.stringify(result, null, 1),
  )
})

test('规范册：真值源表保留"不参与判定"行，任何字段都不缺去向', () => {
  const result = verify.checkUnjudged(verify.readSpec(SPEC))
  assert.equal(result.reason, null, result.reason + '：' + JSON.stringify(result, null, 1))
  assert.equal(result.rows.length, 1, '"不参与判定"行必须恰有一行，实得 ' + result.rows.length + ' 行')
  assert.deepEqual(
    result.missing,
    [],
    '每个不承载判定后果的字段都必须落在"不参与判定"行；漏掉一个，装饰性文字就能冒充约束：' +
      JSON.stringify(result, null, 1),
  )
})

test('规范册：§0.2 登记的每个子标签都落进 §0.5 判据真值源表', () => {
  const result = verify.checkSubTags(verify.readSpec(SPEC))
  assert.equal(result.inconclusive, null, '解析器必须能发现 §0.2 的子标签表，否则给出的是空转通过')
  assert.ok(result.registered.length > 0, '§0.2 子标签表不得为空：' + JSON.stringify(result.registered))
  assert.deepEqual(
    result.missing,
    [],
    '登记在 §0.2 却不落进 §0.5 的子标签会被判定者依封闭性拒读，而撰写者以为它生效：' +
      JSON.stringify(result, null, 1),
  )
})

test('规范册：§0.3 登记的每个定义项都落进 §0.5 判据真值源表', () => {
  const result = verify.checkDocDefs(verify.readSpec(SPEC))
  assert.equal(result.inconclusive, null, '解析器必须能发现 §0.3 的定义项表，否则给出的是空转通过')
  assert.ok(result.registered.length > 0, '§0.3 定义项表不得为空：' + JSON.stringify(result.registered))
  assert.deepEqual(
    result.missing,
    [],
    '文档层定义项若在 §0.5 无去向，其缺省语义就无处可读（如 should／may 的词面语义只能由对照表锚定）：' +
      JSON.stringify(result, null, 1),
  )
})

test('规范册：同一构件不得同时落在"允许来源"与"不参与判定"两处', () => {
  const result = verify.checkMutualExclusion(verify.readSpec(SPEC))
  assert.equal(result.reason, null, result.reason)
  assert.deepEqual(
    result.conflicts,
    [],
    '同一构件两处并存会让判定者得到互斥答案，且两处都能援引 §0.5 为依据：' + JSON.stringify(result, null, 1),
  )
})

test('规范册：文档内锚点必须全部可解析', () => {
  const result = verify.checkLinks(verify.readSpec(SPEC))
  assert.deepEqual(
    result.broken,
    [],
    '锚点不可解析时，读者（含按链接取回的 LLM）会导向不存在的章节：' + JSON.stringify(result.broken, null, 1),
  )
})

test('SKILL.md：路由表必须存在，且其「字段→条目编号」与实际标题一致', () => {
  const spec = verify.readSpec(SPEC)
  const skill = require('node:fs').readFileSync(verify.SKILL, 'utf8')
  const result = verify.checkRoutingTable(skill, spec)
  assert.equal(
    result.inconclusive,
    null,
    '路由表是 LLM 在取回规范前唯一可见的定位入口：它若不在 SKILL.md，读者须先打开 700 余行全文才能知道该读哪里',
  )
  assert.ok(result.pairs.length >= 17, '路由表须覆盖 §0.1 登记的每个字段：' + JSON.stringify(result.pairs))
  assert.deepEqual(
    result.missing,
    [],
    '路由表与实际标题不符会让读者取回到错误的条目，比没有路由表更坏：' + JSON.stringify(result.missing, null, 1),
  )
})

test('SKILL.md：指向规范的跨文件链接必须全部可解析', () => {
  const spec = verify.readSpec(SPEC)
  const skill = require('node:fs').readFileSync(verify.SKILL, 'utf8')
  const result = verify.checkSkillLinks(skill, spec)
  assert.deepEqual(
    result.broken,
    [],
    '入口里的跨文件锚点不可解析即取回失败，而该入口正是路由表所在处：' + JSON.stringify(result.broken, null, 1),
  )
})

test('校验器：SKILL.md 路由表错指条目编号时必须被报出', () => {
  const spec = verify.readSpec(SPEC)
  const skill = require('node:fs').readFileSync(verify.SKILL, 'utf8')
  const drifted = skill.replace('`artifact`→F-08', '`artifact`→F-07')
  const result = verify.checkRoutingTable(drifted, spec)
  assert.ok(
    result.missing.includes('artifact→F-07'),
    '路由表指向错误条目时必须报出：' + JSON.stringify(result.missing, null, 1),
  )
})

test('校验器：SKILL.md 路由表整体缺失时必须被报出', () => {
  const spec = verify.readSpec(SPEC)
  const skill = require('node:fs').readFileSync(verify.SKILL, 'utf8')
  const i = skill.indexOf('## 路由表')
  const j = skill.indexOf('## 工序')
  const removed = skill.slice(0, i) + skill.slice(j)
  const result = verify.checkRoutingTable(removed, spec)
  assert.notEqual(result.inconclusive, null, '路由表缺失时必须判为无法定论，而不是静默通过')
})

test('校验器：新增死锚点时必须被报出', () => {
  const text = verify.readSpec(SPEC)
  const injected = text + '\n见 [不存在的章节](#不存在的章节)。\n'
  const result = verify.checkLinks(injected)
  assert.ok(
    result.broken.some((b) => b.includes('不存在的章节')),
    '新增不可解析锚点时必须报出：' + JSON.stringify(result.broken, null, 1),
  )
})

test('规范册：整册校验不得报出任何问题', () => {
  const result = verify.verify()
  assert.deepEqual(result.problems, [], '规范册校验未通过：' + JSON.stringify(result.problems, null, 1))
})

test('校验器：把某子标签从 §0.5 移除时必须被报出，否则子标签层的完备性是空转的', () => {
  const text = verify.readSpec(SPEC)
  const block = verify.section(text, '### 0.5 判定真值源', '## 1. 规则卡片模板')
  const from = text.indexOf(block)
  const drifted = text.slice(0, from) + block.replace('`连接`', '`连接_renamed`') + text.slice(from + block.length)

  const result = verify.checkSubTags(drifted)
  assert.ok(
    result.missing.includes('连接'),
    '§0.5 不再点名某子标签时必须报出，否则子标签可以静默失效：' + JSON.stringify(result, null, 1),
  )
})

test('校验器：把定义项从 §0.5 移除时必须被报出', () => {
  const text = verify.readSpec(SPEC)
  const block = verify.section(text, '### 0.5 判定真值源', '## 1. 规则卡片模板')
  const from = text.indexOf(block)
  const drifted = text.slice(0, from) + block.replace('`模态词面对照表`', '`对照表_renamed`') + text.slice(from + block.length)

  const result = verify.checkDocDefs(drifted)
  assert.ok(
    result.missing.includes('模态词面对照表'),
    '文档层定义项从 §0.5 移除时必须报出：' + JSON.stringify(result, null, 1),
  )
})

test('校验器：同一字段两处并存时必须被报出', () => {
  const text = verify.readSpec(SPEC)
  const block = verify.section(text, '### 0.5 判定真值源', '## 1. 规则卡片模板')
  const from = text.indexOf(block)
  const injected =
    text.slice(0, from) +
    block.replace('| **不参与判定** |', '| **不参与判定** | `artifact`、') +
    text.slice(from + block.length)

  const result = verify.checkMutualExclusion(injected)
  assert.ok(
    result.conflicts.includes('artifact'),
    '同一构件同时进入"允许来源"与"不参与判定"时必须报出：' + JSON.stringify(result, null, 1),
  )
})

test('校验器：字段改名漂出 §0.5 时必须被报出，否则校验是死的', () => {
  const text = verify.readSpec(SPEC)
  const from = text.indexOf(verify.section(text, '### 0.1 标签 ↔ 字段对照', '### 0.2 子标签登记'))
  const to = from + verify.section(text, '### 0.1 标签 ↔ 字段对照', '### 0.2 子标签登记').length
  const drifted =
    text.slice(0, from) + text.slice(from, to).replace(/\| `artifact` \|/, '| `artifact_renamed` |') + text.slice(to)

  const forward = verify.checkForward(drifted)
  assert.ok(
    forward.registered.includes('artifact_renamed'),
    '在 §0.1 内改名后必须仍能被发现，否则本样例什么也证明不了：' + JSON.stringify(forward.registered)
  )
  assert.ok(
    forward.missing.includes('artifact_renamed'),
    '已登记却不在真值源表中的字段必须被报出：' + JSON.stringify(forward, null, 1)
  )
  assert.ok(
    !verify.truthSourceFields(drifted).includes('artifact_renamed'),
    '改名必须只限在 §0.1 内，否则本样例分不清何为真实漂移'
  )
})

test('校验器：§0.5 点出一个未登记字段时必须被报出', () => {
  const text = verify.readSpec(SPEC)
  const from = text.indexOf(verify.section(text, '### 0.5 判定真值源', '## 1. 规则卡片模板'))
  const block = verify.section(text, '### 0.5 判定真值源', '## 1. 规则卡片模板')
  const injected =
    text.slice(0, from) +
    block.replace('| 强度 | `modality`、', '| 强度 | `modality`、`nonexistent_field`、') +
    text.slice(from + block.length)

  const backward = verify.checkBackward(injected)
  assert.ok(
    backward.unknown.includes('nonexistent_field'),
    '§0.5 指向未登记字段时必须被报出，否则该行约束不到任何对象：' + JSON.stringify(backward, null, 1)
  )
})

test('校验器：空表必须判为无法定论，而不是通过', () => {
  const emptied = verify.readSpec(SPEC).replace(/^\s*\|\s*\d+\s*\|\s*`[^`]+`.*$/gm, '')
  const forward = verify.checkForward(emptied)
  assert.notEqual(forward.inconclusive, null, '发现不到任何字段时必须判为无法定论，空转通过等于把校验关掉')
})

test('校验器：章节缺失必须显式抛错，不得静默返回空结果', () => {
  assert.throws(
    () => verify.section('没有任何标题的文本', '### 0.1 标签 ↔ 字段对照', '### 0.2 子标签登记'),
    /找不到章节起点/,
    '章节定位失败必须抛错：静默返回空串会让所有断言在空数据上通过'
  )
})

test('校验器：以自身位置解析规范册，与技能被复制到何处无关', () => {
  assert.equal(path.basename(SPEC), 'rule-card-writing-constraints.md')
  assert.equal(path.basename(path.dirname(SPEC)), 'reference', '规范册应位于技能根的 reference/ 下')
  assert.equal(path.basename(path.dirname(path.dirname(SPEC))), 'rule-card-writing', '解析路径必须锚定技能自身，而非当前工作目录')
})
