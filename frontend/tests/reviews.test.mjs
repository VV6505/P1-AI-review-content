import test from "node:test";
import assert from "node:assert/strict";
import { activeSegmentAt, formatTime, parseReview, parseSearchResult } from "../src/features/reviews/types.ts";
import { demoReviews, searchDemoReviews } from "../src/features/reviews/demo.ts";

test("all demo reviews satisfy the runtime API contract", () => {
  for (const review of demoReviews) assert.deepEqual(parseReview(review), review);
  assert.equal(parseSearchResult({ reviews: demoReviews, total: 3, source: "demo" }).total, 3);
});
test("search supports accents, casing, multiple words, empty and no matches", () => {
  assert.equal(searchDemoReviews(" GAMMA ")[0].id, "gamma-presentation");
  assert.equal(searchDemoReviews("organize notes")[0].id, "notion-workspace");
  assert.equal(searchDemoReviews("Gámma")[0].id, "gamma-presentation");
  assert.equal(searchDemoReviews("   ").length, 3);
  assert.equal(searchDemoReviews("unknown_product").length, 0);
});
test("transcript follows playback, seeking, gaps and exact cue boundaries", () => {
  const segments = [{ start: 0, end: 4, text: "a" }, { start: 5, end: 8, text: "b" }];
  assert.equal(activeSegmentAt(segments, 0), 0);
  assert.equal(activeSegmentAt(segments, 3.99), 0);
  assert.equal(activeSegmentAt(segments, 4), -1);
  assert.equal(activeSegmentAt(segments, 5), 1);
  assert.equal(activeSegmentAt(segments, 8), -1);
  assert.equal(activeSegmentAt(segments, 1), 0);
  assert.equal(formatTime(65.9), "1:05");
});
test("reject malformed scores, media schemes and overlapping transcripts", () => {
  const review = demoReviews[0];
  for (const score of [-1, 101, NaN, "86"]) assert.throws(() => parseReview({ ...review, score }));
  assert.throws(() => parseReview({ ...review, videoUrl: "javascript:alert(1)" }));
  assert.throws(() => parseReview({ ...review, videoUrl: "//untrusted.example/video" }));
  assert.throws(() => parseReview({ ...review, transcript: [{ start: 0, end: 4, text: "a" }, { start: 3, end: 5, text: "b" }] }));
  assert.throws(() => parseSearchResult({ reviews: demoReviews, total: 1, source: "demo" }));
});
test("pending reviews may have no score or video", () => {
  const review = { ...demoReviews[0], score: null, videoUrl: null, transcript: [], status: "queued" };
  assert.deepEqual(parseReview(review), review);
});
