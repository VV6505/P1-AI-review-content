import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fromM2 } from '../src/features/video-template/model.ts';
import { contentReview } from '../src/features/video-template/content-review.ts';
import { sample } from '../src/features/video-template/sample.ts';

const fixture = () => JSON.parse(fs.readFileSync(new URL('./fixtures/template-handoff.json', import.meta.url), 'utf8'));

test('content review keeps original M2 narration, claims and references while distinguishing estimates and supplied timing', () => {
  const raw = fixture(); raw.script.estimated_duration_s = 42;
  const project = fromM2(raw), original = structuredClone(project);
  const review = contentReview(project);
  assert.equal(review.timeline, 21);
  assert.equal(review.target, 40);
  assert.equal(review.estimated, 42);
  assert.equal(review.timing, 'fixture');
  assert.equal(review.title, raw.script.concept.title);
  let start = 0;
  for (const [index, scene] of review.scenes.entries()) {
    assert.equal(scene.start, start); start = scene.end;
    assert.deepEqual(scene.narration.map(s => ({ segment_id: s.id, text: s.text })), raw.script.scenes[index].narration_segments);
    assert.deepEqual(scene.claims, raw.script.scenes[index].claims.map(c => ({ text: c.text, refs: c.fact_refs, segmentIds: c.segment_ids })));
    assert.deepEqual(scene.refs, project.scenes[index].refs);
  }
  assert.deepEqual(project, original);
});

test('footage ratio uses declared visual kind and scene duration; text-card suggestions do not reject a valid handoff', () => {
  const raw = fixture();
  raw.script.scenes[0].visual_plan = { kind: 'text_card', source_type: 'generated_text', purpose: 'Review test', text: 'Fixture' };
  raw.script.scenes[1].visual_plan = { kind: 'text_card', source_type: 'generated_text', purpose: 'Review test', text: 'Fixture' };
  const review = contentReview(fromM2(raw));
  assert.ok(review.consecutiveTextCards);
  assert.equal(review.footageRatio, 9 / 21);
  assert.equal(contentReview(sample), null, 'a layout fixture must not be presented as an M2 script');
});
