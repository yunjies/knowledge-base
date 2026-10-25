import assert from "node:assert/strict"
import { relative, resolve, isAbsolute, sep } from "node:path"
import { test } from "node:test"
import { createInvocationRuntime, loadDomainScope, listDomainCatalog, runDomainKnowledgeLint, runTool } from "../scripts/domain-runtime.js"
import { DomainToolError } from "../scripts/engine.js"

const workspaceRoot = "/virtual/workspace"
const config = { domainKnowledgeRoot: "assets/domain-knowledge", workerPresetId: "domain-agent-worker" }
const exec = { agent: { id: "parent-session", session: { header: { cwd: workspaceRoot } } }, signal: new AbortController().signal }

class MemoryFs {
  constructor() {
    this.files = new Map()
    this.directories = new Set([workspaceRoot])
    this.symlinks = new Map()
  }

  addDirectory(path) {
    const absolute = resolve(path)
    const parts = absolute.split(sep)
    let current = parts[0] === "" ? sep : parts[0]
    for (const part of parts.slice(parts[0] === "" ? 1 : 1)) {
      current = current === sep ? `${current}${part}` : `${current}${sep}${part}`
      this.directories.add(current)
    }
    this.directories.add(absolute)
  }

  addFile(path, text) {
    const absolute = resolve(path)
    this.addDirectory(resolve(absolute, ".."))
    this.files.set(absolute, { text, version: `v${this.files.size + 1}` })
  }

  addSymlink(path, target) {
    const absolute = resolve(path)
    this.addDirectory(resolve(absolute, ".."))
    this.symlinks.set(absolute, resolve(target))
  }

  async resolve(path, options = {}) {
    const cwd = options.cwd ?? workspaceRoot
    let absolute = isAbsolute(path) ? resolve(path) : resolve(cwd, path)
    const direct = this.symlinks.get(absolute)
    if (direct) absolute = direct
    return { targetKey: absolute, displayPath: absolute }
  }

  contains(parent, child) {
    const result = relative(parent.targetKey, child.targetKey)
    return result === "" || (result !== ".." && !result.startsWith(`..${sep}`) && !isAbsolute(result))
  }

  async stat(target) {
    const file = this.files.get(target.targetKey)
    if (file) return { type: "file", size: Buffer.byteLength(file.text), version: file.version }
    if (this.directories.has(target.targetKey)) return { type: "directory", version: "directory" }
    return undefined
  }

  async lstat(path, options = {}) {
    const cwd = options.cwd ?? workspaceRoot
    const absolute = isAbsolute(path) ? resolve(path) : resolve(cwd, path)
    if (this.symlinks.has(absolute)) return { type: "symlink", version: "link" }
    if (this.files.has(absolute)) return { type: "file", version: this.files.get(absolute).version }
    if (this.directories.has(absolute)) return { type: "directory", version: "directory" }
    return undefined
  }

  async streamText(target) {
    const entry = this.files.get(target.targetKey)
    if (!entry) throw new Error("missing file")
    return (async function* () {
      for (let offset = 0; offset < entry.text.length; offset += 31) yield entry.text.slice(offset, offset + 31)
    })()
  }

  async listDir(target) {
    const prefix = target.targetKey === sep ? sep : `${target.targetKey}${sep}`
    const names = new Set()
    for (const path of [...this.files.keys(), ...this.directories, ...this.symlinks.keys()]) {
      if (!path.startsWith(prefix) || path === target.targetKey) continue
      const rest = path.slice(prefix.length)
      if (rest.length > 0 && !rest.includes(sep)) names.add(rest)
    }
    return [...names].sort().map(name => {
      const path = `${prefix}${name}`
      if (this.symlinks.has(path)) {
        const linked = this.symlinks.get(path)
        const linkedFile = this.files.get(linked)
        if (linkedFile) return { name, type: "file", size: Buffer.byteLength(linkedFile.text), target: { targetKey: linked, displayPath: path } }
        if (this.directories.has(linked)) return { name, type: "directory", target: { targetKey: linked, displayPath: path } }
        return { name, type: "other", target: { targetKey: path, displayPath: path } }
      }
      if (this.directories.has(path)) return { name, type: "directory", target: { targetKey: path, displayPath: path } }
      const file = this.files.get(path)
      return { name, type: "file", size: Buffer.byteLength(file.text), target: { targetKey: path, displayPath: path } }
    })
  }
}

const manifest = {
  schemaVersion: 1,
  domainId: "sample-domain",
  resources: [
    { id: "flow", kind: "implemented-flow", title: "Flow", path: "assets/domain-knowledge/sample-domain/flow.md", format: "markdown", maxBytes: 10000 },
    { id: "github-cli", kind: "version-control", title: "GitHub CLI policy", path: "assets/domain-knowledge/sample-domain/github-cli.md", format: "markdown", maxBytes: 10000 },
    { id: "domain-tests", kind: "domain-knowledge-test-entry", title: "Domain tests", path: "assets/domain-knowledge/sample-domain/tests/README.md", format: "markdown", maxBytes: 10000 }
  ],
  repositories: [
    { id: "sample-repo", root: "assets/projects/sample-repo", readPaths: ["README.md", "src/**"], denyPaths: [".git/**", "**/.env*"], maxFileBytes: 50000, maxLines: 200 }
  ],
  operationMethods: [
    { id: "github-remote", repositoryId: "sample-repo", methodId: "github-cli", resourceIds: ["github-cli"] },
    { id: "domain-knowledge-validation", repositoryId: "sample-repo", methodId: "pytest", resourceIds: ["domain-tests"] }
  ],
  changeKinds: [
    { id: "source-change", layers: ["static"], resourceIds: ["flow"] },
    { id: "domain-knowledge", layers: ["lint"], resourceIds: ["domain-tests"] }
  ]
}

async function setupScope() {
  const fs = new MemoryFs()
  fs.addFile(`${workspaceRoot}/assets/domain-knowledge/catalog.json`, JSON.stringify({ schemaVersion: 1, domains: [{ id: "sample-domain", title: "Sample", repositoryIds: ["sample-repo"], manifestPath: "sample-domain/data/manifest.json" }] }))
  fs.addFile(`${workspaceRoot}/assets/domain-knowledge/sample-domain/data/manifest.json`, JSON.stringify(manifest))
  fs.addFile(`${workspaceRoot}/assets/domain-knowledge/sample-domain/flow.md`, "line one\nline two\nline three")
  fs.addFile(`${workspaceRoot}/assets/domain-knowledge/sample-domain/github-cli.md`, "Use the registered GitHub CLI procedure")
  fs.addDirectory(`${workspaceRoot}/assets/projects/sample-repo/.git`)
  fs.addFile(`${workspaceRoot}/assets/projects/sample-repo/README.md`, "Project readme")
  fs.addFile(`${workspaceRoot}/assets/projects/sample-repo/src/main.ts`, "export const answer = 42\nsecond line")
  fs.addFile(`${workspaceRoot}/assets/projects/sample-repo/src/.env.local`, "secret=hidden")
  fs.addSymlink(`${workspaceRoot}/assets/projects/sample-repo/src/escape.ts`, "/outside/secret.ts")
  fs.addSymlink(`${workspaceRoot}/assets/projects/sample-repo/src/leak.ts`, `${workspaceRoot}/assets/projects/sample-repo/src/.env.local`)
  fs.addSymlink(`${workspaceRoot}/assets/projects/sample-repo/src/alias`, `${workspaceRoot}/assets/projects/sample-repo/src`)
  const context = { fs }
  const scope = await loadDomainScope(context, exec, config, "sample-domain", "sample-repo")
  return { fs, scope, runtime: createInvocationRuntime(context, scope), context }
}

test("catalog and manifest bind a single domain and repository scope", async () => {
  const { context } = await setupScope()
  const result = await listDomainCatalog(context, config, exec)
  assert.deepEqual(result.domains, [{ id: "sample-domain", title: "Sample", repositoryIds: ["sample-repo"] }])
  await assert.rejects(() => loadDomainScope(context, exec, config, "other-domain", "sample-repo"), error => error.code === "UNKNOWN_DOMAIN")
  await assert.rejects(() => loadDomainScope(context, exec, config, "sample-domain", "other-repo"), error => error.code === "UNKNOWN_REPOSITORY")
})

test("method resolution returns the registered enum and instruction resources", async () => {
  const { runtime } = await setupScope()
  assert.deepEqual(runtime.getOperationMethod({ operationId: "github-remote" }), {
    domainId: "sample-domain",
    repositoryId: "sample-repo",
    operationId: "github-remote",
    methodId: "github-cli",
    resourceIds: ["github-cli"]
  })
  assert.throws(() => runtime.getOperationMethod({ operationId: "guessed-method" }), error => error.code === "UNKNOWN_OPERATION")
})

test("knowledge retrieval reads only registered resource ids in bounded lines", async () => {
  const { runtime } = await setupScope()
  const result = await runtime.getKnowledgeResource({ resourceId: "flow", offset: 2, limit: 1 }, exec)
  assert.deepEqual({
    domainId: result.domainId,
    resourceId: result.resourceId,
    kind: result.kind,
    title: result.title,
    path: result.path,
    offset: result.offset,
    totalLines: result.totalLines
  }, {
    domainId: "sample-domain",
    resourceId: "flow",
    kind: "implemented-flow",
    title: "Flow",
    path: "assets/domain-knowledge/sample-domain/flow.md",
    offset: 2,
    totalLines: 3
  })
  assert.equal(result.lines[0].text, "line two")
  assert.equal(result.sourceVersion, "v3")
  const wrapped = await runTool(runtime.getKnowledgeResource.bind(runtime), { resourceId: "flow", offset: 2, limit: 1 }, exec)
  assert.equal(wrapped.ok, true)
  assert.equal(wrapped.domainId, "sample-domain")
  assert.equal(wrapped.resourceId, "flow")
  assert.equal(wrapped.offset, 2)
  assert.equal(wrapped.lines[0].text, "line two")
  await assert.rejects(() => runtime.getKnowledgeResource({ resourceId: "../../README.md" }, exec), error => error.code === "RESOURCE_NOT_ALLOWED")
  await assert.rejects(() => runtime.getKnowledgeResource({ resourceId: "flow", limit: 201 }, exec), error => error.code === "INVALID_RANGE")
})

test("registered knowledge resources reject symlink redirection", async () => {
  const { fs, runtime } = await setupScope()
  fs.addSymlink(`${workspaceRoot}/assets/domain-knowledge/sample-domain/flow.md`, `${workspaceRoot}/assets/projects/sample-repo/src/.env.local`)
  await assert.rejects(() => runtime.getKnowledgeResource({ resourceId: "flow" }, exec), error => error.code === "PATH_SYMLINK")
})

test("source listing and reading obey repository path policies", async () => {
  const { runtime } = await setupScope()
  const listing = await runtime.listProjectFiles({ relativePath: "src" }, exec)
  assert.deepEqual({ domainId: listing.domainId, repositoryId: listing.repositoryId, relativePath: listing.relativePath }, {
    domainId: "sample-domain", repositoryId: "sample-repo", relativePath: "src"
  })
  assert.deepEqual(listing.entries.map(entry => entry.path), ["src/main.ts"])
  const wrappedListing = await runTool(runtime.listProjectFiles.bind(runtime), { relativePath: "src" }, exec)
  assert.equal(wrappedListing.ok, true)
  assert.equal(wrappedListing.domainId, "sample-domain")
  assert.equal(wrappedListing.repositoryId, "sample-repo")
  assert.equal(wrappedListing.relativePath, "src")
  assert.deepEqual(wrappedListing.entries.map(entry => entry.path), ["src/main.ts"])
  const source = await runtime.getProjectSource({ relativePath: "src/main.ts", offset: 2, limit: 1 }, exec)
  assert.deepEqual({ domainId: source.domainId, repositoryId: source.repositoryId, relativePath: source.relativePath, offset: source.offset, totalLines: source.totalLines }, {
    domainId: "sample-domain", repositoryId: "sample-repo", relativePath: "src/main.ts", offset: 2, totalLines: 2
  })
  assert.equal(source.lines[0].text, "second line")
  const wrappedSource = await runTool(runtime.getProjectSource.bind(runtime), { relativePath: "src/main.ts", offset: 2, limit: 1 }, exec)
  assert.equal(wrappedSource.ok, true)
  assert.equal(wrappedSource.domainId, "sample-domain")
  assert.equal(wrappedSource.repositoryId, "sample-repo")
  assert.equal(wrappedSource.relativePath, "src/main.ts")
  assert.equal(wrappedSource.offset, 2)
  assert.equal(wrappedSource.totalLines, 2)
  assert.equal(wrappedSource.lines[0].text, "second line")
  await assert.rejects(() => runtime.getProjectSource({ relativePath: "src/.env.local" }, exec), error => error.code === "PATH_NOT_ALLOWED")
  await assert.rejects(() => runtime.getProjectSource({ relativePath: "src/../README.md" }, exec), error => error.code === "PATH_REJECTED")
  await assert.rejects(() => runtime.getProjectSource({ relativePath: "src/escape.ts" }, exec), error => error.code === "PATH_SYMLINK")
  await assert.rejects(() => runtime.getProjectSource({ relativePath: "src/leak.ts" }, exec), error => error.code === "PATH_SYMLINK")
  await assert.rejects(() => runtime.listProjectFiles({ relativePath: "src/alias" }, exec), error => error.code === "PATH_SYMLINK")
})

test("domain knowledge lint runs only the fixed pytest command and returns bounded evidence", async () => {
  const { context, scope } = await setupScope()
  let spawnSpec
  context.subprocess = {
    async resolveExecutable(command) {
      assert.equal(command, "uv")
      return "/tools/uv"
    },
    spawn(spec) {
      spawnSpec = spec
      return {
        done: Promise.resolve({ exitCode: 0, signal: null }),
        collected: {
          stdout: { readFrom: () => ({ text: "7 passed", lossy: false }) },
          stderr: { readFrom: () => ({ text: "", lossy: false }) }
        }
      }
    }
  }
  const result = await runDomainKnowledgeLint(context, scope, exec)
  assert.deepEqual(spawnSpec.argv, ["/tools/uv", "run", "--with", "pytest==9.1.1", "pytest", "assets/domain-knowledge/sample-domain/tests", "-q"])
  assert.equal(spawnSpec.cwd, workspaceRoot)
  assert.equal(spawnSpec.env.UV_CACHE_DIR, ".uv-cache")
  assert.equal(spawnSpec.signal, exec.signal)
  assert.equal(result.command, "UV_CACHE_DIR=.uv-cache uv run --with pytest==9.1.1 pytest assets/domain-knowledge/sample-domain/tests -q")
  assert.equal(result.exitCode, 0)
  assert.equal(result.passed, true)
  assert.equal(result.stdout, "7 passed")
  assert.equal(result.stderr, "")
})

test("domain knowledge lint reports nonzero exits as failures", async () => {
  const { context, scope } = await setupScope()
  context.subprocess = {
    async resolveExecutable() { return "/tools/uv" },
    spawn() {
      return {
        done: Promise.resolve({ exitCode: 3, signal: null }),
        collected: {
          stdout: { readFrom: () => ({ text: "1 failed", lossy: false }) },
          stderr: { readFrom: () => ({ text: "assertion failed", lossy: false }) }
        }
      }
    }
  }
  const result = await runDomainKnowledgeLint(context, scope, exec)
  assert.equal(result.exitCode, 3)
  assert.equal(result.passed, false)
  assert.equal(result.stdout, "1 failed")
  assert.equal(result.stderr, "assertion failed")
})

test("test plans are registered and unknown change kinds fail closed", async () => {
  const { runtime } = await setupScope()
  assert.deepEqual(await runtime.getTestSpecification({ changeKind: "source-change" }), {
    domainId: "sample-domain",
    id: "source-change",
    layers: ["static"],
    resourceIds: ["flow"]
  })
  await assert.rejects(() => runtime.getTestSpecification({ changeKind: "unknown" }), error => error.code === "UNKNOWN_CHANGE_KIND")
})

test("audit findings return current authorized evidence and allow an explicit empty report", async () => {
  const { runtime } = await setupScope()
  const result = await runtime.submitAuditFindings({ findings: [{
    title: "Example issue", severity: "high", claim: "The behavior violates the contract.",
    counterargument: "The surrounding API might guarantee the invariant.",
    falsificationCondition: "A contract test proves the caller always validates this value.",
    relativePath: "src/main.ts", startLine: 1, endLine: 2
  }] }, exec)
  assert.equal(result.domainId, "sample-domain")
  assert.equal(result.repositoryId, "sample-repo")
  assert.deepEqual(result.findings[0].evidence.lines, [{ number: 1, text: "export const answer = 42" }, { number: 2, text: "second line" }])
  assert.equal(result.findings[0].evidence.sourceVersion, "v6")
  assert.deepEqual((await runtime.submitAuditFindings({ findings: [] }, exec)).findings, [])
  await assert.rejects(() => runtime.submitAuditFindings({ findings: [{ title: "x", severity: "high", claim: "x", counterargument: "x", falsificationCondition: "x", relativePath: "src/.env.local", startLine: 1, endLine: 1 }] }, exec), error => error.code === "PATH_NOT_ALLOWED")
  await assert.rejects(() => runtime.submitAuditFindings({ findings: [{ title: "x", severity: "high", claim: "x", counterargument: "x", falsificationCondition: "x", relativePath: "src/main.ts", startLine: 2, endLine: 3 }] }, exec), error => error.code === "INVALID_FINDING")
  await assert.rejects(() => runtime.submitAuditFindings({ findings: Array(31).fill({}) }, exec), error => error.code === "INVALID_FINDINGS")
})

test("tool wrapper converts domain errors to structured failures", async () => {
  const result = await runTool(async () => { throw new DomainToolError("PATH_NOT_ALLOWED", "denied") }, {}, exec)
  assert.equal(result.ok, false)
  assert.equal(result.error.code, "PATH_NOT_ALLOWED")
})
