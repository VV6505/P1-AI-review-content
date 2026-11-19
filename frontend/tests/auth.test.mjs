import test from 'node:test';
import assert from 'node:assert/strict';
import { demoAccounts, DEMO_PASSWORD, findLoginAccount, loginDestination, normalizeEmail, passwordHash, publicAccount, readAccounts, updateDemoAccounts, validateRegistration } from '../src/features/auth/model.ts';

test('mock accounts verify passwords without persisting plaintext credentials', async () => {
  const accounts = await demoAccounts();
  assert.equal(accounts[0].passwordHash, await passwordHash(DEMO_PASSWORD, accounts[0].salt));
  assert.notEqual(accounts[0].passwordHash, await passwordHash('WrongPassword', accounts[0].salt));
  assert.notEqual(accounts[0].passwordHash, accounts[1].passwordHash);
  assert.equal(JSON.stringify(accounts).includes(DEMO_PASSWORD), false);
  assert.deepEqual(readAccounts(JSON.stringify(accounts)), accounts);
  assert.deepEqual(Object.keys(publicAccount(accounts[0])), ['id', 'name', 'email', 'role']);
  assert.throws(() => readAccounts(JSON.stringify([...accounts, accounts[0]])));
  assert.throws(() => readAccounts('{broken'));
});

test('demo credentials migrate without removing registered accounts and support username login', async () => {
  const seeds = await demoAccounts();
  const oldDemo = { ...seeds[0], name: 'Minh Anh', passwordHash: await passwordHash('Reviewlab123', seeds[0].salt) };
  const registered = { ...seeds[0], id: 'registered', name: 'Test User', email: 'user@example.com' };
  const migrated = updateDemoAccounts([oldDemo, seeds[1], registered], seeds);
  assert.equal(DEMO_PASSWORD, '123456');
  assert.equal(findLoginAccount(migrated, ' CREATOR ').id, 'demo');
  assert.equal(findLoginAccount(migrated, 'admin').id, 'admin-demo');
  assert.equal(findLoginAccount(migrated, 'USER@example.com'), registered);
  assert.equal(findLoginAccount(migrated, 'unknown'), undefined);
  assert.notEqual(migrated[0].passwordHash, oldDemo.passwordHash);
  assert.deepEqual(updateDemoAccounts(migrated, seeds), migrated);
});

test('registration validates identity and confirmation; login return paths remain internal and role-aware', () => {
  assert.equal(normalizeEmail('  Creator@Example.com '), 'creator@example.com');
  assert.doesNotThrow(() => validateRegistration('Test User', 'test@example.com', 'Test12345', 'Test12345'));
  assert.throws(() => validateRegistration(' ', 'test@example.com', 'Test12345', 'Test12345'), /name/);
  assert.throws(() => validateRegistration('Test User', 'bad-email', 'Test12345', 'Test12345'), /email/);
  assert.throws(() => validateRegistration('Test User', 'test@example.com', 'short', 'short'), /password/);
  assert.throws(() => validateRegistration('Test User', 'test@example.com', 'Test12345', 'Different'), /confirmation/);
  assert.equal(loginDestination('/creator/project/saved', 'creator'), '/creator/project/saved');
  assert.equal(loginDestination('/admin/pkb', 'creator'), '/creator/create');
  assert.equal(loginDestination('/admin/pkb', 'admin'), '/admin/pkb');
  assert.equal(loginDestination('/creator/create', 'admin'), '/admin/users');
  assert.equal(loginDestination('/creator/project/saved', 'admin'), '/admin/users');
  assert.equal(loginDestination(null, 'admin'), '/admin/users');
  assert.equal(loginDestination(null, 'creator'), '/creator/create');
  assert.equal(loginDestination('https://example.com', 'creator'), '/creator/create');
  assert.equal(loginDestination('//example.com', 'admin'), '/admin/users');
});
