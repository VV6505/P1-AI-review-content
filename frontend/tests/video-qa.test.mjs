import test from "node:test";
import assert from "node:assert/strict";
import { registerHooks } from "node:module";

// The app uses bundler resolution. Resolve this extensionless fixture import
// for Node's TypeScript runner without changing the application's module mode.
const modelUrl = new URL("../src/features/video-qa/model.ts", import.meta.url).href;
registerHooks({ resolve(specifier, context, nextResolve) {
  return nextResolve(context.parentURL === modelUrl && specifier === "../reviews/demo" ? "../reviews/demo.ts" : specifier, context);
} });
const { checks, decideVideo, flagVideo, initialVideos, parseVideos, requestVideo, changeRender, hookCategory, distributionCaption } = await import(modelUrl);
const { initialProjects } = await import("../src/features/content-factory/model.ts");
const allChecked = Object.fromEntries(checks.map(({ key }) => [key, true]));
const pending = () => structuredClone(initialVideos.assets.find(a => a.status === "pending_review"));
const approved = () => decideVideo(pending(), "approved", allChecked, "", true);

test("generated jobs need approved PKB and finished 9:16 render; reload preserves source version and trusted media", () => {
  assert.throws(() => requestVideo(initialProjects[1], "Demo", "Hook"));
  const queued = requestVideo(initialProjects[0], "Use case", "Hook");
  assert.throws(() => decideVideo(queued, "approved", allChecked, "", true));
  assert.throws(() => changeRender(queued, "completed"));
  const failed = changeRender(changeRender(queued, "running"), "failed");
  const ready = changeRender(changeRender(failed, "running"), "completed");
  assert.equal(ready.review.id, queued.review.id);
  assert.throws(() => decideVideo({ ...ready, duration: 61 }, "approved", allChecked, "", true));
  assert.throws(() => decideVideo({ ...ready, width: 1920 }, "approved", allChecked, "", true));
  const locked = decideVideo(ready, "approved", allChecked, "", true);
  assert.throws(() => changeRender(locked, "running"));
  const state = structuredClone(initialVideos); state.assets.push(locked);
  state.assets.at(-1).review.videoUrl = "https://untrusted.example/video.mp4";
  const restored = parseVideos(JSON.stringify(state)).assets.at(-1);
  assert.equal(restored.review.videoUrl, "/media/leader-demo.mp4"); assert.equal(restored.knowledgeVersion, 1);
});

test("initial video approval requires approved PKB and QA; pending rejection requires a reason", () => {
  assert.throws(() => decideVideo(pending(), "approved", allChecked, "", false));
  assert.throws(() => decideVideo(pending(), "approved", { ...allChecked, facts: false }, "", true));
  assert.throws(() => decideVideo(pending(), "rejected", allChecked, "", false));
  assert.throws(() => decideVideo(pending(), "archived", allChecked, "reason", true));
  const rejected = decideVideo(pending(), "rejected", allChecked, "Policy violation", false);
  assert.equal(rejected.status, "rejected"); assert.equal(rejected.firstApprovedAt, null);
  assert.ok(rejected.reviewedAt && rejected.reviewedBy);
});

test("reported approved videos can retain approval or archive, preserving the original approval and content", () => {
  const original = approved();
  assert.ok(original.firstApprovedAt && original.reviewedAt && original.reviewedBy);
  const flagged = flagVideo(original, "Wrong claim");
  assert.equal(flagged.status, "approved");
  assert.throws(() => decideVideo(flagged, "rejected", allChecked, "Wrong claim", true), /chỉ có thể lưu trữ/);
  assert.throws(() => decideVideo(flagged, "archived", allChecked, "", true));
  const retained = decideVideo(flagged, "approved", allChecked, "", true);
  const archived = decideVideo(flagged, "archived", { ...allChecked, media: false }, "Wrong claim", true);
  for (const result of [retained, archived]) {
    for (const field of ["firstApprovedAt", "reviewedAt", "reviewedBy", "caption", "review", "checklist", "knowledgeVersion"]) assert.deepEqual(result[field], original[field]);
    assert.equal(result.flaggedAt, null);
  }
  assert.equal(retained.status, "approved"); assert.equal(archived.status, "archived");
  assert.equal(archived.reason, "Wrong claim");
  assert.throws(() => flagVideo(archived, "Again"));
  assert.throws(() => decideVideo(archived, "approved", allChecked, "", true));
  assert.throws(() => decideVideo(archived, "rejected", allChecked, "Again", true));
});

test("video saves round-trip locked approvals and migrate legacy fixtures without deleting the library", () => {
  const state = structuredClone(initialVideos);
  state.assets[0] = decideVideo(flagVideo(approved(), "Wrong claim"), "archived", allChecked, "Wrong claim", true);
  assert.deepEqual(parseVideos(JSON.stringify(state)), state);
  const legacy = structuredClone(state); legacy.schema = 1;
  legacy.assets[0].status = "in_review";
  for (const asset of legacy.assets) for (const field of ["firstApprovedAt", "reviewedAt", "reviewedBy"]) delete asset[field];
  const migrated = parseVideos(JSON.stringify(legacy));
  assert.equal(migrated.schema, 2); assert.equal(migrated.assets.length, state.assets.length);
  assert.equal(migrated.assets[0].status, "pending_review");
  assert.ok(migrated.assets.find(a => a.status === "approved").firstApprovedAt);
  const invalid = structuredClone(state); invalid.assets[0].status = "rejected";
  assert.throws(() => parseVideos(JSON.stringify(invalid)), /lifecycle/);
});

test("hook category persists independently of hook wording; distribution supplies hashtags without changing approved content", () => {
  const asset = requestVideo(initialProjects[0], "Problem", "A custom opening sentence", "Pain");
  const restored = parseVideos(JSON.stringify({ ...initialVideos, assets: [...initialVideos.assets, asset] })).assets.at(-1);
  assert.equal(hookCategory(restored), "Pain");
  assert.equal(restored.hook, "A custom opening sentence");
  const locked = structuredClone(initialVideos.assets.find(item => item.status === "approved"));
  const before = structuredClone(locked);
  assert.match(distributionCaption(locked), /#ProductReview/);
  assert.deepEqual(locked, before);
  assert.equal(distributionCaption({ ...locked, caption: "Caption #ExistingTag" }), "Caption #ExistingTag");
});
