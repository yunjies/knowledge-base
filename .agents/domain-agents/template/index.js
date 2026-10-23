import { randomUUID } from "node:crypto"
import z from "@deepseek-ai/schemastery"
import { brandString } from "@deepseek-ai/dsh-brand"
import { createUserMessage } from "@deepseek-ai/dsh-llm"
import { childSessionMeta, finalAssistantOutput, resolveChildAgentOptions, resolveChildDepth } from "@deepseek-ai/dsh-subagent"
import { defineTool } from "@deepseek-ai/dsh-tools"
import { createChildRunOwner, createDomainChildRunner } from "./scripts/child-runner.js"
import { loadAgentInstructions } from "./scripts/domain-runtime.js"
import { registerCoordinatorTools, registerDomainTools } from "./scripts/registration.js"

export const inject = ["tools", "fs", "agents", "subprocess", "systemPrompt"]
export const Config = z.object({
  domainKnowledgeRoot: z.string().default("assets/domain-knowledge")
})

function stopReasonFromEvents(events) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    if (event.type === "turn/end" && typeof event.data?.reason?.kind === "string") return event.data.reason.kind
  }
  return "error"
}

function textOutput(blocks = []) {
  return blocks.filter(block => block.type === "text").map(block => block.text).join("")
}

export function apply(ctx, config = {}) {
  const resolved = {
    domainKnowledgeRoot: config.domainKnowledgeRoot ?? "assets/domain-knowledge",
    workerPresetId: "minimal"
  }
  const childOwner = createChildRunOwner(ctx)
  const runChildAgent = createDomainChildRunner({
    createSessionId: () => brandString(randomUUID()),
    childSessionMeta,
    resolveChildAgentOptions,
    resolveChildDepth,
    createUserMessage,
    finalAssistantOutput,
    stopReason: stopReasonFromEvents,
    textOutput
  }, resolved, loadAgentInstructions, (agentCtx, scope, instructions, globalToolNames) => registerDomainTools(agentCtx, scope, defineTool, instructions, globalToolNames, ctx), childOwner)
  registerCoordinatorTools(ctx, resolved, defineTool, runChildAgent)
  ctx.effect(() => ctx.systemPrompt.section({
    name: "domain-agent-coordinator",
    order: 100,
    text: "For domain work, call list_domain_knowledge to select a registered domain and repository, then call run_domain_agent with a self-contained task. The child receives a fixed per-call domain and repository scope. It resolves operation methods from structured methodId mappings, then reads the mapped resources before source. Do not pass filesystem paths or ask the child to change domains. Audit and final review remain with the coordinator."
  }))
}
