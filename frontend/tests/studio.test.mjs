import test from 'node:test';
import assert from 'node:assert/strict';
import { emptyDraft, initialStudio, parseStudio, estimateTokens, productIsConfirmed, approveRequirements, requirementsAreConfirmed, prepareAutomaticDraft } from '../src/features/studio/model.ts';

test('existing history migrates into individual projects without losing settings or balances', () => {
  const state = structuredClone(initialStudio);
  const draft = { ...emptyDraft, sourceUrl: 'https://gamma.app', preparedUrl: 'https://gamma.app', prompt: 'Saved prompt', opening: 'Saved opening', ratio: '4:5' };
  delete draft.notes;
  delete draft.projectId;
  delete draft.model;
  delete draft.references;
  delete draft.productReview;
  state.draft = draft;
  state.requests = [{ ...draft, id: 'saved-history', createdAt: '2026-10-12T03:00:00.000Z', estimatedTokens: 225, status: 'completed' }];
  const restored = parseStudio(JSON.stringify(state));
  assert.equal(restored.requests[0].projectId, 'saved-history');
  assert.equal(restored.requests[0].notes, '');
  assert.equal(restored.requests[0].model, 'veo');
  assert.deepEqual(restored.requests[0].references, []);
  assert.equal(restored.requests[0].productReview, null);
  assert.equal(restored.requests[0].prompt, 'Saved prompt');
  assert.equal(restored.requests[0].ratio, '4:5');
  assert.deepEqual(restored.users, state.users);
  assert.deepEqual(restored.plans, state.plans);
});

test('product confirmation survives saving and is tied to the exact product link', () => {
  const state = structuredClone(initialStudio);
  state.draft.sourceUrl = 'https://shop.example.com/item/one';
  state.draft.productReview = { sourceUrl: state.draft.sourceUrl, name: 'Product one', description: 'Reviewed description', features: 'Reviewed features', pricing: '', variant: '', sources: state.draft.sourceUrl, confirmedAt: '2026-10-13T00:00:00.000Z' };
  const restored = parseStudio(JSON.stringify(state));
  assert.ok(productIsConfirmed(restored.draft));
  assert.equal(restored.draft.productReview.description, 'Reviewed description');
  assert.equal(productIsConfirmed({ ...restored.draft, sourceUrl: 'https://shop.example.com/item/two' }), false);
  assert.equal(productIsConfirmed({ ...restored.draft, productReview: { ...restored.draft.productReview, confirmedAt: null } }), false);
  assert.equal(productIsConfirmed({ ...restored.draft, productReview: { ...restored.draft.productReview, sources: 'javascript:alert(1)' } }), false);
});

test('project notes and video settings survive saving while invalid source snapshots are rejected', () => {
  const state = structuredClone(initialStudio);
  state.requests = [{ ...emptyDraft, sourceUrl: 'https://gamma.app', preparedUrl: 'https://gamma.app', prompt: 'Prompt', opening: 'Opening', projectId: 'project-1', notes: 'For students', ratio: '21:9', references: [{ id: 'reference-1', name: 'product.pdf', type: 'application/pdf', size: 1024 }], id: 'generation-1', createdAt: '2026-10-12T03:00:00.000Z', estimatedTokens: 225, status: 'completed' }];
  assert.deepEqual(parseStudio(JSON.stringify(state)).requests, state.requests);
  state.requests[0].preparedUrl = 'https://different.example.com';
  assert.throws(() => parseStudio(JSON.stringify(state)));
});

test('manually entered video counts survive reload and update estimates; invalid quantities are rejected', () => {
  const state = structuredClone(initialStudio);
  state.draft.count = 7;
  assert.equal(parseStudio(JSON.stringify(state)).draft.count, 7);
  assert.equal(estimateTokens(state.draft), estimateTokens(emptyDraft) * 7);
  for (const count of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    state.draft.count = count;
    assert.throws(() => parseStudio(JSON.stringify(state)));
  }
});

function confirmedDraft() {
  return { ...structuredClone(emptyDraft), sourceUrl: 'https://aisoeasy.com', notes: 'Dành cho nhân viên văn phòng, giọng thân thiện.',
    productReview: { sourceUrl: 'https://aisoeasy.com', name: 'AISoEasy', description: 'Thông tin đã rà.', features: 'Tính năng có nguồn', pricing: '', variant: '', sources: 'https://aisoeasy.com', confirmedAt: '2026-11-02T03:00:00.000Z' } };
}

test('requirements approval is bound to the reviewed input and survives storage without changing product confirmation', () => {
  const draft = confirmedDraft();
  const approved = approveRequirements(draft, '2026-11-02T04:00:00.000Z');
  assert.equal(draft.requirementsReview, null);
  assert.ok(requirementsAreConfirmed(prepareAutomaticDraft(approved)));
  const state = structuredClone(initialStudio); state.draft = approved;
  const restored = parseStudio(JSON.stringify(state));
  assert.ok(requirementsAreConfirmed(restored.draft));
  assert.deepEqual(restored.draft.productReview, draft.productReview);
  for (const patch of [
    { notes: 'Đổi đối tượng' }, { sourceUrl: 'https://aisoeasy.com/other' }, { ratio: '16:9' }, { duration: 45 },
    { outputLanguage: 'en' }, { count: 2 }, { resolution: '720p' }, { style: 'animation' }, { model: 'kling' },
    { references: [{ id: 'new', name: 'source.txt', type: 'text/plain', size: 12 }] },
    { productReview: { ...draft.productReview, features: 'Nội dung mới', confirmedAt: '2026-11-02T05:00:00.000Z' } },
  ]) assert.equal(requirementsAreConfirmed({ ...approved, ...patch }), false, JSON.stringify(patch));
});

test('legacy notes/history remain intact and do not gain an approval implicitly', () => {
  const state = structuredClone(initialStudio);
  state.draft = confirmedDraft(); delete state.draft.requirementsReview;
  const restored = parseStudio(JSON.stringify(state));
  assert.equal(restored.draft.notes, state.draft.notes);
  assert.equal(restored.draft.requirementsReview, null);
  assert.equal(requirementsAreConfirmed(restored.draft), false);
  assert.throws(() => approveRequirements({ ...restored.draft, productReview: null }, '2026-11-02T04:00:00.000Z'));
  assert.throws(() => approveRequirements(restored.draft, 'invalid'));
});

test('user preferences remain separate from confirmed product facts in the local handoff', () => {
  const draft = confirmedDraft(); draft.notes = 'Nhanh nhất thị trường, tăng năng suất 99%';
  const prepared = prepareAutomaticDraft(draft);
  assert.equal(prepared.notes, draft.notes);
  assert.equal(prepared.productReview.features, draft.productReview.features);
  assert.ok(prepared.prompt.includes('nguyên văn người dùng, không phải thông tin sản phẩm đã xác minh'));
  assert.ok(prepared.prompt.includes('cần đối chiếu với PKB'));
});
