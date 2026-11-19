import test from 'node:test';
import assert from 'node:assert/strict';
import { demoAccounts, ACCOUNTS_KEY, updateDemoAccounts } from '../src/features/auth/model.ts';
import { initialStudio, STUDIO_KEY, estimateTokens } from '../src/features/studio/model.ts';
import { persistStudio, restoreStudio, WELCOME_TOKENS } from '../src/features/studio/storage.ts';

async function fixture() {
  const seeds = await demoAccounts();
  const creator = { ...seeds[0], id: 'registered', name: 'New Creator', email: 'new@example.com' };
  const data = new Map([[ACCOUNTS_KEY, JSON.stringify([...seeds, creator])]]);
  const storage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) };
  return { storage, creator, admin: seeds[1], seeds };
}

test('registered creators appear in Admin and have enough welcome tokens for the default video', async () => {
  const { storage, creator, admin } = await fixture();
  const state = restoreStudio(storage, creator);
  assert.equal(state.users[0].tokens, WELCOME_TOKENS);
  assert.ok(state.users[0].tokens >= estimateTokens(state.draft));
  assert.equal(restoreStudio(storage, admin).users.find(user => user.id === creator.id).email, creator.email);
});

test('Admin profile, balance and status edits reach Creator and survive subsequent saves', async () => {
  const { storage, creator, admin, seeds } = await fixture();
  const state = restoreStudio(storage, admin);
  const user = state.users.find(user => user.id === creator.id);
  Object.assign(user, { name: 'Edited', email: 'edited@example.com', tokens: 3000, active: false });
  persistStudio(storage, admin, { ...state, revision: state.revision + 1 });
  const own = restoreStudio(storage, creator);
  assert.equal(own.users[0].name, 'Edited');
  assert.equal(own.users[0].tokens, 3000);
  assert.equal(own.users[0].active, false);
  persistStudio(storage, creator, { ...own, revision: own.revision + 1 });
  assert.equal(restoreStudio(storage, admin).users.find(user => user.id === creator.id).name, 'Edited');
  const accounts = updateDemoAccounts(JSON.parse(storage.getItem(ACCOUNTS_KEY)), seeds);
  assert.equal(accounts.find(account => account.id === creator.id).email, 'edited@example.com');
});

test('legacy balances and history migrate once with a single welcome top-up', async () => {
  const { storage, creator, admin } = await fixture();
  const legacy = structuredClone(initialStudio);
  legacy.users[0].tokens = 125;
  legacy.draft.notes = 'Saved private notes';
  storage.setItem(`${STUDIO_KEY}.${creator.id}`, JSON.stringify(legacy));
  const first = restoreStudio(storage, creator);
  assert.equal(first.users[0].tokens, 2125);
  assert.equal(first.draft.notes, 'Saved private notes');
  assert.equal(restoreStudio(storage, creator).users[0].tokens, 2125);
  assert.equal(restoreStudio(storage, admin).draft.notes, '');
  assert.equal(restoreStudio(storage, admin).transactions.filter(tx => tx.id === `welcome-${creator.id}`).length, 1);
});

test('Creator spending reaches Admin without exposing private drafts and stale writes fail', async () => {
  const { storage, creator, admin } = await fixture();
  const state = restoreStudio(storage, creator);
  const stale = restoreStudio(storage, admin);
  state.draft.notes = 'Private';
  state.users[0].tokens -= 630;
  state.transactions.unshift({ id: 'spend', userId: 'demo', amount: -630, reason: 'Video', createdAt: new Date().toISOString() });
  persistStudio(storage, creator, { ...state, revision: state.revision + 1 });
  const managed = restoreStudio(storage, admin);
  assert.equal(managed.users.find(user => user.id === creator.id).tokens, 1870);
  assert.equal(managed.transactions.find(tx => tx.id === 'spend').userId, creator.id);
  assert.equal(managed.draft.notes, '');
  assert.throws(() => persistStudio(storage, admin, { ...stale, revision: stale.revision + 1 }), /conflict/);
});

test('duplicate login email edits fail before changing stored data and demo profiles survive reseeding', async () => {
  const { storage, admin, seeds } = await fixture();
  const state = restoreStudio(storage, admin);
  state.users.find(user => user.id === 'registered').email = seeds[1].email;
  const before = storage.getItem(STUDIO_KEY);
  assert.throws(() => persistStudio(storage, admin, { ...state, revision: state.revision + 1 }));
  assert.equal(storage.getItem(STUDIO_KEY), before);
  const accounts = updateDemoAccounts([{ ...seeds[0], name: 'Edited Demo', email: 'edited-demo@example.com' }, seeds[1]], seeds);
  assert.equal(accounts[0].name, 'Edited Demo');
  assert.equal(accounts[0].email, 'edited-demo@example.com');
});
