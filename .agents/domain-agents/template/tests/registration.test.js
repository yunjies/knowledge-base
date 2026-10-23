import assert from "node:assert/strict"
import { test } from "node:test"
import { createChildRunOwner, createDomainChildRunner } from "../scripts/child-runner.js"
import { buildCoordinatorToolDefinitions, buildDomainToolDefinitions, registerDomainTools } from "../scripts/registration.js"
import { runTool } from "../scripts/domain-runtime.js"
import { DomainToolError } from "../scripts/engine.js"

function scopedContext() {
  const registered = []
  const state = { guard: undefined, restriction: undefined, prompt: undefined, cleanup: undefined }
  const ctx = {
    tools: {
      register(tool) {
        registered.push(tool)
        return () => registered.splice(registered.indexOf(tool), 1)
      },
      restrict(filter) {
        state.restriction = filter
        return () => { state.restriction = undefined }
      },
      guard(guard) {
        state.guard = guard
        return () => { state.guard = undefined }
      },
      presentAs(mode) {
        state.mode = mode
        return () => { state.mode = undefined }
      }
    },
    systemPrompt: {
      section(section) {
        state.prompt = section
        return () => { state.prompt = undefined }
      }
    },
    effect(create) {
      state.cleanup = create()
    }
  }
  return { ctx, registered, state }
}

function scope(domainId, repositoryId, methodId) {
  const resource = { id: `${domainId}-instructions`, kind: "instructions", title: `${domainId} instructions`, path: `assets/domain-knowledge/${domainId}/instructions.md`, format: "markdown", maxBytes: 1000 }
  const repository = { id: repositoryId, root: `assets/projects/${repositoryId}`, readPaths: ["src/**"], denyPaths: [".git/**"], maxFileBytes: 1000, maxLines: 100 }
  const operation = { id: "remote-operation", repositoryId, methodId, resourceIds: [resource.id] }
  const changeKind = { id: "source-change", layers: ["static"], resourceIds: [resource.id] }
  return {
    domainId,
    repository,
    manifest: { operationMethods: [operation], changeKinds: [changeKind] },
    indexes: { resources: new Map([[resource.id, resource]]) }
  }
}

function assertNoRequiredArrays(value) {
  if (value === null || typeof value !== "object") return
  if (Array.isArray(value)) {
    for (const item of value) assertNoRequiredArrays(item)
    return
  }
  assert.equal(Array.isArray(value.required), false)
  for (const child of Object.values(value)) assertNoRequiredArrays(child)
}

test("coordinator exposes only domain discovery and one-shot delegation", () => {
  const definitions = buildCoordinatorToolDefinitions({}, { domainKnowledgeRoot: "assets/domain-knowledge" }, definition => definition, async () => ({}))
  assert.deepEqual(definitions.map(tool => tool.name), ["list_domain_knowledge", "run_domain_agent"])
  assert.equal(definitions[1].isConcurrencySafe(), false)
  assert.equal(definitions[0].isConcurrencySafe(), true)
})

test("tool schemas expose deterministic selection and bounded reads", () => {
  const coordinator = buildCoordinatorToolDefinitions({}, {}, definition => definition, async () => ({}))
  const run = coordinator.find(tool => tool.name === "run_domain_agent")
  assert.equal(run.parameters.domainId.required, true)
  assert.equal(run.parameters.repositoryId.required, true)
  assert.equal(run.parameters.task.required, true)
  assert.equal(run.output.schema.oneOf[0].properties.childSessionId.required, true)
  assert.equal(run.output.schema.oneOf[1].properties.error.required, true)
  const scoped = buildDomainToolDefinitions({}, scope("sample-domain", "sample-repo", "git-cli"), definition => definition)
  const byName = new Map(scoped.map(tool => [tool.name, tool]))
  for (const tool of [...coordinator, ...scoped]) {
    assertNoRequiredArrays(tool.parameters)
    assertNoRequiredArrays(tool.output.schema)
  }
  assert.equal(byName.get("get_operation_method").parameters.operationId.required, true)
  assert.equal(byName.get("get_operation_method").output.schema.oneOf[0].properties.methodId.required, true)
  const knowledge = byName.get("get_knowledge_resource")
  assert.equal(knowledge.parameters.resourceId.required, true)
  const [knowledgeSuccess, knowledgeFailure] = knowledge.output.schema.oneOf
  assert.equal(knowledgeSuccess.properties.ok.const, true)
  assert.equal(knowledgeSuccess.properties.domainId.required, true)
  assert.equal(knowledgeFailure.properties.ok.const, false)
  assert.equal(knowledgeFailure.properties.error.required, true)
  assert.equal(knowledgeFailure.properties.domainId, undefined)
  assert.equal(byName.get("get_project_source").parameters.relativePath.required, true)
  const lint = byName.get("run_domain_knowledge_lint")
  assert.deepEqual(lint.parameters, {})
  assert.equal(lint.isConcurrencySafe(), false)
  assert.equal(lint.timeoutMs, 600000)
  const lintFields = ["domainId", "repositoryId", "command", "exitCode", "passed", "stdout", "stderr", "outputTruncated", "errorMessage"]
  for (const field of lintFields) assert.equal(lint.output.schema.oneOf[0].properties[field].required, true)
  assert.match(lint.description, /fixed command/)
  const audit = byName.get("submit_audit_findings")
  assert.equal(audit.parameters.findings.required, true)
  assert.equal(audit.parameters.findings.items.required, undefined)
  for (const field of ["title", "severity", "claim", "counterargument", "falsificationCondition", "relativePath", "startLine", "endLine"]) {
    assert.equal(audit.parameters.findings.items.properties[field].required, true)
  }
  const auditOutput = audit.output.schema.oneOf[0]
  assert.equal(auditOutput.properties.findings.items.properties.evidence.properties.relativePath.required, true)
  assert.equal(auditOutput.properties.findings.required, true)
  assert.equal(audit.output.schema.oneOf[1].properties.findings, undefined)
})

test("domain tool success schemas require every runtime result field", () => {
  const tools = new Map(buildDomainToolDefinitions({}, scope("sample-domain", "sample-repo", "git-cli"), definition => definition).map(tool => [tool.name, tool]))
  const requiredSuccessFields = {
    get_access_paths: ["domainId", "repositoryId", "repositoryRoot", "readPaths", "denyPaths", "resourceIds", "operationIds"],
    get_operation_method: ["domainId", "repositoryId", "operationId", "methodId", "resourceIds"],
    get_knowledge_resource: ["domainId", "resourceId", "kind", "title", "path", "offset", "lines", "totalLines"],
    list_project_files: ["domainId", "repositoryId", "relativePath", "entries"],
    get_project_source: ["domainId", "repositoryId", "relativePath", "offset", "lines", "totalLines"],
    get_test_specification: ["domainId", "id", "layers", "resourceIds"],
    submit_audit_findings: ["domainId", "repositoryId", "findings"]
  }
  for (const [name, fields] of Object.entries(requiredSuccessFields)) {
    const success = tools.get(name).output.schema.oneOf[0]
    for (const field of fields) assert.equal(success.properties[field]?.required, true, `${name} must declare required output ${field}`)
  }
  const knowledgeLines = tools.get("get_knowledge_resource").output.schema.oneOf[0].properties.lines.items.properties
  assert.equal(knowledgeLines.number.required, true)
  assert.equal(knowledgeLines.text.required, true)
  const fileEntries = tools.get("list_project_files").output.schema.oneOf[0].properties.entries.items.properties
  assert.equal(fileEntries.path.required, true)
  assert.equal(fileEntries.type.required, true)
})

test("structured handler failures satisfy the tool's distinct error output branch", async () => {
  const tool = buildDomainToolDefinitions({}, scope("sample-domain", "sample-repo", "git-cli"), definition => definition)
    .find(candidate => candidate.name === "get_knowledge_resource")
  const result = await runTool(async () => { throw new DomainToolError("RESOURCE_NOT_ALLOWED", "resource is not registered") }, {}, {})
  const errorBranch = tool.output.schema.oneOf[1]
  assert.deepEqual(Object.keys(result).sort(), Object.keys(errorBranch.properties).sort())
  assert.deepEqual(Object.keys(result.error).sort(), Object.keys(errorBranch.properties.error.properties).sort())
  assert.equal(result.ok, false)
  assert.equal(errorBranch.properties.ok.const, false)
})

test("one generic tool factory binds independent per-invocation domains", async () => {
  const first = scopedContext()
  const second = scopedContext()
  registerDomainTools(first.ctx, scope("dsh-credentials", "dsh-credentials", "github-cli"), definition => definition, "instructions dsh", ["bash", "read", "run_domain_agent"])
  registerDomainTools(second.ctx, scope("other-domain", "other-repository", "git-cli"), definition => definition, "instructions other", ["bash", "read", "run_domain_agent"])
  assert.deepEqual(first.registered.map(tool => tool.name), ["get_access_paths", "get_operation_method", "get_knowledge_resource", "list_project_files", "get_project_source", "get_test_specification", "run_domain_knowledge_lint", "submit_audit_findings"])
  assert.deepEqual(first.state.restriction, { deny: ["bash", "read", "run_domain_agent"] })
  assert.equal(first.state.mode, "native")
  assert.match(first.state.prompt.text, /dsh-credentials/)
  assert.match(second.state.prompt.text, /other-domain/)
  const firstMethod = await first.registered.find(tool => tool.name === "get_operation_method").execute({ operationId: "remote-operation" }, {})
  const secondMethod = await second.registered.find(tool => tool.name === "get_operation_method").execute({ operationId: "remote-operation" }, {})
  assert.equal(firstMethod.methodId, "github-cli")
  assert.equal(secondMethod.methodId, "git-cli")
  assert.notEqual(firstMethod.domainId, secondMethod.domainId)
  assert.equal(first.state.guard({ name: "run_domain_agent" }), "tool is outside the active domain invocation scope")
  assert.equal(first.state.guard({ name: "get_operation_method" }), undefined)
  first.state.cleanup()
  second.state.cleanup()
  assert.deepEqual(first.registered, [])
  assert.deepEqual(second.registered, [])
})

test("domain tools use host runtime capabilities while registering in the child scope", async () => {
  const child = scopedContext()
  const activeScope = scope("dsh-credentials", "dsh-credentials", "pytest")
  activeScope.workspaceRoot = "/workspace"
  activeScope.indexes.resources.set("domain-tests", {
    id: "domain-tests", kind: "domain-knowledge-test-entry", title: "Domain tests",
    path: "assets/domain-knowledge/dsh-credentials/tests/README.md", maxBytes: 1000
  })
  const runtimeCtx = {
    fs: {
      async lstat() { return undefined },
      async resolve(path, options = {}) { return { targetKey: path.startsWith("/") ? path : `${options.cwd}/${path}` } },
      contains() { return true },
      async stat() { return { type: "file", size: 30, version: "v1" } },
      async *streamText() { yield "pytest assets/domain-knowledge tests" }
    },
    subprocess: {
      async resolveExecutable(name) { assert.equal(name, "uv"); return "/tools/uv" },
      spawn(spec) {
        assert.deepEqual(spec.argv, ["/tools/uv", "run", "--with", "pytest==9.1.1", "pytest", "assets/domain-knowledge/dsh-credentials/tests", "-q"])
        return {
          done: Promise.resolve({ exitCode: 0, signal: null }),
          collected: {
            stdout: { readFrom: () => ({ text: "7 passed", lossy: false }) },
            stderr: { readFrom: () => ({ text: "", lossy: false }) }
          }
        }
      }
    }
  }
  registerDomainTools(child.ctx, activeScope, definition => definition, "domain instructions", [], runtimeCtx)
  const exec = { agent: { session: { header: { cwd: "/workspace" } } }, signal: new AbortController().signal }
  const resource = await child.registered.find(tool => tool.name === "get_knowledge_resource").execute({ resourceId: "domain-tests" }, exec)
  assert.equal(resource.ok, true)
  assert.equal(resource.path, "assets/domain-knowledge/dsh-credentials/tests/README.md")
  assert.equal(resource.lines[0].text, "pytest assets/domain-knowledge tests")
  const lint = await child.registered.find(tool => tool.name === "run_domain_knowledge_lint").execute({}, exec)
  assert.equal(lint.ok, true)
  assert.equal(lint.command, "UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest assets/domain-knowledge/dsh-credentials/tests -q")
  assert.equal(lint.exitCode, 0)
  assert.equal(lint.passed, true)
  assert.equal(lint.stdout, "7 passed")
  assert.equal(lint.stderr, "")
  child.state.cleanup()
})

test("plugin owner disposes all active child handles on unload", async () => {
  let unload
  let disposalCount = 0
  const owner = createChildRunOwner({ effect(create) { unload = create() } })
  owner.track("child-1", { async dispose() { disposalCount += 1 } })
  owner.track("child-2", { async dispose() { disposalCount += 1 } })
  await unload()
  assert.equal(disposalCount, 2)
  let lateDisposed = false
  owner.track("child-3", { async dispose() { lateDisposed = true } })
  assert.equal(lateDisposed, true)
})

test("child runner binds the caller-selected domain before publication and disposes the worker", async () => {
  let createOptions
  let disposed = false
  let userMessage
  let scoped
  const child = {
    id: "child-session",
    session: { snapshotEvents: () => [{ type: "turn/end", data: { reason: { kind: "completed" } } }] },
    followup(message) { userMessage = message },
    async whenIdle() {},
    cancel() {}
  }
  const handle = { agent: child, async dispose() { disposed = true } }
  const parent = {
    id: "parent-session",
    session: { header: { cwd: "/workspace", id: "parent-session" } },
    ctx: {
      tools: { schemas: () => [{ name: "bash" }, { name: "read" }] },
      agents: {
        async create(options) {
          createOptions = options
          await options.setup({ tools: { register: () => () => {}, restrict: () => () => {}, guard: () => () => {} }, systemPrompt: { section: () => () => {} }, effect: create => create() }, child)
          return handle
        }
      }
    }
  }
  let releasedOwner = false
  const owner = { track(id, trackedHandle) { assert.equal(id, "child-session"); assert.equal(typeof trackedHandle.dispose, "function"); return () => { releasedOwner = true } } }
  const runner = createDomainChildRunner({
    createSessionId: () => "child-session",
    childSessionMeta: () => ({ parentSession: "parent-session", origin: "subagent" }),
    resolveChildAgentOptions: () => ({ provider: "test", model: "test-model" }),
    resolveChildDepth: () => 1,
    createUserMessage: message => message,
    finalAssistantOutput: () => [{ type: "text", text: "domain result" }],
    stopReason: () => "completed",
    textOutput: blocks => blocks.map(block => block.text).join("")
  }, { workerPresetId: "minimal" }, async () => "instructions", (agentCtx, scope) => { scoped = scope.domainId }, owner)
  const result = await runner({ args: { task: "inspect source" }, exec: { agent: parent, signal: new AbortController().signal }, scope: {
    domainId: "dsh-credentials",
    repository: { id: "dsh-credentials", root: "assets/projects/dsh-credentials", readPaths: ["src/**"], denyPaths: [".git/**"] },
    indexes: { resources: new Map([["flow", { id: "flow" }]]) },
    manifest: { operationMethods: [{ id: "github-remote", repositoryId: "dsh-credentials" }] }
  } })
  assert.equal(createOptions.parentAgent, parent)
  assert.equal(createOptions.meta.agentPreset, "minimal")
  assert.equal(scoped, "dsh-credentials")
  assert.equal(userMessage.content[0].text.includes("inspect source"), true)
  assert.equal(result.output, "domain result")
  assert.equal(result.completed, true)
  assert.equal(disposed, true)
  assert.equal(releasedOwner, true)
})
