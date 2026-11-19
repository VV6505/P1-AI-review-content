import test from "node:test";
import assert from "node:assert/strict";
import { approvedKnowledge, changeJob, createMockContent, createMockProject, initialWorkspace, latestKnowledge, newDraft, normalizeWebsiteUrl, parseWorkspace, saveKnowledge, transitionKnowledge, enrichKnowledge, startRecrawl, knowledgeErrors, updatePricingMeta } from "../src/features/content-factory/model.ts";

function draft() { return changeJob(changeJob(createMockProject("https://demo.example/tool", "https://demo.example/?ref=test", "test"), "running"), "completed"); }
function approve(project) { return transitionKnowledge(transitionKnowledge(project, "in_review", "merchant"), "approved", "merchant"); }

test("merchant conflicts, evidence limits and explicit price confirmation block approval; recrawl preserves approved snapshots", () => {
  const project = draft();
  const version = enrichKnowledge(latestKnowledge(project), { name: "Demo", tagline: "Demo", pricing: "$35 / month", features: ["Merchant feature"], forbiddenClaims: "No guarantees", logo: "", color: "#333333", uploads: [] });
  assert.equal(version.data.facts.features.origin, "merchant");
  assert.ok(knowledgeErrors(version).some(message => message.includes("xung đột")));
  assert.ok(knowledgeErrors(version).some(message => message.includes("giá Merchant")));
  version.data.conflicts.forEach(conflict => { conflict.resolved = "merchant"; });
  version.data.pricing.plans[0].listPrice = 35; version.data.pricing.plans[0].priceConfirmed = true;
  assert.deepEqual(knowledgeErrors(version), []);
  version.data.facts.description.evidence = "x".repeat(201);
  assert.ok(knowledgeErrors(version).some(message => message.includes("200")));
  const approved = approve(project), original = structuredClone(approvedKnowledge(approved));
  const recrawled = changeJob(changeJob(startRecrawl(approved), "running"), "completed");
  assert.deepEqual(approvedKnowledge(recrawled), original); assert.equal(latestKnowledge(recrawled).version, 2);
  assert.throws(() => startRecrawl(recrawled));
});
test("canonical URL collapses scheme/www/slash/fragment but retains product paths and query", () => {
  assert.equal(normalizeWebsiteUrl(" HTTP://www.Gamma.app/#hero "), "https://gamma.app");
  assert.notEqual(normalizeWebsiteUrl("https://github.com/features/copilot"), normalizeWebsiteUrl("https://github.com/features/another-product"));
  assert.notEqual(normalizeWebsiteUrl("https://demo.example/tool?a=1"), normalizeWebsiteUrl("https://demo.example/tool?a=2"));
  assert.throws(() => normalizeWebsiteUrl("javascript:alert(1)"));
  assert.throws(() => normalizeWebsiteUrl("https://user:password@demo.example"));
});
test("job state and retry stay explicit; failure doesn't create a PKB", () => {
  const queued = createMockProject("https://demo.example/tool", "https://demo.example", "job");
  assert.equal(queued.job.status, "queued"); assert.equal(queued.knowledge.length, 0);
  assert.throws(() => changeJob(queued, "completed"));
  const failed = changeJob(changeJob(queued, "running"), "failed");
  assert.equal(failed.knowledge.length, 0); assert.ok(failed.job.error);
  const retry = changeJob(failed, "running"); assert.equal(retry.job.id, queued.job.id); assert.equal(retry.job.attempts, 2);
  const completed = changeJob(retry, "completed"); assert.equal(latestKnowledge(completed).status, "draft");
});
test("approved snapshots remain immutable after editing and approving a newer version", () => {
  const v1 = approve(draft()); const snapshot = structuredClone(v1.knowledge[0]);
  assert.throws(() => saveKnowledge(v1, snapshot.data, snapshot.updatedAt));
  let v2 = newDraft(v1, "merchant");
  const edited = structuredClone(latestKnowledge(v2).data);
  edited.facts.description = { value: "A revised English description.", origin: "merchant", sourceId: null, evidence: "" };
  v2 = saveKnowledge(v2, edited, latestKnowledge(v2).updatedAt);
  assert.equal(approvedKnowledge(v2).version, 1);
  v2 = approve(v2);
  assert.equal(approvedKnowledge(v2).version, 2);
  assert.deepEqual(v2.knowledge[0], snapshot);
});
test("merchant-only approval and review state are enforced in the mock domain", () => {
  const p = draft(); assert.throws(() => transitionKnowledge(p, "approved", "merchant"));
  assert.throws(() => transitionKnowledge(p, "in_review", "admin"));
  const review = transitionKnowledge(p, "in_review", "merchant");
  assert.throws(() => transitionKnowledge(review, "approved", "admin"));
  assert.throws(() => transitionKnowledge(review, "rejected", "merchant", "Missing evidence"), /Chỉ admin/);
  assert.throws(() => transitionKnowledge(review, "rejected", "admin"));
  const rejected = transitionKnowledge(review, "rejected", "admin", "Missing evidence");
  assert.equal(latestKnowledge(rejected).status, "rejected"); assert.equal(rejected.currentKnowledgeVersion, null);
  assert.equal(latestKnowledge(newDraft(rejected, "merchant")).version, 2);
});
test("missing required facts or invalid pricing block submission; stale saves fail", () => {
  const p = draft(); const data = structuredClone(latestKnowledge(p).data);
  data.facts.description.value = "";
  const saved = saveKnowledge(p, data, latestKnowledge(p).updatedAt);
  assert.throws(() => transitionKnowledge(saved, "in_review", "merchant"));
  assert.throws(() => saveKnowledge(p, data, "outdated revision"));
  data.facts.description.value = "Example"; data.pricing.plans[0].listPrice = -1;
  assert.throws(() => transitionKnowledge(saveKnowledge(p, data, latestKnowledge(p).updatedAt), "in_review", "merchant"));
});
test("saved workspace round-trips jobs, drafts, approvals and English content snapshots", () => {
  const project = approve(draft()); project.content = createMockContent(project, "Content creators", "YouTube Shorts");
  const saved = { ...structuredClone(initialWorkspace), projects: [newDraft(project, "merchant")], selectedId: project.id };
  const restored = parseWorkspace(JSON.stringify(saved));
  assert.deepEqual(restored, saved);
  assert.equal(restored.projects[0].content.knowledgeVersion, 1);
  assert.match(restored.projects[0].content.script, /Language: English/);
  assert.throws(() => parseWorkspace('{"schema":1}'));
  saved.projects[0].currentKnowledgeVersion = 99; assert.throws(() => parseWorkspace(JSON.stringify(saved)));
});

test("currency edits update plan units without converting numbers or changing the saved PKB", () => {
  const original = structuredClone(initialWorkspace.projects[0].knowledge[0].data);
  const edited = updatePricingMeta(original, "currency", "VND");
  assert.equal(edited.pricing.currency, "VND");
  assert.equal(edited.pricing.plans[0].currency, "VND");
  assert.equal(edited.pricing.plans[0].listPrice, original.pricing.plans[0].listPrice);
  assert.equal(edited.pricing.plans[0].origin, "merchant");
  assert.equal(original.pricing.currency, "USD");
});
