import assert from "node:assert/strict"
import { createHash } from "node:crypto"
import { dirname, isAbsolute, relative, resolve } from "node:path"
import test from "node:test"
import { createDevelopmentInvocation } from "../scripts/development-runtime.js"
import { DomainToolError } from "../scripts/engine.js"
import { registerDomainTools } from "../scripts/registration.js"

const root = "/memory/development"
const repo = "assets/projects/example"
const plan = { plan: "Implement bounded changes", counterargument: "Concurrent edits must reject stale observations", acceptanceCriteria: "Validate current inputs" }
const review = { review: "Reviewed changes and test evidence", counterargument: "Unreadable dependencies are not covered", unverified: "External services and unreadable inputs" }
const completed = { childSessionId: "developer-child", completed: true, stopReason: "completed", output: "implemented" }
const hash = text => createHash("sha256").update(text).digest("hex")
const rejectsCode = (action, code) => assert.rejects(action, error => error instanceof DomainToolError && error.code === code)
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes }); return { promise, resolve } }

class MemoryFs {
  files = new Map()
  directories = new Set([root])
  symlinks = new Map()
  writes = []
  sequence = 0
  addDirectory(path) {
    const absolute = resolve(path)
    if (this.directories.has(absolute)) return
    this.directories.add(absolute)
    if (dirname(absolute) !== absolute) this.addDirectory(dirname(absolute))
  }
  put(path, text) {
    const absolute = resolve(root, path)
    this.addDirectory(dirname(absolute))
    const entry = { text, version: `version-${++this.sequence}` }
    this.files.set(absolute, entry)
    return entry.version
  }
  link(path, target) { this.symlinks.set(resolve(root, path), resolve(root, target)) }
  async resolve(path, options = {}) {
    options.signal?.throwIfAborted()
    const absolute = resolve(options.cwd ?? root, path)
    return { targetKey: this.symlinks.get(absolute) ?? absolute, displayPath: absolute }
  }
  contains(parent, child) {
    const path = relative(parent.targetKey, child.targetKey)
    return path === "" || (!isAbsolute(path) && path !== ".." && !path.startsWith("../"))
  }
  processPath(target) { return target.targetKey }
  async lstat(path, options = {}, signal) {
    signal?.throwIfAborted()
    const absolute = resolve(options.cwd ?? root, path)
    if (this.symlinks.has(absolute)) return { type: "symlink", version: "link" }
    return this.stat({ targetKey: absolute }, signal)
  }
  async stat(target, signal) {
    signal?.throwIfAborted()
    const file = this.files.get(target.targetKey)
    if (file) return { type: "file", size: Buffer.byteLength(file.text), version: file.version }
    if (this.directories.has(target.targetKey)) return { type: "directory", version: "directory" }
    return undefined
  }
  async streamText(target, signal) {
    signal?.throwIfAborted()
    const file = this.files.get(target.targetKey)
    if (!file) throw new Error("missing file")
    return (async function* () { yield file.text })()
  }
  async listDir(target, signal) {
    signal?.throwIfAborted()
    const prefix = `${target.targetKey}/`
    return [...new Set([...this.directories, ...this.files.keys(), ...this.symlinks.keys()])]
      .filter(path => path.startsWith(prefix) && path.slice(prefix.length) && !path.slice(prefix.length).includes("/"))
      .sort().map(path => ({ name: path.slice(prefix.length), type: this.symlinks.has(path) ? "symlink" : this.directories.has(path) ? "directory" : "file" }))
  }
  async writeText(target, content, intent, signal, policy) {
    signal.throwIfAborted()
    this.beforeWrite?.(target, intent)
    const fresh = await this.resolve(target.displayPath)
    const sandboxRoot = resolve(policy.workspaceRoot)
    const freshPath = resolve(fresh.targetKey)
    const sandboxRelative = relative(sandboxRoot, freshPath)
    if (sandboxRelative !== "" && (isAbsolute(sandboxRelative) || sandboxRelative === ".." || sandboxRelative.startsWith("../"))) throw new DomainToolError("FS_SANDBOX_DENIED", "fresh target escaped exact sandbox root")
    const current = this.files.get(target.targetKey)
    if ((intent.kind === "createIfAbsent" && current) || (intent.kind === "replaceIfVersion" && current?.version !== intent.version)) throw new DomainToolError("STALE_STORE_VERSION", "atomic conflict")
    assert.ok(["createIfAbsent", "replaceIfVersion"].includes(intent.kind))
    const version = this.put(target.targetKey, content)
    this.writes.push({ target, content, intent, policy, version })
    return { version, operation: current ? "replaced" : "created" }
  }
}

function fixture(options = {}) {
  const fs = new MemoryFs()
  const abort = new AbortController()
  const exec = { agent: { id: "domain-parent", session: { header: { cwd: root } } }, signal: abort.signal }
  const resource = { id: "project-tests", kind: "project-test-entry", title: "Test instructions", path: `${repo}/tests/README.md`, maxBytes: 10000 }
  const scope = {
    domainId: "example-domain", workspaceRoot: root,
    repository: { id: "example", root: repo, readPaths: ["src/**", "tests/**", "README.md"], denyPaths: ["**/.env*", ".git/**"], maxFileBytes: 50000, maxLines: 200,
      development: { writePaths: ["src/**"], changeKind: "source-change", operationId: "project-validation", argv: ["node", "--test", "tests/project.test.js"] } },
    indexes: { resources: new Map([[resource.id, resource]]) },
    manifest: { operationMethods: [{ id: "project-validation", repositoryId: "example", methodId: "pytest", resourceIds: [resource.id] }], changeKinds: [{ id: "source-change", layers: ["static"], resourceIds: [resource.id] }] }
  }
  fs.put("assets/inbox/req.example.change.md", "Admitted requirement")
  for (const [path, text] of [["src/main.js", "original\n"], ["src/other.js", "other input"], ["tests/README.md", "Run node --test tests/project.test.js; require exit zero"], ["tests/project.test.js", "test input"], ["README.md", "readable dependency"]]) fs.put(`${repo}/${path}`, text)
  const calls = []
  const ctx = { fs,
    sandboxPolicy: { resolve: () => ({ mode: "workspace-write", workspaceRoot: root, sessionId: exec.agent.id }) },
    sandbox: { async confine(argv, policy, signal) {
      calls.push(["confine", argv, policy, signal])
      return { argv: ["/mock/sandbox", ...argv], enforcement: options.enforcement ?? "full", denialSignatures: ["read-only file system"], runnerFailureRules: [] }
    } },
    subprocess: {
      async resolveExecutable(command) { assert.equal(command, "node"); return "/mock/node" },
      spawn(spec) {
        calls.push(["spawn", spec])
        options.onSpawn?.(fs)
        return {
          done: options.pending?.promise ?? Promise.resolve({ exitCode: options.exitCode ?? 0, signal: null }),
          collected: { stdout: { readFrom: () => ({ text: "mock test output", nextOffset: 16, lossy: false }) }, stderr: { readFrom: () => ({ text: options.stderr ?? "", nextOffset: 0, lossy: false }) } },
          terminate() { calls.push(["terminate"]); options.pending?.resolve({ exitCode: null, signal: "SIGTERM" }) },
          async waitForExit() { calls.push(["waitForExit"]); return true }
        }
      }
    }
  }
  const grant = { requestId: "req.example.change", writeFiles: ["src/main.js"] }
  return { fs, scope, exec, abort, ctx, grant, calls, create: () => createDevelopmentInvocation(ctx, scope, grant, exec) }
}

async function write(scope, exec, path = "src/main.js", content = "updated\n") {
  const observed = await scope.developer.read({ relativePath: path }, exec)
  return scope.developer.write({ relativePath: path, expectedVersion: observed.sourceVersion, content }, exec)
}
async function implement(f, invocation, content = "updated\n", result = completed) {
  return invocation.runDeveloper(plan, f.exec, async ({ scope, exec, args }) => {
    assert.equal(scope.role, "developer")
    assert.equal(scope.developmentInvocation, undefined)
    assert.match(args.task, /req.example.change/)
    await write(scope, exec, "src/main.js", content)
    return result
  })
}
async function validateProject(invocation, exec) {
  await invocation.prepareTests({}, exec)
  return invocation.test({}, exec)
}
function mount(f, scope) {
  const tools = new Map()
  const guards = []
  const agentCtx = { effect: fn => fn(), tools: {
    register(tool) { tools.set(tool.name, tool); return () => {} }, restrict: () => () => {}, guard(fn) { guards.push(fn); return () => {} }, presentAs: () => () => {}
  }, systemPrompt: { section: () => () => {} } }
  registerDomainTools(agentCtx, scope, value => value, "Scoped instructions", ["bash", "subagent", "write", "run_code"], f.ctx, async () => completed)
  return { tools, guards }
}

test("developer writes through scoped capability, tests, accepts and finalizes detached evidence", async () => {
  const f = fixture()
  const invocation = await f.create()
  const before = f.fs.files.get(`${root}/${repo}/src/main.js`)
  const result = await implement(f, invocation)
  assert.equal(result.completed, true)
  assert.equal(result.changes.length, 1)
  const change = await invocation.getChanges({ relativePath: "src/main.js" }, f.exec)
  assert.equal(change.before, before.text)
  assert.equal(change.after, "updated\n")
  assert.equal(change.beforeVersion, before.version)
  assert.equal(change.beforeHash, hash(before.text))
  assert.equal(change.afterHash, hash(change.after))
  assert.equal(change.currentMatches, true)
  assert.deepEqual(f.fs.writes[0].intent, { kind: "replaceIfVersion", version: before.version })
  assert.deepEqual(f.fs.writes[0].policy, { mode: "workspace-write", workspaceRoot: `${root}/${repo}/src/main.js`, sessionId: "domain-parent" })
  await rejectsCode(() => invocation.test({}, f.exec), "TEST_PLAN_NOT_PREPARED")
  assert.equal(f.calls.some(call => call[0] === "spawn"), false)
  const prepared = await invocation.prepareTests({}, f.exec)
  assert.deepEqual(prepared.argv, f.scope.repository.development.argv)
  assert.equal(prepared.methodId, "pytest")
  assert.equal(prepared.testInstructions.lines[0].text, "Run node --test tests/project.test.js; require exit zero")
  const tested = await invocation.test({ argv: ["malicious"] }, f.exec)
  assert.equal(tested.passed, true)
  assert.equal(tested.inputUnchanged, true)
  assert.equal(tested.stdout, "mock test output")
  assert.deepEqual(tested.argv, f.scope.repository.development.argv)
  assert.equal(tested.methodId, "pytest")
  assert.deepEqual(tested.resourceIds, ["project-tests"])
  assert.deepEqual(f.calls[0].slice(0, 3), ["confine", ["/mock/node", "--test", "tests/project.test.js"], { mode: "read-only", workspaceRoot: root, sessionId: f.exec.agent.id }])
  assert.deepEqual(f.calls.find(call => call[0] === "spawn")[1].argv, ["/mock/sandbox", "/mock/node", "--test", "tests/project.test.js"])
  const accepted = await invocation.accept(review, f.exec)
  assert.equal(accepted.status, "domain-accepted")
  assert.equal(accepted.finalReviewRequired, true)
  const evidence = await invocation.finalize(f.exec)
  assert.deepEqual(evidence.acceptance, accepted)
  assert.deepEqual(evidence.developerRuns, [{ childSessionId: "developer-child", completed: true, stopReason: "completed" }])
  evidence.changes[0].afterHash = "mutated"
  evidence.testEvidence.passed = false
  evidence.acceptance.status = "mutated"
  assert.equal(invocation.evidence().changes[0].afterHash, hash(change.after))
  assert.equal(invocation.evidence().testEvidence.passed, true)
  assert.equal(invocation.evidence().acceptance.status, "domain-accepted")
})

for (const grant of [null, {}, { requestId: "../escape", writeFiles: ["src/main.js"] }, { requestId: "req.example", writeFiles: [] }, { requestId: "req.example", writeFiles: ["src/main.js", "src/main.js"] }, { requestId: "req.example", writeFiles: ["src/main.js"], command: "shell" }, { requestId: "req.example", writeFiles: Array.from({ length: 31 }, (_, n) => `src/file-${n}.js`) }]) {
  test(`reject malformed authorization ${JSON.stringify(grant)}`, async () => {
    const f = fixture()
    await rejectsCode(() => createDevelopmentInvocation(f.ctx, f.scope, grant, f.exec), "INVALID_DEVELOPMENT_GRANT")
    assert.equal(f.fs.writes.length, 0)
  })
}

test("both registered policy and admitted requirement are mandatory", async () => {
  const f = fixture()
  delete f.scope.repository.development
  await rejectsCode(f.create, "DEVELOPMENT_NOT_ALLOWED")
  const missing = fixture()
  missing.fs.files.delete(`${root}/assets/inbox/req.example.change.md`)
  await rejectsCode(missing.create, "REQUIREMENT_MISSING")
})

for (const [path, code] of [["README.md", "WRITE_NOT_ALLOWED"], ["src/.env.local", "WRITE_NOT_ALLOWED"], ["private/file.js", "WRITE_NOT_ALLOWED"], ["src/*.js", "WRITE_NOT_ALLOWED"], ["src/.git/config", "WRITE_NOT_ALLOWED"], [".git/config", "WRITE_NOT_ALLOWED"], ["../escape", "PATH_REJECTED"], ["src/../README.md", "PATH_REJECTED"], ["/tmp/file", "PATH_REJECTED"], ["src\\file.js", "PATH_REJECTED"]]) {
  test(`reject unsafe or disallowed exact grant ${path}`, async () => {
    const f = fixture()
    f.grant.writeFiles = [path]
    await rejectsCode(f.create, code)
  })
}

test("read policy intersects write policy rather than trusting a broader write pattern", async () => {
  const f = fixture()
  f.scope.repository.development.writePaths.push("private/**")
  f.grant.writeFiles = ["private/file.js"]
  await rejectsCode(f.create, "WRITE_NOT_ALLOWED")
})

for (const path of ["assets/inbox", `${repo}/src`, `${repo}/src/main.js`]) {
  test(`symbolic link component refuses access ${path}`, async () => {
    const f = fixture()
    f.fs.link(path, "/outside")
    if (path === "assets/inbox") await rejectsCode(f.create, "PATH_SYMLINK")
    else { const invocation = await f.create(); await rejectsCode(() => implement(f, invocation), "PATH_SYMLINK") }
    assert.equal(f.fs.writes.length, 0)
  })
}

test("readRequired, exact whitelist and version conflicts prevent writes", async () => {
  const f = fixture()
  const invocation = await f.create()
  await invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => {
    const d = scope.developer
    await rejectsCode(() => d.write({ relativePath: "src/main.js", expectedVersion: "absent", content: "bad" }, exec), "READ_REQUIRED")
    for (const path of ["src/other.js", "src/../main.js", "../escape", ".git/config"]) {
      await rejectsCode(() => d.read({ relativePath: path }, exec), "WRITE_NOT_ALLOWED")
      await rejectsCode(() => d.write({ relativePath: path, expectedVersion: "absent", content: "bad" }, exec), "WRITE_NOT_ALLOWED")
    }
    const observed = await d.read({ relativePath: "src/main.js" }, exec)
    await rejectsCode(() => d.write({ relativePath: observed.relativePath, expectedVersion: "wrong", content: "bad" }, exec), "READ_REQUIRED")
    f.fs.put(`${repo}/src/main.js`, "concurrent change")
    await rejectsCode(() => d.write({ relativePath: observed.relativePath, expectedVersion: observed.sourceVersion, content: "bad" }, exec), "STALE_STORE_VERSION")
    return completed
  })
  assert.equal(f.fs.writes.length, 0)
  assert.deepEqual(invocation.evidence().changes, [])
})

test("absent reads fail closed because no-follow file creation is not available", async () => {
  const f = fixture()
  f.grant.writeFiles = ["src/new.js"]
  const invocation = await f.create()
  await invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => {
    const observed = await scope.developer.read({ relativePath: "src/new.js" }, exec)
    assert.equal(observed.content, null)
    assert.equal(observed.sourceVersion, "absent")
    await rejectsCode(() => scope.developer.write({ relativePath: observed.relativePath, expectedVersion: observed.sourceVersion, content: "created" }, exec), "CREATE_NOT_SUPPORTED")
    return completed
  })
  assert.equal(f.fs.writes.length, 0)
  assert.deepEqual(invocation.evidence().changes, [])
})

for (const content of [null, "contains\0nul", "x".repeat(50001), "汉".repeat(16667)]) {
  test(`invalid write content is rejected (${typeof content}, ${content?.length})`, async () => {
    const f = fixture()
    const invocation = await f.create()
    await invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => {
      const observed = await scope.developer.read({ relativePath: "src/main.js" }, exec)
      await rejectsCode(() => scope.developer.write({ relativePath: observed.relativePath, expectedVersion: observed.sourceVersion, content }, exec), "INVALID_WRITE")
      return completed
    })
    assert.equal(f.fs.writes.length, 0)
  })
}

for (const throws of [false, true]) {
  test(`failed child retains side effects but cannot test or accept (${throws})`, async () => {
    const f = fixture()
    const invocation = await f.create()
    if (throws) await assert.rejects(() => invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => { await write(scope, exec, "src/main.js", "partial"); throw new Error("child crashed") }), /child crashed/)
    else await implement(f, invocation, "partial", { ...completed, completed: false, stopReason: "error" })
    assert.equal(f.fs.files.get(`${root}/${repo}/src/main.js`).text, "partial")
    assert.equal(invocation.evidence().changes.length, 1)
    await rejectsCode(() => invocation.test({}, f.exec), "DEVELOPMENT_NOT_READY")
    await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
    assert.equal((await invocation.finalize(f.exec)).acceptance, null)
    assert.equal(f.calls.length, 0)
  })
}

test("test failure retains real evidence and refuses acceptance", async () => {
  const f = fixture({ exitCode: 1, stderr: "assertion failed" })
  const invocation = await f.create()
  await implement(f, invocation)
  const result = await validateProject(invocation, f.exec)
  assert.equal(result.passed, false)
  assert.equal(result.exitCode, 1)
  assert.equal(result.stderr, "assertion failed")
  await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
})

for (const enforcement of ["partial", "none"]) {
  test(`non-full isolation does not execute or accept (${enforcement})`, async () => {
    const f = fixture({ enforcement })
    const invocation = await f.create()
    await implement(f, invocation)
    await invocation.prepareTests({}, f.exec)
    await rejectsCode(() => invocation.test({}, f.exec), "TEST_SANDBOX_UNAVAILABLE")
    await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
    assert.equal(f.calls.some(call => call[0] === "spawn"), false)
  })
}

for (const path of ["src/main.js", "src/other.js", "tests/project.test.js", "tests/README.md", "README.md", "src/new-input.js"]) {
  test(`any readable input mutation after tests refuses acceptance ${path}`, async () => {
    const f = fixture()
    const invocation = await f.create()
    await implement(f, invocation)
    assert.equal((await validateProject(invocation, f.exec)).passed, true)
    f.fs.put(`${repo}/${path}`, "changed after tests")
    await rejectsCode(() => invocation.accept(review, f.exec), "STALE_TEST_EVIDENCE")
    assert.equal((await invocation.finalize(f.exec)).acceptance, null)
  })
}

test("mutation during successful process execution cannot validate inputs", async () => {
  const f = fixture({ onSpawn: fs => fs.put(`${repo}/src/other.js`, "changed during tests") })
  const invocation = await f.create()
  await implement(f, invocation)
  const result = await validateProject(invocation, f.exec)
  assert.equal(result.exitCode, 0)
  assert.equal(result.inputUnchanged, false)
  assert.equal(result.passed, false)
  await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
})

test("finalization revokes acceptance after post-review mutation", async () => {
  const f = fixture()
  const invocation = await f.create()
  await implement(f, invocation)
  await validateProject(invocation, f.exec)
  await invocation.accept(review, f.exec)
  f.fs.put(`${repo}/README.md`, "post-review mutation")
  assert.equal((await invocation.finalize(f.exec)).acceptance, null)
})

test("revision invalidates prior tests and acceptance but preserves original before-state", async () => {
  const f = fixture()
  const invocation = await f.create()
  await implement(f, invocation)
  await validateProject(invocation, f.exec)
  await invocation.accept(review, f.exec)
  await implement(f, invocation, "third revision")
  const evidence = invocation.evidence()
  assert.equal(evidence.testEvidence, null)
  assert.equal(evidence.acceptance, null)
  assert.equal(evidence.changes.length, 1)
  assert.equal(evidence.changes[0].beforeHash, hash("original\n"))
  assert.equal(evidence.changes[0].afterHash, hash("third revision"))
  await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
  await validateProject(invocation, f.exec)
  assert.equal((await invocation.accept(review, f.exec)).status, "domain-accepted")
})

test("developer tools cannot delegate or test, parent tools cannot write, guards deny bypass", async () => {
  const f = fixture()
  const invocation = await f.create()
  const parent = mount(f, { ...f.scope, developmentInvocation: invocation })
  for (const name of ["write_project_file", "read_development_file"]) assert.equal(parent.tools.has(name), false)
  for (const name of ["run_domain_developer", "run_project_tests", "submit_domain_acceptance"]) assert.ok(parent.tools.has(name))
  await invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => {
    const child = mount(f, scope)
    for (const name of ["run_domain_developer", "run_project_tests", "submit_domain_acceptance", "run_domain_knowledge_lint", "subagent", "bash", "write", "run_code"]) {
      assert.equal(child.tools.has(name), false, name)
      assert.equal(typeof child.guards[0]({ name }), "string", name)
    }
    assert.equal(child.guards[0]({ name: "write_project_file" }), undefined)
    const observed = await child.tools.get("read_development_file").execute({ relativePath: "src/main.js" }, exec)
    assert.equal(observed.ok, true)
    const written = await child.tools.get("write_project_file").execute({ relativePath: "src/main.js", expectedVersion: observed.result.sourceVersion, content: "tool write" }, exec)
    assert.equal(written.ok, true)
    return completed
  })
  assert.equal(invocation.evidence().changes.length, 1)
})

test("retained developer capability closes after child and remains closed during retries", async () => {
  const f = fixture()
  const invocation = await f.create()
  let saved
  await invocation.runDeveloper(plan, f.exec, async ({ scope }) => { saved = scope.developer; return completed })
  await rejectsCode(() => saved.read({ relativePath: "src/main.js" }, f.exec), "WRITE_NOT_ALLOWED")
  await invocation.runDeveloper(plan, f.exec, async () => {
    await rejectsCode(() => saved.write({ relativePath: "src/main.js", expectedVersion: "absent", content: "bad" }, f.exec), "WRITE_NOT_ALLOWED")
    return completed
  })
})

test("three retry limit retains writes, invalid plans do not consume retries", async () => {
  const f = fixture()
  const invocation = await f.create()
  for (let n = 0; n < 4; n++) await rejectsCode(() => invocation.runDeveloper({ ...plan, plan: "" }, f.exec, async () => completed), "INVALID_DEVELOPMENT_INPUT")
  for (let n = 0; n < 3; n++) await implement(f, invocation, `revision ${n}`)
  let ran = false
  await rejectsCode(() => invocation.runDeveloper(plan, f.exec, async () => { ran = true; return completed }), "DEVELOPMENT_LIMIT")
  assert.equal(ran, false)
  assert.equal(invocation.evidence().developerRuns.length, 3)
  assert.equal(f.fs.writes.length, 3)
})

test("active child excludes parallel developer, tests and acceptance", async () => {
  const f = fixture()
  const invocation = await f.create()
  const entered = deferred()
  const release = deferred()
  const running = invocation.runDeveloper(plan, f.exec, async () => { entered.resolve(); await release.promise; return completed })
  await entered.promise
  try {
    await rejectsCode(() => invocation.runDeveloper(plan, f.exec, async () => completed), "DEVELOPMENT_BUSY")
    await rejectsCode(() => invocation.test({}, f.exec), "DEVELOPMENT_NOT_READY")
    await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
  } finally { release.resolve(); await running }
})

for (const mode of ["close", "cancel"]) {
  test(`${mode} blocks additional effects and lifecycle operations, preserving recorded writes`, async () => {
    const f = fixture()
    const invocation = await f.create()
    await invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => {
      const written = await write(scope, exec, "src/main.js", "retained")
      if (mode === "close") invocation.close()
      else f.abort.abort(new Error("cancelled"))
      await rejectsCode(() => scope.developer.write({ relativePath: "src/main.js", expectedVersion: written.sourceVersion, content: "forbidden" }, exec), "DEVELOPMENT_CLOSED")
      return completed
    })
    assert.equal(f.fs.files.get(`${root}/${repo}/src/main.js`).text, "retained")
    assert.equal(invocation.evidence().changes.length, 1)
    await rejectsCode(() => invocation.test({}, f.exec), "DEVELOPMENT_CLOSED")
    await rejectsCode(() => invocation.accept(review, f.exec), "DEVELOPMENT_CLOSED")
    await rejectsCode(() => invocation.runDeveloper(plan, f.exec, async () => completed), "DEVELOPMENT_CLOSED")
    assert.equal(invocation.evidence().acceptance, null)
  })
}

test("pre-cancelled admission cannot create invocation", async () => {
  const f = fixture()
  f.abort.abort(new Error("cancelled before admission"))
  await assert.rejects(f.create)
})

for (const mode of ["read-only", "unavailable", "wrong-root"]) {
  test(`authorizing session policy fails closed (${mode})`, async () => {
    const f = fixture()
    if (mode === "unavailable") delete f.ctx.sandboxPolicy
    else f.ctx.sandboxPolicy.resolve = () => ({ mode: mode === "wrong-root" ? "workspace-write" : mode, workspaceRoot: mode === "wrong-root" ? "/other" : root })
    await rejectsCode(f.create, mode === "unavailable" ? "WRITE_POLICY_UNAVAILABLE" : "WRITE_POLICY_DENIED")
    assert.equal(f.fs.writes.length, 0)
  })
}

test("test instructions changing after preparation invalidate the plan before spawn", async () => {
  const f = fixture()
  const invocation = await f.create()
  await implement(f, invocation)
  await invocation.prepareTests({}, f.exec)
  f.fs.put(`${repo}/tests/README.md`, "changed test instructions")
  await rejectsCode(() => invocation.test({}, f.exec), "STALE_TEST_PLAN")
  assert.equal(f.calls.some(call => call[0] === "spawn"), false)
  await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
})

test("required test instructions must be readable before test spawn", async () => {
  const f = fixture()
  const invocation = await f.create()
  await implement(f, invocation)
  f.fs.files.delete(`${root}/${repo}/tests/README.md`)
  await rejectsCode(() => invocation.prepareTests({}, f.exec), "RESOURCE_MISSING")
  assert.equal(f.calls.some(call => call[0] === "spawn"), false)
  await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
})

test("completed child without actual changes cannot be accepted", async () => {
  const f = fixture()
  const invocation = await f.create()
  await invocation.runDeveloper(plan, f.exec, async () => completed)
  assert.equal((await validateProject(invocation, f.exec)).passed, true)
  await rejectsCode(() => invocation.accept(review, f.exec), "ACCEPTANCE_NOT_READY")
})

test("write policy downgrade after admission refuses side effects", async () => {
  const f = fixture()
  const invocation = await f.create()
  await invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => {
    const observed = await scope.developer.read({ relativePath: "src/main.js" }, exec)
    f.ctx.sandboxPolicy.resolve = () => ({ mode: "read-only", workspaceRoot: root })
    await rejectsCode(() => scope.developer.write({ relativePath: observed.relativePath, expectedVersion: observed.sourceVersion, content: "forbidden" }, exec), "WRITE_POLICY_DENIED")
    return completed
  })
  assert.equal(f.fs.writes.length, 0)
  assert.deepEqual(invocation.evidence().changes, [])
})

test("exact target file sandbox root rejects a symlink swap at the mutation boundary", async () => {
  const f = fixture()
  const invocation = await f.create()
  await invocation.runDeveloper(plan, f.exec, async ({ scope, exec }) => {
    const observed = await scope.developer.read({ relativePath: "src/main.js" }, exec)
    f.fs.beforeWrite = target => f.fs.symlinks.set(target.displayPath, `${root}/${repo}/tests/project.test.js`)
    await rejectsCode(() => scope.developer.write({ relativePath: observed.relativePath, expectedVersion: observed.sourceVersion, content: "escaped" }, exec), "FS_SANDBOX_DENIED")
    return completed
  })
  assert.equal(f.fs.writes.length, 0)
  assert.deepEqual(invocation.evidence().changes, [])
})

test("same-content replacement still invalidates version-bound test evidence", async () => {
  const f = fixture()
  const invocation = await f.create()
  await implement(f, invocation)
  await validateProject(invocation, f.exec)
  f.fs.put(`${repo}/src/other.js`, "other input")
  await rejectsCode(() => invocation.accept(review, f.exec), "STALE_TEST_EVIDENCE")
})

test("cancellation during test spawn terminates managed child and cannot record acceptance", async () => {
  const pending = deferred()
  const f = fixture({ pending, onSpawn: () => f.abort.abort(new Error("cancel during project tests")) })
  const invocation = await f.create()
  await implement(f, invocation)
  await invocation.prepareTests({}, f.exec)
  await rejectsCode(() => invocation.test({}, f.exec), "DEVELOPMENT_CLOSED")
  assert.ok(f.calls.some(call => call[0] === "terminate"))
  assert.ok(f.calls.some(call => call[0] === "waitForExit"))
  assert.equal(invocation.evidence().acceptance, null)
  assert.equal(invocation.evidence().testEvidence, null)
  assert.equal(invocation.evidence().changes.length, 1)
  assert.equal(f.fs.files.get(`${root}/${repo}/src/main.js`).text, "updated\n")
})
