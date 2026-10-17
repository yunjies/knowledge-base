import z from "@deepseek-ai/schemastery"
import { defineTool } from "@deepseek-ai/dsh-tools"
import { registerDomainTools } from "./scripts/registration.js"

export const inject = ["tools", "fs"]
export const Config = z.object({
  domainId: z.string().default("knowledge-base-operations"),
  domainRoot: z.string().default(".agents/domain-agents/instance")
})

export function apply(ctx, config = {}) {
  registerDomainTools(ctx, config, defineTool)
}
