import { createRuntime, runTool } from "./runtime.js"

const output = {
  schema: {
    type: "object",
    additionalProperties: true,
    properties: {
      ok: { type: "boolean", required: true },
      error: {
        type: "object",
        additionalProperties: false,
        properties: {
          code: { type: "string", required: true },
          message: { type: "string", required: true }
        }
      }
    }
  },
  render: (_args, value) => [{ type: "text", text: JSON.stringify(value, null, 2) }]
}

function definition(defineTool, runtime, name, description, parameters, handler) {
  return defineTool({
    name,
    description,
    parameters,
    output,
    async execute(args, exec) {
      return runTool(runtime[handler].bind(runtime), args, { ...exec, domainId: runtime.domainId })
    },
    isConcurrencySafe: args => args.action === "list" || args.action === "get"
  })
}

export function buildDomainToolDefinitions(runtime, defineTool) {
  return [
    definition(defineTool, runtime, "get_version_control_instructions", "Retrieve the registered version-management instructions in bounded line ranges.", {
      offset: { type: "integer", description: "1-based first line; defaults to 1." },
      limit: { type: "integer", description: "Maximum lines, from 1 to 200; defaults to 120." }
    }, "getVersionControlInstructions"),
    definition(defineTool, runtime, "get_access_paths", "Return structured read-resource and knowledge-store write permissions for this domain instance.", {}, "getAccessPaths"),
    definition(defineTool, runtime, "get_test_specification", "Retrieve the registered test layers and source resources for one change kind.", {
      changeKind: { type: "string", required: true, description: "Exact change-kind id from the structured test specification." }
    }, "getTestSpecification"),
    definition(defineTool, runtime, "get_knowledge_resource", "Read one allowlisted domain resource by id and bounded line range; raw paths are not accepted.", {
      resourceId: { type: "string", required: true, description: "Exact resource id from the domain catalog." },
      offset: { type: "integer", description: "1-based first line; defaults to 1." },
      limit: { type: "integer", description: "Maximum lines, from 1 to 200; defaults to 120." }
    }, "getKnowledgeResource"),
    definition(defineTool, runtime, "advance_review", "Advance the structured review workflow and return the next stage contract.", {
      state: { type: "json", description: "Structured state returned by the preceding call; omit to start the registered workflow." },
      submission: { type: "json", description: "Current-stage outcome, required fields, and evidence references." }
    }, "advanceReview"),
    definition(defineTool, runtime, "manage_domain_knowledge", "Create, read, update, list, or delete structured records in this domain's version-guarded store.", {
      action: { type: "string", required: true, enum: ["list", "get", "create", "update", "delete"] },
      recordId: { type: "string", description: "Stable record id; required except for list." },
      title: { type: "string", description: "Record title for create or update." },
      body: { type: "string", description: "Record body for create or update." },
      tags: { type: "array", items: { type: "string" }, description: "Structured record tags." },
      expectedRevision: { type: "integer", description: "Required current record revision for update and delete." }
    }, "manageKnowledge")
  ]
}

export function registerDomainTools(ctx, config, defineTool, runtimeFactory = createRuntime) {
  const resolvedConfig = {
    domainId: config.domainId ?? "knowledge-base-operations",
    domainRoot: config.domainRoot ?? ".agents/domain-agents/instance"
  }
  const runtime = runtimeFactory(ctx, resolvedConfig)
  runtime.domainId = resolvedConfig.domainId
  const tools = buildDomainToolDefinitions(runtime, defineTool)
  ctx.effect(() => {
    const disposers = tools.map(tool => ctx.tools.register(tool))
    return () => disposers.reverse().forEach(dispose => dispose())
  })
}
