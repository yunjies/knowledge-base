import assert from "node:assert/strict"
import { test } from "node:test"
import { registerDomainTools } from "../scripts/registration.js"

const toolNames = [
  "get_version_control_instructions",
  "get_access_paths",
  "get_test_specification",
  "get_knowledge_resource",
  "advance_review",
  "manage_domain_knowledge"
]

function fakeRuntime() {
  return Object.fromEntries([
    "getVersionControlInstructions",
    "getAccessPaths",
    "getTestSpecification",
    "getKnowledgeResource",
    "advanceReview",
    "manageKnowledge"
  ].map(name => [name, async (args, exec) => ({ handler: name, args, domainId: exec.domainId })]))
}

test("registration exposes and executes every declared host tool", async () => {
  const registered = []
  let cleanup
  const ctx = {
    tools: {
      register(tool) {
        registered.push(tool)
        return () => registered.splice(registered.indexOf(tool), 1)
      }
    },
    effect(create) {
      cleanup = create()
    }
  }
  const defineTool = definition => definition
  registerDomainTools(ctx, { domainId: "knowledge-base-operations", domainRoot: ".agents/domain-agents/test" }, defineTool, () => fakeRuntime())
  assert.deepEqual(registered.map(tool => tool.name), toolNames)
  const args = [
    { offset: 1, limit: 1 },
    {},
    { changeKind: "docs" },
    { resourceId: "version-control", offset: 1, limit: 1 },
    {},
    { action: "list" }
  ]
  for (let index = 0; index < registered.length; index += 1) {
    const result = await registered[index].execute(args[index], { agent: { id: "session-test" }, signal: new AbortController().signal })
    assert.equal(result.ok, true, registered[index].name)
    assert.equal(result.domainId, "knowledge-base-operations", registered[index].name)
    assert.equal(typeof registered[index].output.render(args[index], result)[0].text, "string")
    assert.equal(registered[index].output.schema.properties.ok.required, true)
  }
  assert.equal(registered.at(-1).isConcurrencySafe({ action: "list" }), true)
  assert.equal(registered.at(-1).isConcurrencySafe({ action: "update" }), false)
  cleanup()
  assert.deepEqual(registered, [])
})

test("registration uses explicit schemas for retrieval and CRUD arguments", () => {
  const registered = []
  const ctx = {
    tools: { register(tool) { registered.push(tool); return () => {} } },
    effect(create) { create() }
  }
  registerDomainTools(ctx, {}, definition => definition, () => fakeRuntime())
  const byName = new Map(registered.map(tool => [tool.name, tool]))
  assert.equal(byName.get("get_knowledge_resource").parameters.resourceId.required, true)
  assert.equal(byName.get("get_test_specification").parameters.changeKind.required, true)
  assert.deepEqual(byName.get("manage_domain_knowledge").parameters.action.enum, ["list", "get", "create", "update", "delete"])
  assert.equal(byName.get("advance_review").parameters.state.type, "json")
})
