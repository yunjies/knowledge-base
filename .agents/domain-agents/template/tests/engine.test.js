import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"
import { advanceReview, applyKnowledgeOperation, beginReview, DomainToolError, validateRelativePath } from "../scripts/engine.js"

const workflow = JSON.parse(await readFile(new URL("../data/review-workflow.json", import.meta.url), "utf8"))

function store() {
  return { schemaVersion: 1, domainId: "knowledge-base-operations", revision: 0, records: [] }
}

test("review workflow starts at its registered start stage", () => {
  const state = beginReview(workflow)
  assert.equal(state.currentStage, workflow.startStage)
  assert.equal(state.workflowId, workflow.workflowId)
})

test("review workflow rejects an undeclared transition", () => {
  const state = beginReview(workflow)
  assert.throws(() => advanceReview(workflow, state, { outcome: "complete", fields: {} }), error => error instanceof DomainToolError && error.code === "INVALID_TRANSITION")
})

test("review workflow rejects a forged stage skip", () => {
  const state = { ...beginReview(workflow), currentStage: "convergence" }
  assert.throws(() => advanceReview(workflow, state, { outcome: "converged", fields: { convergenceResult: "pass" } }), error => error instanceof DomainToolError && error.code === "INVALID_REVIEW_STATE")
})

test("review workflow rejects missing required stage output", () => {
  let state = beginReview(workflow)
  state = advanceReview(workflow, state, { outcome: "ready", fields: { baselineRef: "baseline-1" } })
  assert.equal(state.currentStage, "dispatch")
  assert.throws(() => advanceReview(workflow, state, { outcome: "complete", fields: { perspectiveSet: [] } }), error => error instanceof DomainToolError && error.code === "MISSING_STAGE_OUTPUT")
})

test("review workflow requires the leader-owned dispatch outputs", () => {
  const dispatch = workflow.stages.find(stage => stage.id === "dispatch")
  assert.equal(dispatch.delegationOwner, "session-leader")
  assert.deepEqual(dispatch.requiredResultFields, ["perspectiveSet", "reviewerResults"])
})

test("review workflow rejects an empty reviewer result set", () => {
  let state = beginReview(workflow)
  state = advanceReview(workflow, state, { outcome: "ready", fields: { baselineRef: "baseline-1" } })
  assert.throws(() => advanceReview(workflow, state, {
    outcome: "complete",
    fields: { perspectiveSet: ["AP-01"], reviewerResults: [] }
  }), error => error instanceof DomainToolError && error.code === "MISSING_STAGE_OUTPUT")
})

test("knowledge store creates and retrieves a structured record", () => {
  const created = applyKnowledgeOperation(store(), {
    action: "create",
    record: { id: "policy-1", title: "Policy", body: "Use a registered tool", tags: ["access"] }
  })
  assert.equal(created.result.record.revision, 1)
  const retrieved = applyKnowledgeOperation(created.store, { action: "get", recordId: "policy-1" })
  assert.equal(retrieved.result.record.body, "Use a registered tool")
})

test("knowledge store rejects a stale update and preserves the record", () => {
  const created = applyKnowledgeOperation(store(), {
    action: "create",
    record: { id: "policy-1", title: "Policy", body: "Original" }
  })
  assert.throws(() => applyKnowledgeOperation(created.store, {
    action: "update",
    recordId: "policy-1",
    expectedRevision: 0,
    record: { title: "Policy", body: "Changed" }
  }), error => error instanceof DomainToolError && error.code === "STALE_RECORD_VERSION")
  assert.equal(created.store.records[0].body, "Original")
})

test("knowledge store requires a version for deletion", () => {
  const created = applyKnowledgeOperation(store(), {
    action: "create",
    record: { id: "policy-1", title: "Policy", body: "Original" }
  })
  assert.throws(() => applyKnowledgeOperation(created.store, { action: "delete", recordId: "policy-1" }), error => error instanceof DomainToolError && error.code === "STALE_RECORD_VERSION")
})

test("knowledge store rejects duplicate record identities", () => {
  const duplicateStore = {
    ...store(),
    records: [
      { id: "same-id", title: "One", body: "First", tags: [], revision: 1 },
      { id: "same-id", title: "Two", body: "Second", tags: [], revision: 1 }
    ]
  }
  assert.throws(() => applyKnowledgeOperation(duplicateStore, { action: "list" }), error => error instanceof DomainToolError && error.code === "INVALID_STORE")
})

test("path validation rejects absolute and traversal paths", () => {
  assert.throws(() => validateRelativePath("/etc/passwd"), error => error instanceof DomainToolError && error.code === "PATH_REJECTED")
  assert.throws(() => validateRelativePath("data/../secret.json"), error => error instanceof DomainToolError && error.code === "PATH_REJECTED")
  assert.throws(() => validateRelativePath("data\\secret.json"), error => error instanceof DomainToolError && error.code === "PATH_REJECTED")
})
