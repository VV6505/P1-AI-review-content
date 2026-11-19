"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ACCOUNTS_KEY, SESSION_KEY, demoAccounts, findLoginAccount, normalizeEmail, passwordHash, publicAccount, readAccounts, updateDemoAccounts, validateRegistration, type Account } from "./model";

type Auth = {
  account: Account | null; ready: boolean; error: boolean;
  signIn: (identifier: string, password: string) => Promise<Account>;
  signUp: (name: string, email: string, password: string, confirmation: string) => Promise<Account>;
  signOut: () => void;
};
const Context = createContext<Auth | null>(null);

function savedAccounts() {
  const raw = localStorage.getItem(ACCOUNTS_KEY);
  if (!raw) throw new Error("storage");
  return readAccounts(raw);
}

export function MockAuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    const seeds = demoAccounts();
    async function restore() {
      try {
        const demo = await seeds;
        if (!alive) return;
        const raw = localStorage.getItem(ACCOUNTS_KEY);
        const accounts = updateDemoAccounts(raw ? readAccounts(raw) : [], demo);
        const next = JSON.stringify(accounts);
        if (raw !== next) localStorage.setItem(ACCOUNTS_KEY, next);
        const id = localStorage.getItem(SESSION_KEY);
        const saved = savedAccounts().find(item => item.id === id);
        if (alive) { setAccount(saved ? publicAccount(saved) : null); setError(false); }
      } catch { if (alive) { setAccount(null); setError(true); } }
      finally { if (alive) setReady(true); }
    }
    void restore();
    const sync = (event: StorageEvent) => {
      if (event.key === ACCOUNTS_KEY || event.key === SESSION_KEY || event.key === null) void restore();
    };
    window.addEventListener("storage", sync);
    return () => { alive = false; window.removeEventListener("storage", sync); };
  }, []);

  function startSession(next: Account) {
    localStorage.setItem(SESSION_KEY, next.id);
    setAccount(next);
    return next;
  }
  async function signIn(identifier: string, password: string) {
    if (!ready || error) throw new Error("storage");
    const found = findLoginAccount(savedAccounts(), identifier);
    if (!found || found.passwordHash !== await passwordHash(password, found.salt)) throw new Error("credentials");
    return startSession(publicAccount(found));
  }
  async function signUp(name: string, email: string, password: string, confirmation: string) {
    if (!ready || error) throw new Error("storage");
    validateRegistration(name, email, password, confirmation);
    const salt = crypto.randomUUID();
    const next = { id: crypto.randomUUID(), name: name.trim(), email: normalizeEmail(email), role: "creator" as const, salt, passwordHash: await passwordHash(password, salt) };
    const accounts = savedAccounts();
    if (accounts.some(item => item.email === next.email)) throw new Error("duplicate");
    localStorage.setItem(ACCOUNTS_KEY, JSON.stringify([...accounts, next]));
    return startSession(publicAccount(next));
  }
  function signOut() {
    localStorage.removeItem(SESSION_KEY);
    setAccount(null);
  }
  return <Context.Provider value={{ account, ready, error, signIn, signUp, signOut }}>{children}</Context.Provider>;
}

export function useAuth() {
  const auth = useContext(Context);
  if (!auth) throw new Error("MockAuthProvider required");
  return auth;
}
