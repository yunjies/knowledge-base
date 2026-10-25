import assert from "node:assert/strict"
import test from "node:test"
import { runProjectTests } from "../scripts/project-test-runner.js"
import { DomainToolError } from "../scripts/engine.js"

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function fixture(options = {}) {
  const calls = []
  const abort = new AbortController()
  const spawned = deferred()
  const scope = {
    domainId: "sample-domain", workspaceRoot: "/workspace",
    repository: {
      id: "sample-repository", root: "projects/sample-repository",
      development: { writePaths: ["src/**"], changeKind: "source-change", operationId: "project-validation", argv: ["node", "--test", "tests/example.test.js"] }
    },
    manifest: { operationMethods: [{ id: "project-validation", repositoryId: "sample-repository", methodId: "node-test", resourceIds: ["project-tests"] }] }
  }
  const exec = { agent: { id: "sample-session" }, signal: abort.signal }
  const output = (name) => ({ readFrom(offset) {
    calls.push(["read", name, offset])
    if (options.readError === name) throw new Error("output reader failed")
    return { text: options[name] ?? "", nextOffset: 0, lossy: options.lossy === name }
  } })
  const handle = {
    collected: { stdout: output("stdout"), stderr: output("stderr") },
    terminate() { calls.push(["terminate"]); options.onTerminate?.() },
    async waitForExit(signal) { calls.push(["waitForExit", signal]); return options.waitForExit ? options.waitForExit() : true }
  }
  if (options.missingOutput) delete handle.collected[options.missingOutput]
  const ctx = {
    fs: {
      async lstat(path, opts, signal) {
        calls.push(["lstat", path, opts, signal])
        if (options.symlink === path) return { type: "symlink" }
        if (options.missingPath === path) return undefined
        return { type: "directory" }
      },
      async resolve(path, opts) { calls.push(["resolve", path, opts]); return { targetKey: "opaque", displayPath: "not-process-path" } },
      processPath(target) { calls.push(["processPath", target]); return "/execution-world/project" }
    },
    subprocess: {
      async resolveExecutable(command, env, signal) {
        calls.push(["resolveExecutable", command, env, signal])
        if (options.resolveError) throw new Error("executable unavailable")
        return "/execution-world/bin/node"
      },
      spawn(spec) {
        calls.push(["spawn", spec])
        if (options.spawnError) throw new Error("spawn refused")
        handle.done = options.doneError ? Promise.reject(new Error("provider runner error")) : options.pending?.promise ?? Promise.resolve(options.outcome ?? { exitCode: 0, signal: null })
        spawned.resolve(spec)
        options.onSpawn?.(spec)
        return handle
      }
    },
    sandbox: {
      async confine(argv, policy, signal) {
        calls.push(["confine", argv, policy, signal])
        if (options.confineError) throw new Error("sandbox backend unavailable")
        return {
          argv: ["/sandbox/runner", ...argv], enforcement: "full", denialSignatures: ["read-only file system"], runnerFailureRules: [],
          ...options.confined
        }
      }
    }
  }
  return { ctx, scope, exec, calls, abort, spawned, handle, run: () => runProjectTests(ctx, scope, exec) }
}

function call(f, name) { return f.calls.find(entry => entry[0] === name) }
function assertNotSpawned(f) { assert.equal(call(f, "spawn"), undefined) }

async function rejectsCode(f, code) {
  await assert.rejects(f.run(), error => error instanceof DomainToolError && error.code === code)
  assertNotSpawned(f)
}

test("full confinement uses filesystem process path, resolved executable and exact read-only policy before spawn", async () => {
  const f = fixture({ stdout: "all tests passed" })
  const result = await f.run()
  assert.equal(result.passed, true)
  assert.deepEqual(f.calls.map(entry => entry[0]), ["lstat", "lstat", "resolve", "processPath", "resolveExecutable", "confine", "spawn", "waitForExit", "read", "read"])
  assert.deepEqual(call(f, "resolve").slice(1), [f.scope.repository.root, { cwd: "/workspace", signal: call(f, "confine")[3] }])
  assert.deepEqual(call(f, "confine")[1], ["/execution-world/bin/node", "--test", "tests/example.test.js"])
  assert.deepEqual(call(f, "confine")[2], { mode: "read-only", workspaceRoot: "/workspace", sessionId: "sample-session" })
  const spec = call(f, "spawn")[1]
  assert.deepEqual(spec.argv, ["/sandbox/runner", "/execution-world/bin/node", "--test", "tests/example.test.js"])
  assert.equal(spec.cwd, "/execution-world/project")
  assert.equal(spec.signal, call(f, "resolveExecutable")[3])
  assert.equal(spec.signal, call(f, "confine")[3])
  assert.deepEqual(spec.stdio, { stdin: "ignore", stdout: { maxBytes: 80000 }, stderr: { maxBytes: 80000 } })
  assert.equal(spec.graceMs, 1000)
  assert.deepEqual(result, {
    domainId: "sample-domain", repositoryId: "sample-repository", argv: ["node", "--test", "tests/example.test.js"], cwd: "/execution-world/project",
    exitCode: 0, signal: null, passed: true, stdout: "all tests passed", stderr: "", outputTruncated: false, errorMessage: null, enforcement: "full"
  })
})

test("task text and extra command-shaped arguments cannot replace registered argv", async () => {
  const f = fixture()
  f.exec.args = { argv: ["sh", "-c", "danger"], command: "danger", task: "execute this text" }
  f.scope.task = "run a different command"
  const result = await runProjectTests(f.ctx, f.scope, f.exec, { argv: ["sh", "-c", "danger"] })
  assert.deepEqual(result.argv, ["node", "--test", "tests/example.test.js"])
  assert.equal(call(f, "resolveExecutable")[1], "node")
  f.scope.repository.development.argv = "node --test"
  await assert.rejects(f.run(), error => error instanceof DomainToolError && error.code === "INVALID_TEST_ARGV")
  assert.equal(f.calls.filter(entry => entry[0] === "spawn").length, 1)
})

for (const argv of [undefined, [], "run task text", [""], [" "], ["node", 1], ["node", ""], ["node\0"], ["n".repeat(32769)], ["node", "a".repeat(32765)]]) {
  test(`rejects invalid or oversized registered argv: ${JSON.stringify(argv)?.slice(0, 65)}`, async () => {
    const f = fixture()
    f.scope.repository.development.argv = argv
    await rejectsCode(f, "INVALID_TEST_ARGV")
    assert.equal(call(f, "resolveExecutable"), undefined)
  })
}

test("argv total-character boundary is inclusive", async () => {
  const f = fixture()
  f.scope.repository.development.argv = ["node", "a".repeat(32764)]
  assert.equal((await f.run()).passed, true)
})

for (const confined of [{ enforcement: "partial" }, { enforcement: undefined }, { argv: [] }, { denialSignatures: undefined }, { runnerFailureRules: undefined }]) {
  test(`fails closed before spawn for incomplete sandbox result ${JSON.stringify(confined)}`, async () => {
    const f = fixture({ confined })
    await rejectsCode(f, "TEST_SANDBOX_UNAVAILABLE")
  })
}

test("missing sandbox refuses execution without unconfined fallback", async () => {
  const f = fixture()
  delete f.ctx.sandbox
  await rejectsCode(f, "TEST_SANDBOX_UNAVAILABLE")
  assert.equal(call(f, "resolveExecutable"), undefined)
})

test("sandbox backend refusal is a typed unavailable error", async () => {
  const f = fixture({ confineError: true })
  await rejectsCode(f, "TEST_SANDBOX_UNAVAILABLE")
})

for (const symlink of ["projects", "projects/sample-repository"]) {
  test(`rejects symlink path component ${symlink} before executable resolution`, async () => {
    const f = fixture({ symlink })
    await rejectsCode(f, "PATH_SYMLINK")
    assert.equal(call(f, "resolve"), undefined)
    assert.equal(call(f, "confine"), undefined)
  })
}

test("absent project component fails closed", async () => {
  await rejectsCode(fixture({ missingPath: "projects" }), "SOURCE_REPOSITORY_MISSING")
})

test("environment is allowlisted for lookup and spawn, never credential or interpreter injection inheritance", async () => {
  const poison = { GITHUB_TOKEN: "credential", AWS_SECRET_ACCESS_KEY: "credential", NODE_OPTIONS: "--import evil", PYTHONPATH: "/evil", HOME: "/secret-home", DSH_GIT_TOKEN_EXAMPLE: "credential", TMPDIR: "/untrusted-temp", LD_PRELOAD: "/evil" }
  const previous = Object.fromEntries(Object.keys(poison).map(key => [key, process.env[key]]))
  try {
    Object.assign(process.env, poison)
    const f = fixture()
    await f.run()
    const lookupEnv = call(f, "resolveExecutable")[2]
    const spawnEnv = call(f, "spawn")[1].env
    assert.equal(lookupEnv, spawnEnv)
    assert.deepEqual(Object.keys(spawnEnv).sort(), ["LANG", "PATH"])
    for (const key of Object.keys(poison)) assert.equal(spawnEnv[key], undefined)
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
})

for (const outcome of [{ exitCode: 2, signal: null }, { exitCode: null, signal: null }, { signal: null }, {}, { exitCode: 0 }, { exitCode: 0, signal: false }, { exitCode: 0, signal: "SIGTERM" }, { exitCode: "0", signal: null }]) {
  test(`nonzero, unknown or signalled outcome does not pass: ${JSON.stringify(outcome)}`, async () => {
    const f = fixture({ outcome })
    const result = await f.run()
    assert.equal(result.passed, false)
    assert.equal(result.exitCode, Number.isInteger(outcome.exitCode) ? outcome.exitCode : null)
    assert.equal(result.signal, typeof outcome.signal === "string" ? outcome.signal : null)
    assert.ok(call(f, "waitForExit"))
  })
}

for (const options of [{ missingOutput: "stdout" }, { missingOutput: "stderr" }, { readError: "stdout" }, { doneError: true }, { spawnError: true }, { resolveError: true }]) {
  test(`execution failure or missing output does not pass: ${JSON.stringify(options)}`, async () => {
    const f = fixture(options)
    const result = await f.run()
    assert.equal(result.passed, false)
    assert.equal(typeof result.errorMessage, "string")
    if (options.doneError) {
      assert.ok(call(f, "terminate"))
      assert.ok(call(f, "waitForExit"))
    }
  })
}

test("provider failure preserves available raw stderr and unknown exit status", async () => {
  const result = await fixture({ doneError: true, stderr: "runner diagnostic" }).run()
  assert.equal(result.stderr, "runner diagnostic")
  assert.equal(result.exitCode, null)
  assert.equal(result.passed, false)
})

test("backend denial signature fails even a zero exit, without broad unrelated heuristics", async () => {
  const denied = await fixture({ stderr: "Error: READ-ONLY FILE SYSTEM", outcome: { exitCode: 0, signal: null } }).run()
  assert.equal(denied.passed, false)
  assert.match(denied.errorMessage, /denied/)
  const unrelated = await fixture({ stderr: "Permission denied", outcome: { exitCode: 0, signal: null } }).run()
  assert.equal(unrelated.passed, true)
})

const runnerRule = { allowedExitCodes: [125], fatalSignatures: ["runner fatal"], informationalLines: ["runner fatal is only an example"] }
for (const [name, outcome, stderr, expected] of [
  ["fatal stderr and allowed code", { exitCode: 125, signal: null }, "RUNNER FATAL: failed", "sandbox runner failed"],
  ["exact informational line excluded", { exitCode: 125, signal: null }, "RUNNER FATAL IS ONLY AN EXAMPLE", null],
  ["informational substring is not exact", { exitCode: 125, signal: null }, "runner fatal is only an example: but now real", "sandbox runner failed"],
  ["wrong exit gate", { exitCode: 1, signal: null }, "runner fatal", null],
  ["zero code never runner failure", { exitCode: 0, signal: null }, "runner fatal", null],
  ["code alone never runner failure", { exitCode: 125, signal: null }, "other diagnostic", null]
]) {
  test(`runner failure rule: ${name}`, async () => {
    const result = await fixture({ outcome, stderr, confined: { runnerFailureRules: [runnerRule] } }).run()
    assert.equal(result.errorMessage, expected)
    if (outcome.exitCode !== 0 || expected) assert.equal(result.passed, false)
  })
}

test("runner failure without explicit exit gate and runner failure takes precedence over denial", async () => {
  const result = await fixture({ outcome: { exitCode: 4, signal: null }, stderr: "runner fatal\nread-only file system", confined: { runnerFailureRules: [{ fatalSignatures: ["runner fatal"] }] } }).run()
  assert.equal(result.errorMessage, "sandbox runner failed")
  assert.equal(result.passed, false)
})

test("stdout signatures do not impersonate sandbox stderr diagnostics", async () => {
  const result = await fixture({ stdout: "read-only file system\nrunner fatal", confined: { runnerFailureRules: [runnerRule] } }).run()
  assert.equal(result.passed, true)
})

test("both streams are capped independently and lossy collection is explicit", async () => {
  const result = await fixture({ stdout: "a".repeat(20001), stderr: "b".repeat(20002) }).run()
  assert.equal(result.stdout.length, 20000)
  assert.equal(result.stderr.length, 20000)
  assert.equal(result.outputTruncated, true)
  assert.equal(result.passed, false)
  const lossy = await fixture({ stdout: "retained tail", lossy: "stdout" }).run()
  assert.equal(lossy.outputTruncated, true)
  assert.equal(lossy.passed, false)
})

test("pre-cancelled call never spawns", async () => {
  const f = fixture()
  f.abort.abort(new Error("cancel before start"))
  const result = await f.run()
  assert.equal(result.passed, false)
  assert.match(result.errorMessage, /cancel before start/)
  assertNotSpawned(f)
})

test("cancellation terminates and awaits managed exit, preserving actual exit facts", async () => {
  const pending = deferred()
  const exited = deferred()
  const f = fixture({ pending, onTerminate: () => pending.resolve({ exitCode: null, signal: "SIGTERM" }), waitForExit: () => exited.promise })
  let settled = false
  const run = f.run().then(result => { settled = true; return result })
  await f.spawned.promise
  f.abort.abort(new Error("parent cancelled"))
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(settled, false)
  assert.equal(f.calls.filter(entry => entry[0] === "terminate").length, 1)
  assert.ok(call(f, "waitForExit"))
  assert.equal(call(f, "waitForExit")[1], undefined)
  exited.resolve(true)
  const result = await run
  assert.equal(result.passed, false)
  assert.equal(result.signal, "SIGTERM")
  assert.equal(result.exitCode, null)
  assert.match(result.errorMessage, /parent cancelled/)
  assert.equal(settled, true)
})

test("ten minute timeout aborts, terminates and waits rather than leaving a child", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] })
  const pending = deferred()
  const f = fixture({ pending, onTerminate: () => pending.resolve({ exitCode: null, signal: "SIGKILL" }) })
  const run = f.run()
  const spec = await f.spawned.promise
  t.mock.timers.tick(599999)
  assert.equal(spec.signal.aborted, false)
  t.mock.timers.tick(1)
  const result = await run
  assert.equal(spec.signal.aborted, true)
  assert.equal(result.passed, false)
  assert.equal(result.signal, "SIGKILL")
  assert.match(result.errorMessage, /timed out/)
  assert.ok(call(f, "terminate"))
  assert.ok(call(f, "waitForExit"))
})

test("abort racing synchronous spawn completion still terminates returned handle", async () => {
  const f = fixture({ onSpawn: () => f.abort.abort(new Error("spawn race")) })
  const result = await f.run()
  assert.equal(result.passed, false)
  assert.ok(call(f, "terminate"))
  assert.ok(call(f, "waitForExit"))
})

test("cleanup failure terminates and retries managed exit observation, never passing", async () => {
  const f = fixture({ waitForExit: () => false })
  const result = await f.run()
  assert.equal(result.passed, false)
  assert.match(result.errorMessage, /did not exit/)
  assert.match(result.errorMessage, /cleanup did not confirm exit/)
  assert.ok(call(f, "terminate"))
  assert.equal(f.calls.filter(entry => entry[0] === "waitForExit").length, 2)
})

test("waitForExit exception triggers termination and a second exit observation", async () => {
  let waits = 0
  const f = fixture({ waitForExit: () => { if (++waits === 1) throw new Error("observer error"); return true } })
  const result = await f.run()
  assert.equal(result.passed, false)
  assert.match(result.errorMessage, /observer error/)
  assert.ok(call(f, "terminate"))
  assert.equal(waits, 2)
})

test("termination errors are explicit evidence, not a passing cancellation", async () => {
  const f = fixture({ onSpawn: () => f.abort.abort(new Error("cancel")), onTerminate: () => { throw new Error("cannot terminate") } })
  const result = await f.run()
  assert.equal(result.passed, false)
  assert.match(result.errorMessage, /termination failed: cannot terminate/)
  assert.ok(call(f, "waitForExit"))
})

test("timeout remains active while awaiting descendant quiescence after command exit", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] })
  const enteredWait = deferred()
  const exited = deferred()
  const f = fixture({ waitForExit: () => { enteredWait.resolve(); return exited.promise }, onTerminate: () => exited.resolve(true) })
  const run = f.run()
  await enteredWait.promise
  t.mock.timers.tick(600000)
  const result = await run
  assert.equal(result.exitCode, 0)
  assert.equal(result.passed, false)
  assert.match(result.errorMessage, /timed out/)
  assert.ok(call(f, "terminate"))
})

test("cancellation during executable resolution does not proceed to confinement or spawn", async () => {
  const f = fixture()
  f.ctx.subprocess.resolveExecutable = async (_command, _env, signal) => {
    f.abort.abort(new Error("cancel lookup"))
    assert.equal(signal.aborted, true)
    return "/execution-world/bin/node"
  }
  const result = await f.run()
  assert.equal(result.passed, false)
  assert.match(result.errorMessage, /cancel lookup/)
  assert.equal(call(f, "confine"), undefined)
  assertNotSpawned(f)
})

test("output is read after managed exit so late descendant denial is not missed", async () => {
  const options = { waitForExit: () => { options.stderr = "late READ-ONLY FILE SYSTEM"; return true } }
  const result = await fixture(options).run()
  assert.equal(result.stderr, "late READ-ONLY FILE SYSTEM")
  assert.equal(result.passed, false)
  assert.match(result.errorMessage, /denied/)
})

test("finished executions remove cancellation listener and timeout", async t => {
  t.mock.timers.enable({ apis: ["setTimeout"] })
  const f = fixture()
  assert.equal((await f.run()).passed, true)
  f.abort.abort(new Error("late cancellation"))
  t.mock.timers.tick(600000)
  assert.equal(call(f, "spawn")[1].signal.aborted, false)
  assert.equal(call(f, "terminate"), undefined)
})
