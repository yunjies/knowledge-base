export function createChildRunOwner(ctx) {
  const active = new Map()
  let disposed = false
  ctx.effect(() => async () => {
    disposed = true
    const handles = [...active.values()]
    active.clear()
    await Promise.all(handles.map(handle => handle.dispose()))
  })
  return {
    track(sessionId, handle) {
      if (disposed) {
        try {
          void Promise.resolve(handle.dispose()).catch(() => {})
        } catch {}
        return () => {}
      }
      active.set(sessionId, handle)
      let released = false
      return () => {
        if (released) return
        released = true
        if (active.get(sessionId) === handle) active.delete(sessionId)
      }
    }
  }
}

export function createDomainChildRunner(dependencies, config, loadInstructions, registerDomainTools, owner) {
  return async ({ args, exec, scope }) => {
    const parent = exec.agent
    if (!parent?.ctx?.agents) throw new Error("calling agent cannot create a scoped domain worker")
    const childDepth = dependencies.resolveChildDepth(parent, scope.role === "developer" || scope.developmentInvocation ? 2 : 1)
    const childMeta = { ...dependencies.childSessionMeta(parent, childDepth, false), agentPreset: config.workerPresetId }
    const childSessionId = dependencies.createSessionId()
    const instructions = await loadInstructions()
    const globalToolNames = parent.ctx.tools.schemas().map(tool => tool.name)
    let handle
    let disposePromise
    let disposeHandle
    let releaseOwner
    let abortChild
    try {
      handle = await parent.ctx.agents.create({
        sessionId: childSessionId,
        parentAgent: parent,
        meta: childMeta,
        agentOptions: dependencies.resolveChildAgentOptions(parent, undefined, childDepth),
        signal: exec.signal,
        setup: async agentCtx => registerDomainTools(agentCtx, scope, instructions, globalToolNames)
      })
      disposeHandle = () => {
        if (!disposePromise) disposePromise = Promise.resolve().then(() => handle.dispose())
        return disposePromise
      }
      releaseOwner = owner.track(childSessionId, { dispose: disposeHandle })
      const child = handle.agent
      abortChild = () => child.cancel({ kind: "parent" })
      if (exec.signal.aborted) abortChild()
      else exec.signal.addEventListener("abort", abortChild, { once: true })
      child.followup(dependencies.createUserMessage({
        content: [{ type: "text", text: `Active domain: ${scope.domainId}\nActive repository: ${scope.repository.id}\nKnowledge resource ids: ${[...scope.indexes.resources.keys()].join(", ")}\nOperation ids: ${scope.manifest.operationMethods.filter(item => item.repositoryId === scope.repository.id).map(item => item.id).join(", ")}\nRepository root: ${scope.repository.root}\n\nDomain task:\n${args.task}` }],
        source: { kind: "user" }
      }))
      await child.whenIdle()
      const events = child.session.snapshotEvents()
      const stopReason = dependencies.stopReason(events)
      return {
        domainId: scope.domainId,
        repositoryId: scope.repository.id,
        childSessionId,
        completed: stopReason === "completed",
        stopReason,
        output: dependencies.textOutput(dependencies.finalAssistantOutput(events))
      }
    } finally {
      if (abortChild) exec.signal.removeEventListener("abort", abortChild)
      releaseOwner?.()
      if (disposeHandle) await disposeHandle()
    }
  }
}
