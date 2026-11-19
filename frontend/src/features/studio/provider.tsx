"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { initialStudio, STUDIO_KEY, type StudioState } from "./model";
import { ACCOUNTS_KEY } from "../auth/model";
import { persistStudio, restoreStudio } from "./storage";
import { useAuth } from "@/features/auth/provider";

type Store = StudioState & { ready: boolean; error: boolean; commit: (update: (state: StudioState) => StudioState) => void };
const Context = createContext<Store | null>(null);
export function StudioProvider({ children }: { children: ReactNode }) {
  const { account } = useAuth();
  const storageKey = account && !["demo", "admin-demo"].includes(account.id) ? `${STUDIO_KEY}.${account.id}` : STUDIO_KEY;
  const [state, setState] = useState(initialStudio);
  const current = useRef(state);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    const restore = () => {
      if (!alive) return;
      try {
        if (!account) return;
        const restored = restoreStudio(localStorage, account);
        current.current = restored; setState(restored); setError(false); setReady(true);
      } catch { setError(true); setReady(false); }
    };
    queueMicrotask(restore);
    const sync = (event: StorageEvent) => { if ([storageKey, STUDIO_KEY, ACCOUNTS_KEY, null].includes(event.key)) restore(); };
    window.addEventListener("storage", sync);
    return () => { alive = false; window.removeEventListener("storage", sync); };
  }, [account, storageKey]);
  function commit(update: (state: StudioState) => StudioState) {
    if (!ready || !account) throw new Error("storage");
    try {
      const next = { ...update(current.current), revision: current.current.revision + 1 };
      persistStudio(localStorage, account, next);
      current.current = next; setState(next); setError(false);
    } catch { setError(true); throw new Error("storage"); }
  }
  return <Context.Provider value={{ ...state, ready, error, commit }}>{children}</Context.Provider>;
}
export function useStudio() {
  const context = useContext(Context);
  if (!context) throw new Error("StudioProvider required");
  return context;
}
