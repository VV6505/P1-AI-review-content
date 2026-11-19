"use client";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Language, Theme } from "./model";
export type VideoView = "grid" | "list";
type Preferences = {
  language: Language; theme: Theme; videoView: VideoView; sidebarCollapsed: boolean;
  setLanguage: (value: Language) => void; setTheme: (value: Theme) => void;
  setVideoView: (value: VideoView) => void; setSidebarCollapsed: (value: boolean) => void;
  t: (vi: string, en: string) => string; number: (value: number) => string; date: (value: string) => string;
};
const Context = createContext<Preferences | null>(null);
export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [language, changeLanguage] = useState<Language>("vi");
  const [theme, changeTheme] = useState<Theme>("light");
  const [videoView, changeVideoView] = useState<VideoView>("grid");
  const [sidebarCollapsed, changeSidebarCollapsed] = useState(false);
  useEffect(() => {
    let alive = true;
    const restore = () => {
      if (!alive) return;
      try {
        changeLanguage(localStorage.getItem("reviewlab.language") === "en" ? "en" : "vi");
        changeTheme(localStorage.getItem("reviewlab.theme") === "dark" ? "dark" : "light");
        changeVideoView(localStorage.getItem("reviewlab.video-view") === "list" ? "list" : "grid");
        changeSidebarCollapsed(localStorage.getItem("reviewlab.sidebar") === "collapsed");
      } catch { /* Preferences remain available for this session. */ }
    };
    queueMicrotask(restore);
    const sync = (event: StorageEvent) => { if (event.key?.startsWith("reviewlab.")) restore(); };
    window.addEventListener("storage", sync);
    return () => { alive = false; window.removeEventListener("storage", sync); };
  }, []);
  useEffect(() => { document.documentElement.lang = language; document.documentElement.classList.toggle("dark", theme === "dark"); }, [language, theme]);
  function save(key: string, value: string) { try { localStorage.setItem(key, value); } catch {} }
  const locale = language === "vi" ? "vi-VN" : "en-US";
  return <Context.Provider value={{ language, theme, videoView, sidebarCollapsed,
    setLanguage: value => { changeLanguage(value); save("reviewlab.language", value); },
    setTheme: value => { changeTheme(value); save("reviewlab.theme", value); },
    setVideoView: value => { changeVideoView(value); save("reviewlab.video-view", value); },
    setSidebarCollapsed: value => { changeSidebarCollapsed(value); save("reviewlab.sidebar", value ? "collapsed" : "expanded"); },
    t: (vi, en) => language === "vi" ? vi : en,
    number: value => value.toLocaleString(locale),
    date: value => new Date(value).toLocaleString(locale, { timeZone: "Asia/Ho_Chi_Minh", dateStyle: "short", timeStyle: "short" }),
  }}>{children}</Context.Provider>;
}
export function usePreferences() { const value = useContext(Context); if (!value) throw new Error("PreferencesProvider required"); return value; }
