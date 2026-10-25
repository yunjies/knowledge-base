import { DomainToolError } from "./engine.js"
import { createInvocationRuntime, listDomainCatalog, loadDomainScope, runDomainKnowledgeLint, runTool } from "./domain-runtime.js"
import { createDevelopmentInvocation } from "./development-runtime.js"

const activeRepositories = new Set()
const record = { type: "object", additionalProperties: true }

const errorResult = {
  type: "object",
  additionalProperties: false,
  properties: {
    code: { type: "string", required: true },
    message: { type: "string", required: true }
  }
}

const textLine = {
  type: "object",
  additionalProperties: false,
  properties: {
    number: { type: "integer", required: true },
    text: { type: "string", required: true }
  }
}

const directoryEntry = {
  type: "object",
  additionalProperties: false,
  properties: {
    path: { type: "string", required: true },
    type: { type: "string", required: true, enum: ["file", "directory"] },
    size: { type: "integer" }
  }
}

function resultOutput(properties) {
  return {
    schema: {
      oneOf: [
        {
          type: "object",
          additionalProperties: false,
          properties: {
            ok: { type: "boolean", const: true, required: true },
            ...properties
          }
        },
        {
          type: "object",
          additionalProperties: false,
          properties: {
            ok: { type: "boolean", const: false, required: true },
            error: { ...errorResult, required: true }
          }
        }
      ]
    },
    render: (_args, value) => [{ type: "text", text: JSON.stringify(value, null, 2) }]
  }
}

function definition(defineTool, name, description, parameters, outputProperties, handler, parallel = true, timeoutMs) {
  return defineTool({
    name,
    description,
    parameters,
    output: resultOutput(outputProperties),
    ...(timeoutMs === undefined ? {} : { timeoutMs }),
    async execute(args, exec) {
      return runTool(handler, args, exec)
    },
    isConcurrencySafe: () => parallel
  })
}

export function buildCoordinatorToolDefinitions(ctx, config, defineTool, runChildAgent) {
  return [
    definition(defineTool, "list_domain_knowledge", "List registered domain packages and their repository identifiers.", {}, {
      domains: {
        type: "array",
        required: true,
        items: {
          type: "object",
          additionalProperties: false,
          properties: {
            id: { type: "string", required: true },
            title: { type: "string", required: true },
            repositoryIds: { type: "array", required: true, items: { type: "string" } }
          }
        }
      }
    }, (args, exec) => listDomainCatalog(ctx, config, exec)),
    definition(defineTool, "run_domain_agent", "Run a scoped domain child. It reads by default; an explicit development grant allows it to delegate bounded source edits and validate them. Changes remain in the checkout on failure; inspect the returned development evidence before further action.", {
      domainId: { type: "string", required: true, description: "Exact domain id from list_domain_knowledge." },
      repositoryId: { type: "string", required: true, description: "Exact repository id registered by the selected domain." },
      task: { type: "string", required: true, description: "Self-contained task for the domain child." },
      development: {
        type: "object", additionalProperties: false, description: "Omit for read-only work. Set only after requirement admission and branch approval; grants source-file create/replace, not commit, deployment or knowledge edits.",
        properties: {
          requestId: { type: "string", required: true, description: "Existing inbox requirement filename without .md." },
          writeFiles: { type: "array", required: true, description: "1 to 30 unique exact repository-relative files within the manifest write policy; no globs.", items: { type: "string" } }
        }
      }
    }, {
      domainId: { type: "string", required: true },
      repositoryId: { type: "string", required: true },
      childSessionId: { type: "string", required: true },
      completed: { type: "boolean", required: true },
      stopReason: { type: "string", required: true },
      output: { type: "string", required: true },
      development: record
    }, async (args, exec) => {
      if (typeof args.task !== "string" || args.task.trim().length === 0 || args.task.length > 24000) throw new DomainToolError("INVALID_TASK", "task must be non-empty and within the task size limit")
      const scope = await loadDomainScope(ctx, exec, config, args.domainId, args.repositoryId)
      const root = await ctx.fs.resolve(scope.repository.root, { cwd: scope.workspaceRoot, signal: exec.signal })
      const key = root.targetKey
      if (activeRepositories.has(key)) throw new DomainToolError("REPOSITORY_BUSY", "another domain invocation owns this repository")
      activeRepositories.add(key)
      let invocation
      try {
        if (args.development !== undefined) {
          invocation = await createDevelopmentInvocation(ctx, scope, args.development, exec)
          scope.developmentInvocation = invocation
        }
        const result = await runChildAgent({ args, exec, scope })
        if (!invocation) return result
        const development = await invocation.finalize(exec)
        if (!result.completed) development.acceptance = null
        return { ...result, development }
      } catch (error) {
        if (!invocation) throw error
        return { domainId: scope.domainId, repositoryId: scope.repository.id, childSessionId: "", completed: false, stopReason: exec.signal.aborted ? "aborted" : "error", output: `Development stopped: ${error instanceof DomainToolError ? error.code : "TOOL_FAILURE"}; inspect recorded side effects.`, development: { ...invocation.evidence(), acceptance: null } }
      } finally {
        invocation?.close()
        activeRepositories.delete(key)
      }
    }, false, 3600000)
  ]
}

export function buildDomainToolDefinitions(ctx, scope, defineTool) {
  const runtime = createInvocationRuntime(ctx, scope)
  return [
    definition(defineTool, "get_access_paths", "Return the resources and source paths authorized for this invocation.", {}, {
      domainId: { type: "string", required: true },
      repositoryId: { type: "string", required: true },
      repositoryRoot: { type: "string", required: true },
      readPaths: { type: "array", required: true, items: { type: "string" } },
      denyPaths: { type: "array", required: true, items: { type: "string" } },
      writePaths: { type: "array", required: true, items: { type: "string" } },
      authorizedWriteFiles: { type: "array", required: true, items: { type: "string" } },
      requestId: { type: "string", required: true },
      resourceIds: { type: "array", required: true, items: { type: "string" } },
      operationIds: { type: "array", required: true, items: { type: "string" } }
    }, runtime.getAccessPaths),
    definition(defineTool, "get_operation_method", "Resolve one registered operation id to its fixed method id and instruction resource ids; method selection is data-driven.", {
      operationId: { type: "string", required: true, description: "Exact operation id from get_access_paths." }
    }, {
      domainId: { type: "string", required: true },
      repositoryId: { type: "string", required: true },
      operationId: { type: "string", required: true },
      methodId: { type: "string", required: true },
      resourceIds: { type: "array", required: true, items: { type: "string" } }
    }, runtime.getOperationMethod),
    definition(defineTool, "get_knowledge_resource", "Read one registered knowledge resource by id and bounded line range; raw paths are not accepted.", {
      resourceId: { type: "string", required: true, description: "Exact resource id returned by get_access_paths or get_operation_method." },
      offset: { type: "integer", description: "1-based first line; defaults to 1." },
      limit: { type: "integer", description: "Maximum lines, from 1 to 200; defaults to 120." }
    }, {
      domainId: { type: "string", required: true },
      resourceId: { type: "string", required: true },
      kind: { type: "string", required: true },
      title: { type: "string", required: true },
      path: { type: "string", required: true },
      sourceVersion: { type: "string" },
      offset: { type: "integer", required: true },
      lines: { type: "array", required: true, items: textLine },
      totalLines: { type: "integer", required: true },
      nextOffset: { type: "integer" }
    }, runtime.getKnowledgeResource),
    definition(defineTool, "list_project_files", "List direct entries under one allowed project directory, with paths relative to the active repository.", {
      relativePath: { type: "string", description: "Optional repository-relative directory; omit to list the repository root." },
      offset: { type: "integer", description: "Zero-based first entry; defaults to 0." },
      limit: { type: "integer", description: "Maximum entries, from 1 to 100; defaults to 100." }
    }, {
      domainId: { type: "string", required: true },
      repositoryId: { type: "string", required: true },
      relativePath: { type: "string", required: true },
      entries: { type: "array", required: true, items: directoryEntry },
      nextOffset: { type: "integer" }
    }, runtime.listProjectFiles),
    definition(defineTool, "get_project_source", "Read one registered source file by repository-relative path and bounded line range.", {
      relativePath: { type: "string", required: true, description: "Allowed path relative to the active repository root; absolute paths and traversal are not accepted." },
      offset: { type: "integer", description: "1-based first line; defaults to 1." },
      limit: { type: "integer", description: "Maximum lines, from 1 to the repository's registered limit." }
    }, {
      domainId: { type: "string", required: true },
      repositoryId: { type: "string", required: true },
      relativePath: { type: "string", required: true },
      sourceVersion: { type: "string" },
      offset: { type: "integer", required: true },
      lines: { type: "array", required: true, items: textLine },
      totalLines: { type: "integer", required: true },
      nextOffset: { type: "integer" }
    }, runtime.getProjectSource),
    definition(defineTool, "get_test_specification", "Return the registered test layers and evidence resources for one change kind.", {
      changeKind: { type: "string", required: true, description: "Exact change-kind id from get_access_paths." }
    }, {
      domainId: { type: "string", required: true },
      id: { type: "string", required: true },
      layers: { type: "array", required: true, items: { type: "string", enum: ["lint", "static", "live", "external"] } },
      resourceIds: { type: "array", required: true, items: { type: "string" } }
    }, runtime.getTestSpecification),
    definition(defineTool, "run_domain_knowledge_lint", "Run the active domain's registered pytest knowledge lint using the fixed command. Test code executes in the workspace and may create its documented cache or test artifacts; arbitrary commands and paths are not accepted.", {}, {
      domainId: { type: "string", required: true },
      repositoryId: { type: "string", required: true },
      command: { type: "string", required: true },
      exitCode: { type: "integer", required: true },
      passed: { type: "boolean", required: true },
      stdout: { type: "string", required: true },
      stderr: { type: "string", required: true },
      outputTruncated: { type: "boolean", required: true },
      errorMessage: { type: "string", required: true }
    }, async (_args, exec) => runDomainKnowledgeLint(ctx, scope, exec), false, 600000),
    definition(defineTool, "submit_audit_findings", "Submit structured findings for the active repository. Each finding must cite a bounded, readable source line range; the tool returns the source excerpt and version as evidence. This does not persist findings or assign a final audit verdict.", {
      findings: {
        type: "array", required: true, description: "Zero or more findings, up to 30. Use an empty array to explicitly report no findings.",
        items: {
          type: "object", additionalProperties: false,
          properties: {
            title: { type: "string", required: true, description: "Concise defect statement." },
            severity: { type: "string", required: true, enum: ["blocker", "high", "medium", "low"] },
            claim: { type: "string", required: true, description: "Why the cited implementation violates a requirement." },
            counterargument: { type: "string", required: true, description: "Strongest design-based reason this may not be a defect." },
            falsificationCondition: { type: "string", required: true, description: "Observable evidence that would disprove the finding." },
            relativePath: { type: "string", required: true, description: "Readable path relative to the active repository." },
            startLine: { type: "integer", required: true, description: "First evidence line, 1-based." },
            endLine: { type: "integer", required: true, description: "Last evidence line; the cited span is limited to 20 lines." }
          }
        }
      }
    }, {
      domainId: { type: "string", required: true },
      repositoryId: { type: "string", required: true },
      findings: {
        type: "array", required: true,
        items: {
          type: "object", additionalProperties: false,
          properties: {
            title: { type: "string", required: true }, severity: { type: "string", required: true },
            claim: { type: "string", required: true }, counterargument: { type: "string", required: true },
            falsificationCondition: { type: "string", required: true },
            evidence: {
              type: "object", additionalProperties: false,
              properties: {
                relativePath: { type: "string", required: true }, startLine: { type: "integer", required: true }, endLine: { type: "integer", required: true }, sourceVersion: { type: "string" },
                lines: { type: "array", required: true, items: textLine }
              }
            }
          }
        }
      }
    }, runtime.submitAuditFindings)
  ]
}

export function registerCoordinatorTools(ctx, config, defineTool, runChildAgent) {
  const tools = buildCoordinatorToolDefinitions(ctx, config, defineTool, runChildAgent)
  ctx.effect(() => {
    const disposers = []
    const cleanup = () => disposers.splice(0).reverse().forEach(dispose => dispose())
    try {
      for (const tool of tools) disposers.push(ctx.tools.register(tool))
      return cleanup
    } catch (error) {
      cleanup()
      throw error
    }
  })
}

function developmentTools(ctx, scope, defineTool, runChildAgent) {
  const output = { result: { ...record, required: true } }
  const wrap = handler => async (args, exec) => ({ result: await handler(args, exec) })
  if (scope.role === "developer") return [
    definition(defineTool, "read_development_file", "Observe full bounded text or absence for one granted source file before writing.", {
      relativePath: { type: "string", required: true, description: "One exact file from the development grant." }
    }, output, wrap(scope.developer.read), false),
    definition(defineTool, "write_project_file", "Atomically replace an observed granted UTF-8 file. Missing targets and stale versions are rejected; changes are not automatically rolled back.", {
      relativePath: { type: "string", required: true },
      expectedVersion: { type: "string", required: true, description: "Existing sourceVersion returned by read_development_file; an absent target is rejected." },
      content: { type: "string", required: true, description: "Complete new content, at most 50000 bytes and the repository file limit." }
    }, output, wrap(scope.developer.write), false)
  ]
  const invocation = scope.developmentInvocation
  if (!invocation) return []
  return [
    definition(defineTool, "run_domain_developer", "Delegate one source implementation to a fresh restricted child; returns actual writes and completion, not acceptance. Retries retain partial changes; at most three attempts.", {
      plan: { type: "string", required: true, description: "Implementation plan within the fixed grant, at most 12000 characters." },
      counterargument: { type: "string", required: true, description: "Strongest design objection and observable falsification condition, at most 12000 characters." },
      acceptanceCriteria: { type: "string", required: true, description: "Behavioral requirements and tests, at most 12000 characters." }
    }, output, wrap((args, exec) => invocation.runDeveloper(args, exec, runChildAgent)), false, 1800000),
    definition(defineTool, "get_development_change", "Return the before/after text and current version for one recorded source change.", {
      relativePath: { type: "string", required: true }
    }, output, wrap(invocation.getChanges), false),
    definition(defineTool, "prepare_project_tests", "Read the registered project test criteria, operation method and fixed argv before executing validation.", {}, output, wrap(invocation.prepareTests), false),
    definition(defineTool, "run_project_tests", "After prepare_project_tests, run the manifest-selected project validation in a full read-only file sandbox; unavailable confinement fails closed. Returns raw bounded evidence bound to readable project inputs; it is not domain acceptance.", {}, output, wrap(invocation.test), false, 660000),
    definition(defineTool, "submit_domain_acceptance", "Record domain acceptance only after completed development and successful tests on current readable inputs. The coordinator still owns final review and subsequent actions.", {
      review: { type: "string", required: true, description: "Explain how inspected changes satisfy the requirement, at most 12000 characters." },
      counterargument: { type: "string", required: true, description: "Strongest remaining objection and falsification condition, at most 12000 characters." },
      unverified: { type: "string", required: true, description: "Explicit unverified boundaries, including inputs outside read scope and external effects; use none only when justified." }
    }, output, wrap(invocation.accept), false)
  ]
}

export function registerDomainTools(agentCtx, scope, defineTool, instructions, globalToolNames = [], runtimeCtx = agentCtx, runChildAgent) {
  let tools = buildDomainToolDefinitions(runtimeCtx, scope, defineTool)
  if (scope.role === "developer" || scope.developmentInvocation) tools = tools.filter(tool => tool.name !== "run_domain_knowledge_lint")
  if (scope.role === "developer") tools = tools.filter(tool => tool.name !== "submit_audit_findings")
  tools.push(...developmentTools(runtimeCtx, scope, defineTool, runChildAgent))
  const allowedNames = new Set(tools.map(tool => tool.name))
  const scopePrompt = [
    instructions,
    "",
    `Active domain: ${scope.domainId}`,
    `Active repository: ${scope.repository.id}`,
    `Knowledge resource ids: ${[...scope.indexes.resources.keys()].join(", ")}`,
    `Operation ids: ${scope.manifest.operationMethods.filter(item => item.repositoryId === scope.repository.id).map(item => item.id).join(", ")}`,
    `Repository read root: ${scope.repository.root}`,
    `Role: ${scope.role === "developer" ? "developer: implement only; no delegation or tests" : "domain: analyze, delegate if granted, inspect changes, test, accept"}`,
    `Development grant: ${scope.developmentInvocation ? JSON.stringify({ requestId: scope.developmentInvocation.requestId, writeFiles: scope.developmentInvocation.writeFiles }) : scope.role === "developer" ? "fixed by the parent task" : "none; remain read-only"}`
  ].join("\n")
  agentCtx.effect(() => {
    const disposers = []
    let removeGlobalTools = () => {}
    let removeOtherTools = () => {}
    let restoreToolMode = () => {}
    let removeInstructions = () => {}
    const cleanup = () => {
      removeInstructions()
      restoreToolMode()
      removeOtherTools()
      removeGlobalTools()
      disposers.splice(0).reverse().forEach(dispose => dispose())
    }
    try {
      for (const tool of tools) disposers.push(agentCtx.tools.register(tool))
      const deniedGlobalTools = globalToolNames.filter(name => name !== "run_code" && !allowedNames.has(name))
      if (deniedGlobalTools.length > 0) removeGlobalTools = agentCtx.tools.restrict({ deny: deniedGlobalTools })
      removeOtherTools = agentCtx.tools.guard(execution => allowedNames.has(execution.name) ? undefined : "tool is outside the active domain invocation scope")
      restoreToolMode = agentCtx.tools.presentAs("native")
      removeInstructions = agentCtx.systemPrompt.section({ name: "domain-agent-invocation", order: 100, text: scopePrompt })
      return cleanup
    } catch (error) {
      cleanup()
      throw error
    }
  })
}
