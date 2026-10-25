import { createHash } from "node:crypto"
import { DomainToolError, pathPolicyAllows, pathPolicyMayContain, validateRelativePath } from "./engine.js"
import { createInvocationRuntime, readBoundedText, resolveInside } from "./domain-runtime.js"
import { runProjectTests } from "./project-test-runner.js"

const digest = value => createHash("sha256").update(value).digest("hex")
const fail = (code, message) => { throw new DomainToolError(code, message) }
const boundedText = (value, name) => {
  if (typeof value !== "string" || !value.trim() || value.length > 12000) fail("INVALID_DEVELOPMENT_INPUT", `${name} must be nonempty text within 12000 characters`)
  return value
}

export async function createDevelopmentInvocation(ctx, scope, grant, exec) {
  const policy = scope.repository.development
  if (!policy) fail("DEVELOPMENT_NOT_ALLOWED", "repository has no registered development policy")
  if (!grant || Object.keys(grant).some(key => !["requestId", "writeFiles"].includes(key)) || typeof grant.requestId !== "string" || !/^req\.[a-z0-9.-]{1,180}$/.test(grant.requestId)) fail("INVALID_DEVELOPMENT_GRANT", "a requirement record id and exact writeFiles are required")
  if (!Array.isArray(grant.writeFiles) || grant.writeFiles.length < 1 || grant.writeFiles.length > 30 || new Set(grant.writeFiles).size !== grant.writeFiles.length) fail("INVALID_DEVELOPMENT_GRANT", "writeFiles must contain 1 to 30 unique exact paths")
  const policyProvider = ctx.get?.("sandboxPolicy") ?? ctx.sandboxPolicy
  const writePolicy = target => {
    if (typeof policyProvider?.resolve !== "function") fail("WRITE_POLICY_UNAVAILABLE", "session file policy is required for development")
    const resolved = policyProvider.resolve({ session: exec.agent.session })
    if (!["workspace-write", "danger-full-access"].includes(resolved.mode) || resolved.workspaceRoot !== scope.workspaceRoot) fail("WRITE_POLICY_DENIED", "the authorizing session does not permit workspace writes")
    return { ...resolved, mode: "workspace-write", workspaceRoot: target ? ctx.fs.processPath(target) : resolved.workspaceRoot }
  }
  writePolicy()
  const allowed = new Set()
  for (const path of grant.writeFiles) {
    validateRelativePath(path)
    if (/[\*?\[\]{}]/.test(path) || path.split("/").includes(".git") || !pathPolicyAllows(path, scope.repository) || !pathPolicyAllows(path, { readPaths: policy.writePaths, denyPaths: scope.repository.denyPaths })) fail("WRITE_NOT_ALLOWED", "write grant must be inside registered readable and writable paths")
    allowed.add(path)
  }
  const requestPath = `assets/inbox/${grant.requestId}.md`
  const requestTarget = await resolveInside(ctx, requestPath, "assets/inbox", scope.workspaceRoot, exec.signal)
  const requestInfo = await ctx.fs.stat(requestTarget, exec.signal)
  if (!requestInfo || requestInfo.type !== "file") fail("REQUIREMENT_MISSING", "the coordinator must first admit the requirement in inbox")
  let active = false
  let closed = false
  let attempts = 0
  let lastChildCompleted = false
  let preparedTestPlan
  let testEvidence
  let acceptance
  const changes = new Map()
  const developerRuns = []
  const runtime = createInvocationRuntime(ctx, scope)
  const ensureOpen = signal => {
    if (closed || exec.signal.aborted || signal?.aborted) fail("DEVELOPMENT_CLOSED", "development invocation is closed or cancelled")
  }
  const fileState = async (relativePath, signal) => {
    validateRelativePath(relativePath)
    const target = await resolveInside(ctx, `${scope.repository.root}/${relativePath}`, scope.repository.root, scope.workspaceRoot, signal)
    const before = await ctx.fs.stat(target, signal)
    if (!before) return { target, sourceVersion: "absent", content: null }
    if (before.type !== "file") fail("SOURCE_NOT_REGULAR", "development target is not a regular file")
    const content = await readBoundedText(ctx, target, Math.min(scope.repository.maxFileBytes, 50000), signal)
    const after = await ctx.fs.stat(target, signal)
    if (!before.version || before.version !== after?.version) fail("STALE_STORE_VERSION", "file changed during observation")
    return { target, sourceVersion: before.version, content }
  }
  const snapshot = async signal => {
    const records = []
    let bytes = 0
    let entriesSeen = 0
    const walk = async (path, depth) => {
      ensureOpen(signal)
      if (depth > 32 || entriesSeen > 10000) fail("SNAPSHOT_TOO_LARGE", "readable project tree exceeds the snapshot bound")
      const target = await resolveInside(ctx, path ? `${scope.repository.root}/${path}` : scope.repository.root, scope.repository.root, scope.workspaceRoot, signal)
      const entries = await ctx.fs.listDir(target, signal)
      for (const entry of entries) {
        entriesSeen += 1
        const relativePath = path ? `${path}/${entry.name}` : entry.name
        validateRelativePath(relativePath)
        if (relativePath.split("/").includes(".git")) continue
        if (entry.type === "directory" && pathPolicyMayContain(relativePath, scope.repository)) await walk(relativePath, depth + 1)
        else if (entry.type === "file" && pathPolicyAllows(relativePath, scope.repository)) {
          const state = await fileState(relativePath, signal)
          bytes += Buffer.byteLength(state.content ?? "", "utf8")
          if (records.length >= 2000 || bytes > 20000000) fail("SNAPSHOT_TOO_LARGE", "readable project inputs exceed the snapshot bound")
          records.push([relativePath, state.sourceVersion, digest(state.content ?? "")])
        }
      }
    }
    await walk("", 0)
    records.sort((left, right) => left[0].localeCompare(right[0]))
    return digest(JSON.stringify(records))
  }
  const evidence = () => ({
    requestId: grant.requestId,
    writeFiles: [...allowed],
    changes: [...changes.values()].map(({ relativePath, beforeVersion, afterVersion, beforeHash, afterHash }) => ({ relativePath, beforeVersion, afterVersion, beforeHash, afterHash })),
    developerRuns: developerRuns.map(run => ({ ...run })),
    testEvidence: testEvidence ? structuredClone(testEvidence) : null,
    acceptance: acceptance ? structuredClone(acceptance) : null
  })
  return {
    requestId: grant.requestId,
    writeFiles: [...allowed],
    evidence,
    close() { closed = true },
    async runDeveloper(args, childExec, runChild) {
      ensureOpen(childExec.signal)
      if (active) fail("DEVELOPMENT_BUSY", "only one developer or test operation may run at a time")
      if (attempts >= 3) fail("DEVELOPMENT_LIMIT", "developer retry limit reached; return remaining work to the coordinator")
      for (const field of ["plan", "counterargument", "acceptanceCriteria"]) boundedText(args[field], field)
      active = true
      attempts += 1
      lastChildCompleted = false
      preparedTestPlan = undefined
      testEvidence = undefined
      acceptance = undefined
      let childOpen = true
      const observed = new Map()
      const developer = {
        writeFiles: [...allowed],
        async read(args, writeExec) {
          ensureOpen(writeExec.signal)
          if (!childOpen || !allowed.has(args.relativePath)) fail("WRITE_NOT_ALLOWED", "file is not in this developer's exact grant")
          const state = await fileState(args.relativePath, writeExec.signal)
          observed.set(args.relativePath, state.sourceVersion)
          return { relativePath: args.relativePath, sourceVersion: state.sourceVersion, content: state.content }
        },
        async write(args, writeExec) {
          ensureOpen(writeExec.signal)
          if (!childOpen || !allowed.has(args.relativePath)) fail("WRITE_NOT_ALLOWED", "file is not in this developer's exact grant")
          if (typeof args.content !== "string" || args.content.includes("\u0000") || Buffer.byteLength(args.content, "utf8") > Math.min(scope.repository.maxFileBytes, 50000)) fail("INVALID_WRITE", "content must be bounded UTF-8 text without NUL")
          if (!observed.has(args.relativePath) || observed.get(args.relativePath) !== args.expectedVersion) fail("READ_REQUIRED", "read this file and pass its observed version before writing")
          if (args.expectedVersion === "absent") fail("CREATE_NOT_SUPPORTED", "MVP writes replace existing files only; new-file creation requires a no-follow host capability")
          const before = await fileState(args.relativePath, writeExec.signal)
          if (before.sourceVersion !== args.expectedVersion) fail("STALE_STORE_VERSION", "file changed since the developer read it")
          ensureOpen(writeExec.signal)
          const intent = { kind: "replaceIfVersion", version: args.expectedVersion }
          const outcome = await ctx.fs.writeText(before.target, args.content, intent, writeExec.signal, writePolicy(before.target))
          const existing = changes.get(args.relativePath)
          changes.set(args.relativePath, { relativePath: args.relativePath, beforeVersion: existing?.beforeVersion ?? before.sourceVersion, afterVersion: outcome.version, beforeHash: existing?.beforeHash ?? digest(before.content ?? ""), afterHash: digest(args.content), before: existing ? existing.before : before.content, after: args.content })
          observed.set(args.relativePath, outcome.version)
          return { relativePath: args.relativePath, sourceVersion: outcome.version, operation: outcome.operation }
        }
      }
      try {
        const result = await runChild({ args: { task: `Requirement: ${grant.requestId}\nPlan: ${args.plan}\nStrongest counterargument: ${args.counterargument}\nAcceptance criteria: ${args.acceptanceCriteria}\nExact writable files: ${[...allowed].join(", ")}\nImplement only this plan. Read with read_development_file before write_project_file. Do not run tests or delegate.` }, exec: childExec, scope: { ...scope, role: "developer", developer, developmentInvocation: undefined } })
        developerRuns.push({ childSessionId: result.childSessionId, completed: result.completed, stopReason: result.stopReason })
        lastChildCompleted = result.completed === true
        return { ...result, changes: evidence().changes }
      } finally {
        childOpen = false
        active = false
      }
    },
    async getChanges(args, childExec) {
      ensureOpen(childExec.signal)
      const change = changes.get(args.relativePath)
      if (!change) fail("CHANGE_NOT_FOUND", "no recorded change for this file")
      const state = await fileState(args.relativePath, childExec.signal)
      return { ...change, currentVersion: state.sourceVersion, currentMatches: state.sourceVersion === change.afterVersion }
    },
    async prepareTests(_args, childExec) {
      ensureOpen(childExec.signal)
      if (active || !lastChildCompleted) fail("DEVELOPMENT_NOT_READY", "a developer must finish before preparing project validation")
      active = true
      preparedTestPlan = undefined
      testEvidence = undefined
      acceptance = undefined
      try {
        const specification = await runtime.getTestSpecification({ changeKind: policy.changeKind })
        const method = runtime.getOperationMethod({ operationId: policy.operationId })
        const resourceIds = [...new Set([...specification.resourceIds, ...method.resourceIds])]
        const testInstructions = await runtime.getKnowledgeResource({ resourceId: "project-tests", limit: 200 }, childExec)
        if (testInstructions.nextOffset || Buffer.byteLength(testInstructions.lines.map(line => line.text).join("\n"), "utf8") > 50000) fail("TEST_RESOURCE_TOO_LONG", "project test entry must fit in the bounded output before validation")
        preparedTestPlan = {
          changeKind: policy.changeKind,
          operationId: policy.operationId,
          methodId: method.methodId,
          resourceIds,
          layers: [...specification.layers],
          argv: [...policy.argv],
          testEntryVersion: testInstructions.sourceVersion
        }
        return { ...structuredClone(preparedTestPlan), testInstructions }
      } finally { active = false }
    },
    async test(_args, childExec) {
      ensureOpen(childExec.signal)
      if (active || !lastChildCompleted) fail("DEVELOPMENT_NOT_READY", "a developer must finish before project validation")
      if (!preparedTestPlan) fail("TEST_PLAN_NOT_PREPARED", "read registered project-test instructions with prepare_project_tests before execution")
      active = true
      acceptance = undefined
      testEvidence = undefined
      try {
        const currentEntry = await runtime.getKnowledgeResource({ resourceId: "project-tests", limit: 200 }, childExec)
        if (currentEntry.sourceVersion !== preparedTestPlan.testEntryVersion || currentEntry.nextOffset || Buffer.byteLength(currentEntry.lines.map(line => line.text).join("\n"), "utf8") > 50000) fail("STALE_TEST_PLAN", "project test instructions changed or exceed the prepared read")
        for (const resourceId of preparedTestPlan.resourceIds) await runtime.getKnowledgeResource({ resourceId }, childExec)
        const before = await snapshot(childExec.signal)
        const result = await runProjectTests(ctx, scope, childExec)
        const after = await snapshot(childExec.signal)
        testEvidence = { ...result, inputDigest: before, inputUnchanged: before === after, ...structuredClone(preparedTestPlan) }
        if (before !== after) testEvidence.passed = false
        return structuredClone(testEvidence)
      } finally { active = false }
    },
    async accept(args, childExec) {
      ensureOpen(childExec.signal)
      if (active || !lastChildCompleted || changes.size === 0 || !testEvidence?.passed || !testEvidence.inputUnchanged) fail("ACCEPTANCE_NOT_READY", "acceptance requires recorded changes, a completed developer and successful current project tests")
      boundedText(args.review, "review")
      boundedText(args.counterargument, "counterargument")
      boundedText(args.unverified, "unverified")
      if (await snapshot(childExec.signal) !== testEvidence.inputDigest) fail("STALE_TEST_EVIDENCE", "readable project inputs changed after tests; rerun validation")
      for (const change of changes.values()) {
        if ((await fileState(change.relativePath, childExec.signal)).sourceVersion !== change.afterVersion) fail("STALE_TEST_EVIDENCE", "recorded writes no longer match the current files")
      }
      acceptance = { status: "domain-accepted", review: args.review, counterargument: args.counterargument, unverified: args.unverified, inputDigest: testEvidence.inputDigest, finalReviewRequired: true }
      return structuredClone(acceptance)
    },
    async finalize(childExec) {
      if (acceptance && await snapshot(childExec.signal) !== acceptance.inputDigest) acceptance = undefined
      return evidence()
    }
  }
}
