export type Account = { id: string; name: string; email: string; role: "creator" | "admin" };
export type MockAccount = Account & { salt: string; passwordHash: string };
export const ACCOUNTS_KEY = "reviewlab.mock-accounts.v1";
export const SESSION_KEY = "reviewlab.mock-session.v1";
export const DEMO_PASSWORD = "123456";

export function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

export function validateRegistration(name: string, email: string, password: string, confirmation: string) {
  if (name.trim().length < 2 || name.trim().length > 80) throw new Error("name");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizeEmail(email))) throw new Error("email");
  if (password.length < 8 || password.length > 128) throw new Error("password");
  if (password !== confirmation) throw new Error("confirmation");
}

// This is a browser-only mock. Never persist a password in plain text.
export async function passwordHash(password: string, salt: string) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", salt: encoder.encode(salt), iterations: 100_000, hash: "SHA-256" }, key, 256);
  return Array.from(new Uint8Array(bits), byte => byte.toString(16).padStart(2, "0")).join("");
}

export async function demoAccounts(): Promise<MockAccount[]> {
  const accounts: Account[] = [
    { id: "demo", name: "Creator", email: "creator@reviewlab.demo", role: "creator" },
    { id: "admin-demo", name: "Admin", email: "admin@reviewlab.demo", role: "admin" },
  ];
  return Promise.all(accounts.map(async account => ({ ...account, salt: account.id, passwordHash: await passwordHash(DEMO_PASSWORD, account.id) })));
}

export function updateDemoAccounts(accounts: MockAccount[], seeds: MockAccount[]) {
  const seedIds = new Set(seeds.map(account => account.id));
  return [...seeds.map(seed => {
    const saved = accounts.find(account => account.id === seed.id);
    return saved ? { ...seed, name: saved.name, email: saved.email } : seed;
  }), ...accounts.filter(account => !seedIds.has(account.id))];
}

export function findLoginAccount(accounts: MockAccount[], identifier: string) {
  const login = normalizeEmail(identifier);
  const demoId = login === "creator" ? "demo" : login === "admin" ? "admin-demo" : null;
  return accounts.find(account => demoId ? account.id === demoId : account.email === login);
}

export function readAccounts(raw: string): MockAccount[] {
  const accounts = JSON.parse(raw) as MockAccount[];
  if (!Array.isArray(accounts) || accounts.some(account => !account ||
    ![account.id, account.name, account.email, account.salt].every(value => typeof value === "string" && value.length > 0) ||
    !["creator", "admin"].includes(account.role) || !/^[a-f0-9]{64}$/.test(account.passwordHash)) ||
    new Set(accounts.map(account => account.email)).size !== accounts.length ||
    new Set(accounts.map(account => account.id)).size !== accounts.length) throw new Error("storage");
  return accounts;
}

export function publicAccount({ id, name, email, role }: MockAccount): Account {
  return { id, name, email, role };
}

export function loginDestination(next: string | null, role: Account["role"]) {
  const workspace = role === "admin" ? "/admin/" : "/creator/";
  if (next?.startsWith(workspace)) return next;
  return role === "admin" ? "/admin/users" : "/creator/create";
}
