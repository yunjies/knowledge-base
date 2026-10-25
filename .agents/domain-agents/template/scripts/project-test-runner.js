import { DomainToolError, validateRelativePath } from "./engine.js"

const MAX_ARGV_CHARS = 32768
const MAX_OUTPUT_CHARS = 20000
const TIMEOUT_MS = 600000

function registeredArgv(scope) {
  const argv = scope.repository.development?.argv
  if (!Array.isArray(argv) || argv.length === 0 || argv.some(value => typeof value !== "string" || value.trim().length === 0 || value.includes("\0")) || argv.reduce((size, value) => size + value.length, 0) > MAX_ARGV_CHARS) {
    throw new DomainToolError("INVALID_TEST_ARGV", "registered test argv must contain non-empty strings within 32768 total characters")
  }
  return [...argv]
}

async function projectCwd(ctx, scope, signal) {
  const root = validateRelativePath(scope.repository.root)
  let prefix = ""
  for (const segment of root.split("/")) {
    signal.throwIfAborted()
    prefix = prefix ? `${prefix}/${segment}` : segment
    const info = await ctx.fs.lstat(prefix, { cwd: scope.workspaceRoot }, signal)
    if (info?.type === "symlink") throw new DomainToolError("PATH_SYMLINK", "project root cannot traverse symbolic links")
    if (info?.type !== "directory") throw new DomainToolError("SOURCE_REPOSITORY_MISSING", "project root components must be existing directories")
  }
  const target = await ctx.fs.resolve(root, { cwd: scope.workspaceRoot, signal })
  return ctx.fs.processPath(target)
}

function readOutput(reader) {
  if (!reader) throw new Error("subprocess output reader is unavailable")
  const output = reader.readFrom(0)
  if (typeof output?.text !== "string" || typeof output.lossy !== "boolean") throw new Error("subprocess output is unavailable")
  return { text: output.text.slice(0, MAX_OUTPUT_CHARS), truncated: output.lossy || output.text.length > MAX_OUTPUT_CHARS }
}

function sandboxFailure(confined, exitCode, stderr) {
  const lines = stderr.toLowerCase().split(/\r?\n/)
  if (Number.isInteger(exitCode) && exitCode !== 0) {
    for (const rule of confined.runnerFailureRules) {
      if (rule.allowedExitCodes && !rule.allowedExitCodes.includes(exitCode)) continue
      const informational = new Set((rule.informationalLines ?? []).map(line => line.toLowerCase()))
      if (lines.some(line => !informational.has(line) && rule.fatalSignatures.some(signature => line.includes(signature.toLowerCase())))) return "sandbox runner failed"
    }
  }
  if (confined.denialSignatures.some(signature => stderr.toLowerCase().includes(signature.toLowerCase()))) return "sandbox denied a file effect"
  return null
}

export async function runProjectTests(ctx, scope, exec) {
  const argv = registeredArgv(scope)
  const sandbox = ctx.get?.("sandbox") ?? ctx.sandbox
  if (typeof sandbox?.confine !== "function") throw new DomainToolError("TEST_SANDBOX_UNAVAILABLE", "full read-only file-effect sandbox is required")
  const controller = new AbortController()
  const signal = controller.signal
  const cancel = () => controller.abort(exec.signal.reason ?? new Error("project tests cancelled"))
  if (exec.signal?.aborted) cancel()
  else exec.signal?.addEventListener("abort", cancel, { once: true })
  const timer = setTimeout(() => controller.abort(new Error("project tests timed out after 600000ms")), TIMEOUT_MS)
  let handle
  let confined
  let stopped = false
  let terminateError
  const stop = () => {
    if (!handle || stopped) return
    stopped = true
    try { handle.terminate() } catch (error) { terminateError = error }
  }
  const result = {
    domainId: scope.domainId, repositoryId: scope.repository.id, argv, cwd: null,
    exitCode: null, signal: null, passed: false, stdout: "", stderr: "",
    outputTruncated: false, errorMessage: null, enforcement: null
  }
  signal.addEventListener("abort", stop)
  try {
    signal.throwIfAborted()
    result.cwd = await projectCwd(ctx, scope, signal)
    const env = { PATH: process.env.PATH ?? "/usr/local/bin:/usr/bin:/bin", LANG: "C.UTF-8" }
    const executable = await ctx.subprocess.resolveExecutable(argv[0], env, signal)
    signal.throwIfAborted()
    try {
      confined = await sandbox.confine([executable, ...argv.slice(1)], { mode: "read-only", workspaceRoot: scope.workspaceRoot, sessionId: exec.agent.id }, signal)
    } catch (error) {
      if (signal.aborted) throw signal.reason
      throw new DomainToolError("TEST_SANDBOX_UNAVAILABLE", `read-only sandbox unavailable: ${error.message}`)
    }
    result.enforcement = confined?.enforcement ?? null
    if (confined?.enforcement !== "full" || !Array.isArray(confined.argv) || confined.argv.length === 0 || confined.argv.some(value => typeof value !== "string" || !value.length || value.includes("\0")) || !Array.isArray(confined.denialSignatures) || !Array.isArray(confined.runnerFailureRules)) {
      throw new DomainToolError("TEST_SANDBOX_UNAVAILABLE", "full read-only file-effect sandbox is required")
    }
    signal.throwIfAborted()
    handle = ctx.subprocess.spawn({
      argv: confined.argv, cwd: result.cwd, env, signal, graceMs: 1000,
      stdio: { stdin: "ignore", stdout: { maxBytes: 80000 }, stderr: { maxBytes: 80000 } }
    })
    if (signal.aborted) stop()
    try {
      const outcome = await handle.done
      result.exitCode = Number.isInteger(outcome?.exitCode) ? outcome.exitCode : null
      result.signal = typeof outcome?.signal === "string" ? outcome.signal : null
      if (outcome?.signal !== null && typeof outcome?.signal !== "string") result.errorMessage = "subprocess did not report a valid exit signal"
    } catch (error) {
      result.errorMessage = error?.message ?? String(error)
      stop()
    }
  } catch (error) {
    if (error instanceof DomainToolError) throw error
    result.errorMessage = error?.message ?? String(error)
  } finally {
    if (handle) {
      if (signal.aborted || result.errorMessage) stop()
      try {
        if (!await handle.waitForExit()) throw new Error("subprocess managed range did not exit")
      } catch (error) {
        stop()
        result.errorMessage ??= error?.message ?? String(error)
        try {
          if (!await handle.waitForExit()) result.errorMessage += "; subprocess cleanup did not confirm exit"
        } catch (cleanupError) {
          result.errorMessage += `; subprocess cleanup failed: ${cleanupError?.message ?? String(cleanupError)}`
        }
      }
      for (const name of ["stdout", "stderr"]) {
        try {
          const output = readOutput(handle.collected?.[name])
          result[name] = output.text
          result.outputTruncated ||= output.truncated
        } catch (error) { result.errorMessage ??= error?.message ?? String(error) }
      }
      try {
        result.errorMessage ??= sandboxFailure(confined, result.exitCode, result.stderr)
      } catch (error) { result.errorMessage ??= error?.message ?? String(error) }
      if (result.outputTruncated) result.errorMessage ??= "test output was truncated; complete failure evidence is unavailable"
    }
    if (signal.aborted) result.errorMessage = [signal.reason?.message ?? "project tests cancelled", result.errorMessage].filter(Boolean).join("; ")
    if (terminateError) result.errorMessage = [result.errorMessage, `subprocess termination failed: ${terminateError.message}`].filter(Boolean).join("; ")
    clearTimeout(timer)
    signal.removeEventListener("abort", stop)
    exec.signal?.removeEventListener("abort", cancel)
  }
  result.passed = result.exitCode === 0 && result.signal === null && result.enforcement === "full" && result.errorMessage === null
  return result
}
