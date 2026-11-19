import { ACCOUNTS_KEY, normalizeEmail, readAccounts, type Account } from "../auth/model.ts";
import { initialStudio, parseStudio, STUDIO_KEY, type StudioState } from "./model.ts";

export const WELCOME_TOKENS = 2500;
const scoped = (account: Account) => !["demo", "admin-demo"].includes(account.id);
const privateKey = (account: Account) => scoped(account) ? `${STUDIO_KEY}.${account.id}` : STUDIO_KEY;

// The shared store owns management data. Scoped stores retain drafts and history.
function management(storage: Storage): StudioState {
  const raw = storage.getItem(STUDIO_KEY);
  const state = raw ? parseStudio(raw) : structuredClone(initialStudio);
  const accounts = readAccounts(storage.getItem(ACCOUNTS_KEY) ?? "[]");
  let changed = !raw;
  const free = state.plans.find(plan => plan.id === "free");
  if (free?.tokens === 500) { free.tokens = WELCOME_TOKENS; changed = true; }
  for (const account of accounts.filter(item => item.role === "creator" && item.id !== "demo")) {
    if (state.users.some(user => user.id === account.id)) continue;
    const legacyRaw = storage.getItem(`${STUDIO_KEY}.${account.id}`);
    const legacy = legacyRaw ? parseStudio(legacyRaw) : null;
    const oldUser = legacy?.users.find(user => user.id === "demo");
    state.users.push({ id: account.id, name: account.name, email: account.email,
      planId: oldUser?.planId ?? "free", active: oldUser?.active ?? true,
      tokens: oldUser ? oldUser.tokens + WELCOME_TOKENS - 500 : WELCOME_TOKENS });
    state.transactions.push(...(legacy?.transactions ?? []).map(tx => ({ ...tx, userId: tx.userId === "demo" ? account.id : tx.userId })));
    state.transactions.push({ id: `welcome-${account.id}`, userId: account.id,
      amount: oldUser ? WELCOME_TOKENS - 500 : WELCOME_TOKENS,
      reason: "Token chào mừng mẫu", createdAt: new Date().toISOString() });
    changed = true;
  }
  if (changed) {
    state.revision += 1;
    parseStudio(JSON.stringify(state));
    storage.setItem(STUDIO_KEY, JSON.stringify(state));
  }
  return state;
}

export function restoreStudio(storage: Storage, account: Account): StudioState {
  const shared = management(storage);
  if (!scoped(account)) return shared;
  const raw = storage.getItem(privateKey(account));
  const local = raw ? parseStudio(raw) : structuredClone(initialStudio);
  const user = shared.users.find(item => item.id === account.id);
  if (!user) throw new Error("account");
  return { ...local, revision: shared.revision, users: [{ ...user, id: "demo" }], plans: shared.plans,
    transactions: shared.transactions.filter(tx => tx.userId === account.id).map(tx => ({ ...tx, userId: "demo" })) };
}

export function persistStudio(storage: Storage, account: Account, next: StudioState) {
  const shared = management(storage);
  if (shared.revision !== next.revision - 1) throw new Error("conflict");
  parseStudio(JSON.stringify(next));
  const merged = scoped(account) ? {
    ...shared, revision: next.revision, plans: next.plans,
    users: shared.users.map(user => user.id === account.id ? { ...next.users.find(item => item.id === "demo")!, id: account.id } : user),
    transactions: [...shared.transactions.filter(tx => tx.userId !== account.id),
      ...next.transactions.map(tx => ({ ...tx, userId: account.id }))],
  } : next;
  parseStudio(JSON.stringify(merged));
  const rawAccounts = storage.getItem(ACCOUNTS_KEY);
  const accounts = readAccounts(rawAccounts ?? "[]").map(item => {
    const user = merged.users.find(user => user.id === item.id);
    return user ? { ...item, name: user.name, email: normalizeEmail(user.email) } : item;
  });
  // Validate profile edits before writing, including duplicate login emails.
  readAccounts(JSON.stringify(accounts));
  const keys = [...new Set([privateKey(account), STUDIO_KEY, ACCOUNTS_KEY])];
  const previous = keys.map(key => [key, storage.getItem(key)] as const);
  try {
    if (scoped(account)) storage.setItem(privateKey(account), JSON.stringify(next));
    storage.setItem(STUDIO_KEY, JSON.stringify(merged));
    storage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
  } catch (error) {
    for (const [key, value] of previous) { if (value === null) storage.removeItem(key); else storage.setItem(key, value); }
    throw error;
  }
}
