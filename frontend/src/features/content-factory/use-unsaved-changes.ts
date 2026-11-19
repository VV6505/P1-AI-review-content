"use client";

import { useEffect } from "react";

const dirtyEditors = new Set<symbol>();
const HISTORY_INDEX = "reviewlabHistoryIndex";

export function confirmDiscard(dirty: boolean): boolean {
  return !dirty || window.confirm("Bạn có thay đổi chưa lưu. Rời khỏi phần này và bỏ các thay đổi?");
}

function historyIndex(state: unknown): number | null {
  const index = state && typeof state === "object" ? (state as Record<string, unknown>)[HISTORY_INDEX] : null;
  return typeof index === "number" && Number.isSafeInteger(index) ? index : null;
}

// Mounted once in the root layout, before any client-side route changes. Tag real
// entries without adding sentinel entries or replacing Next's router state.
export function UnsavedChangesGuard() {
  useEffect(() => {
    let currentIndex = historyIndex(window.history.state) ?? 0;
    let restoringIndex: number | null = null;
    const history = window.history;
    const originalPush = history.pushState;
    const originalReplace = history.replaceState;
    const indexedState = (data: unknown, index: number) => ({
      ...(data && typeof data === "object" ? data : {}), [HISTORY_INDEX]: index,
    });
    originalReplace.call(history, indexedState(history.state, currentIndex), "");
    const push: History["pushState"] = (data: unknown, unused, url) => {
      const nextIndex = currentIndex + 1;
      originalPush.call(history, indexedState(data, nextIndex), unused, url);
      currentIndex = nextIndex;
    };
    const replace: History["replaceState"] = (data: unknown, unused, url) => {
      originalReplace.call(history, indexedState(data, currentIndex), unused, url);
    };
    history.pushState = push;
    history.replaceState = replace;
    const beforeTraverse = (event: PopStateEvent) => {
      const targetIndex = historyIndex(event.state);
      if (targetIndex === null) return; // Cross-document exits use beforeunload.
      if (restoringIndex !== null) {
        event.stopImmediatePropagation();
        if (targetIndex === restoringIndex) restoringIndex = null;
        else history.go(restoringIndex - targetIndex);
        return;
      }
      if (targetIndex === currentIndex) return;
      if (dirtyEditors.size && !confirmDiscard(true)) {
        // popstate cannot be cancelled. Restore the previous entry before Next
        // handles the traversal, keeping the mounted editor and its input intact.
        event.stopImmediatePropagation();
        restoringIndex = currentIndex;
        history.go(currentIndex - targetIndex);
        return;
      }
      currentIndex = targetIndex;
    };
    window.addEventListener("popstate", beforeTraverse, true);
    return () => {
      window.removeEventListener("popstate", beforeTraverse, true);
      if (history.pushState === push) history.pushState = originalPush;
      if (history.replaceState === replace) history.replaceState = originalReplace;
    };
  }, []);
  return null;
}

export function useUnsavedChanges(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const editor = Symbol("unsaved-editor");
    dirtyEditors.add(editor);
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    const beforeNavigate = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(target instanceof HTMLAnchorElement) || target.target === "_blank" || target.hasAttribute("download") || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (target.origin === window.location.origin && (target.pathname !== window.location.pathname || target.search !== window.location.search) && !confirmDiscard(true)) {
        event.preventDefault(); event.stopImmediatePropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", beforeNavigate, true);
    return () => { dirtyEditors.delete(editor); window.removeEventListener("beforeunload", beforeUnload); document.removeEventListener("click", beforeNavigate, true); };
  }, [dirty]);
}
