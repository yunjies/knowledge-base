export class DomainToolError extends Error {
  constructor(code, message) {
    super(message)
    this.name = "DomainToolError"
    this.code = code
  }
}

export function beginReview(workflow) {
  if (!workflow || !Array.isArray(workflow.stages)) throw new DomainToolError("INVALID_WORKFLOW", "workflow stages are missing")
  const start = workflow.stages.find(stage => stage.id === workflow.startStage)
  if (!start) throw new DomainToolError("INVALID_WORKFLOW", "workflow start stage is not registered")
  return {
    workflowId: workflow.workflowId,
    currentStage: start.id,
    completedStages: [],
    evidence: []
  }
}

function validateReviewState(workflow, state) {
  if (state?.workflowId !== workflow?.workflowId) throw new DomainToolError("WORKFLOW_MISMATCH", "review state belongs to another workflow")
  if (!Array.isArray(state.completedStages) || !Array.isArray(state.evidence)) throw new DomainToolError("INVALID_REVIEW_STATE", "review history and evidence must be arrays")
  const stages = new Map((workflow?.stages ?? []).map(stage => [stage.id, stage]))
  let expectedStage = workflow.startStage
  for (const completed of state.completedStages) {
    const stage = stages.get(expectedStage)
    if (!stage || completed?.id !== expectedStage || typeof completed.outcome !== "string") throw new DomainToolError("INVALID_REVIEW_STATE", "completed stages do not follow the registered workflow")
    const next = stage.transitions?.[completed.outcome]
    if (!next) throw new DomainToolError("INVALID_REVIEW_STATE", `outcome ${completed.outcome} is not valid for ${stage.id}`)
    const fields = completed.fields && typeof completed.fields === "object" && !Array.isArray(completed.fields) ? completed.fields : {}
    validateStageFields(stage, completed.outcome, fields, "INVALID_REVIEW_STATE")
    expectedStage = next
  }
  if (state.currentStage !== expectedStage) throw new DomainToolError("INVALID_REVIEW_STATE", "current stage does not follow the completed workflow history")
  if (expectedStage === workflow.terminalStage && state.status !== "complete") throw new DomainToolError("INVALID_REVIEW_STATE", "completed workflow status is inconsistent")
  if (expectedStage === "halt" && state.status !== "blocked") throw new DomainToolError("INVALID_REVIEW_STATE", "blocked workflow status is inconsistent")
  if (expectedStage !== workflow.terminalStage && expectedStage !== "halt" && state.status !== undefined && state.status !== "in_progress") throw new DomainToolError("INVALID_REVIEW_STATE", "in-progress workflow status is inconsistent")
  if (expectedStage === workflow.terminalStage || expectedStage === "halt") throw new DomainToolError("REVIEW_FINISHED", "completed or blocked review cannot be advanced")
}

function validateStageFields(stage, outcome, fields, failureCode) {
  if (outcome === "blocked") return
  const required = stage.requiredResultFields ?? []
  const missing = required.filter(key => !(key in fields))
  if (missing.length > 0) throw new DomainToolError(failureCode, `stage ${stage.id} is missing: ${missing.join(", ")}`)
  for (const [key, constraint] of Object.entries(stage.fieldConstraints ?? {})) {
    if (!required.includes(key) || !(key in fields)) throw new DomainToolError("INVALID_WORKFLOW", `field constraint ${key} is not paired with a required result field`)
    const value = fields[key]
    const typeMatches = {
      string: typeof value === "string",
      array: Array.isArray(value),
      object: typeof value === "object" && value !== null && !Array.isArray(value),
      number: typeof value === "number" && Number.isFinite(value),
      integer: Number.isSafeInteger(value),
      boolean: typeof value === "boolean"
    }
    if (!typeMatches[constraint.type]) throw new DomainToolError(failureCode, `stage ${stage.id} field ${key} must have type ${constraint.type}`)
    if (constraint.minLength !== undefined && value.length < constraint.minLength) throw new DomainToolError(failureCode, `stage ${stage.id} field ${key} is too short`)
    if (constraint.minItems !== undefined && value.length < constraint.minItems) throw new DomainToolError(failureCode, `stage ${stage.id} field ${key} has too few items`)
    if (constraint.enum && !constraint.enum.includes(value)) throw new DomainToolError(failureCode, `stage ${stage.id} field ${key} has an unregistered value`)
  }
}

export function advanceReview(workflow, state, submission) {
  validateReviewState(workflow, state)
  const stages = new Map((workflow?.stages ?? []).map(stage => [stage.id, stage]))
  const current = stages.get(state.currentStage)
  if (!current) throw new DomainToolError("INVALID_REVIEW_STATE", "current stage is not registered")
  if (!submission || typeof submission.outcome !== "string") throw new DomainToolError("INVALID_SUBMISSION", "submission outcome is required")
  const nextStageId = current.transitions?.[submission.outcome]
  if (!nextStageId) throw new DomainToolError("INVALID_TRANSITION", `outcome ${submission.outcome} is not allowed from ${current.id}`)
  const fields = submission.fields && typeof submission.fields === "object" && !Array.isArray(submission.fields) ? submission.fields : {}
  validateStageFields(current, submission.outcome, fields, "MISSING_STAGE_OUTPUT")
  const completedStages = [...(state.completedStages ?? []), {
    id: current.id,
    outcome: submission.outcome,
    fields
  }]
  const evidence = [...(state.evidence ?? []), ...(Array.isArray(submission.evidence) ? submission.evidence : [])]
  if (nextStageId === workflow.terminalStage || nextStageId === "halt") {
    return {
      workflowId: workflow.workflowId,
      currentStage: nextStageId,
      completedStages,
      evidence,
      status: nextStageId === "halt" ? "blocked" : "complete",
      delegationOwner: current.delegationOwner ?? null,
      resourceIds: current.resourceIds ?? []
    }
  }
  const next = stages.get(nextStageId)
  if (!next) throw new DomainToolError("INVALID_WORKFLOW", `next stage ${nextStageId} is not registered`)
  return {
    workflowId: workflow.workflowId,
    currentStage: next.id,
    completedStages,
    evidence,
    status: "in_progress",
    delegationOwner: next.delegationOwner ?? null,
    resourceIds: next.resourceIds ?? []
  }
}

function validateKnowledgeRecord(record) {
  if (!record || typeof record !== "object" || Array.isArray(record)) throw new DomainToolError("INVALID_RECORD", "record must be an object")
  if (Object.keys(record).some(key => !["id", "title", "body", "tags", "revision"].includes(key))) throw new DomainToolError("INVALID_RECORD", "record contains an unregistered field")
  if (typeof record.id !== "string" || !/^[a-z0-9][a-z0-9._-]{0,79}$/.test(record.id)) throw new DomainToolError("INVALID_RECORD_ID", "record id must be a stable lowercase identifier")
  if (typeof record.title !== "string" || record.title.trim().length === 0) throw new DomainToolError("INVALID_RECORD", "record title is required")
  if (typeof record.body !== "string" || record.body.trim().length === 0) throw new DomainToolError("INVALID_RECORD", "record body is required")
  if (record.tags !== undefined && (!Array.isArray(record.tags) || record.tags.some(tag => typeof tag !== "string"))) throw new DomainToolError("INVALID_RECORD", "record tags must be an array of strings")
  return {
    id: record.id,
    title: record.title,
    body: record.body,
    tags: record.tags ?? []
  }
}

export function applyKnowledgeOperation(store, request) {
  if (!store || store.schemaVersion !== 1 || !Array.isArray(store.records) || !Number.isSafeInteger(store.revision) || store.revision < 0) throw new DomainToolError("INVALID_STORE", "knowledge store does not match schema version 1")
  const knownIds = new Set()
  for (const record of store.records) {
    validateKnowledgeRecord(record)
    if (!Number.isSafeInteger(record.revision) || record.revision < 1 || knownIds.has(record.id)) throw new DomainToolError("INVALID_STORE", "knowledge record revisions and ids must be unique and valid")
    knownIds.add(record.id)
  }
  if (!request || !["list", "get", "create", "update", "delete"].includes(request.action)) throw new DomainToolError("INVALID_ACTION", "unsupported knowledge operation")
  const records = store.records
  if (request.action === "list") return { store, result: { records } }
  if (typeof request.recordId !== "string" || request.recordId.length === 0) {
    if (request.action !== "create") throw new DomainToolError("RECORD_ID_REQUIRED", "recordId is required")
  }
  const index = records.findIndex(record => record.id === request.recordId)
  if (request.action === "get") {
    if (index < 0) throw new DomainToolError("RECORD_NOT_FOUND", "knowledge record does not exist")
    return { store, result: { record: records[index] } }
  }
  if (request.action === "create") {
    const record = validateKnowledgeRecord(request.record)
    if (records.some(existing => existing.id === record.id)) throw new DomainToolError("RECORD_EXISTS", "knowledge record already exists")
    const next = { ...record, revision: 1 }
    const updatedStore = { ...store, revision: (store.revision ?? 0) + 1, records: [...records, next] }
    return { store: updatedStore, result: { operation: "created", record: next, storeRevision: updatedStore.revision } }
  }
  if (index < 0) throw new DomainToolError("RECORD_NOT_FOUND", "knowledge record does not exist")
  const current = records[index]
  if (!Number.isSafeInteger(request.expectedRevision) || current.revision !== request.expectedRevision) throw new DomainToolError("STALE_RECORD_VERSION", "expectedRevision does not match the current record revision")
  if (request.action === "delete") {
    const updatedStore = { ...store, revision: (store.revision ?? 0) + 1, records: records.filter(record => record.id !== request.recordId) }
    return { store: updatedStore, result: { operation: "deleted", recordId: request.recordId, storeRevision: updatedStore.revision } }
  }
  const replacement = validateKnowledgeRecord({ ...request.record, id: request.recordId })
  const next = { ...replacement, revision: current.revision + 1 }
  const updatedRecords = [...records]
  updatedRecords[index] = next
  const updatedStore = { ...store, revision: (store.revision ?? 0) + 1, records: updatedRecords }
  return { store: updatedStore, result: { operation: "updated", record: next, storeRevision: updatedStore.revision } }
}

export function validateRelativePath(path) {
  if (typeof path !== "string" || path.length === 0 || path.startsWith("/") || path.includes("\\")) throw new DomainToolError("PATH_REJECTED", "path must be a non-empty workspace-relative POSIX path")
  const segments = path.split("/")
  if (segments.some(segment => segment === ".." || segment === "." || segment.length === 0)) throw new DomainToolError("PATH_REJECTED", "path traversal and empty path segments are forbidden")
  return path
}
