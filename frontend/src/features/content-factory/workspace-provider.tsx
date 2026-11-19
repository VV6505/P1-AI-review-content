"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { initialWorkspace, parseWorkspace, WORKSPACE_KEY, type DemoRole, type Project, type WorkspaceState, type IntakeDraft } from "./model";

type Workspace = WorkspaceState & { ready: boolean; storageError: string; setSelectedId: (id: string) => void; setRole: (role: DemoRole) => void; addProject: (project: Project) => void; updateProject: (id: string, update: (project: Project) => Project) => void; saveIntake: (draft: IntakeDraft | null) => void };
const WorkspaceContext = createContext<Workspace | null>(null);

export function WorkspaceProvider({ children, storageScope }: { children: ReactNode; storageScope?: string }) {
  const storageKey = storageScope && !["demo", "admin-demo"].includes(storageScope) ? `${WORKSPACE_KEY}.${storageScope}` : WORKSPACE_KEY;
  const [state, setState] = useState<WorkspaceState>(initialWorkspace);
  const current = useRef(state);
  const [ready, setReady] = useState(false);
  const [storageError, setStorageError] = useState("");
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      try {
        const raw = localStorage.getItem(storageKey);
        const restored = raw ? parseWorkspace(raw) : initialWorkspace;
        current.current = restored; setState(restored);
      } catch { setStorageError("Không đọc được dữ liệu mock đã lưu. Dữ liệu cũ được giữ nguyên; hãy kiểm tra bộ nhớ trình duyệt."); }
      setReady(true);
    });
    return () => { cancelled = true; };
  }, [storageKey]);
  function commit(update: (value: WorkspaceState) => WorkspaceState) {
    if (!ready) throw new Error("Đang khôi phục workspace.");
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw && parseWorkspace(raw).revision !== current.current.revision) throw new Error("Workspace đã đổi ở tab khác. Tải lại trang trước khi lưu.");
      const next = { ...update(current.current), revision: current.current.revision + 1 };
      localStorage.setItem(storageKey, JSON.stringify(next));
      current.current = next; setState(next); setStorageError("");
    } catch (error) {
      const message = error instanceof Error && error.message.includes("tab khác") ? error.message : "Không thể lưu mock vào trình duyệt. Thay đổi chưa được lưu; hãy kiểm tra bộ nhớ và thử lại.";
      setStorageError(message); throw new Error(message);
    }
  }
  function setSelectedId(id: string) { commit((value) => ({ ...value, selectedId: id })); }
  function setRole(role: DemoRole) { commit((value) => ({ ...value, role })); }
  function addProject(project: Project) {
    if (current.current.projects.some((p) => p.url === project.url)) throw new Error("Website URL đã có trong workspace.");
    commit((value) => ({ ...value, projects: [project, ...value.projects], selectedId: project.id, intakeDraft: null }));
  }
  function updateProject(id: string, update: (project: Project) => Project) {
    const project = current.current.projects.find((item) => item.id === id);
    if (!project) throw new Error("Không tìm thấy sản phẩm.");
    const next = update(project);
    commit((value) => ({ ...value, projects: value.projects.map((item) => item.id === id ? next : item) }));
  }
  const saveIntake = (draft: IntakeDraft | null) => commit(value => ({ ...value, intakeDraft: draft }));
  return <WorkspaceContext.Provider value={{ ...state, ready, storageError, setSelectedId, setRole, addProject, updateProject, saveIntake }}>{children}</WorkspaceContext.Provider>;
}
export function useWorkspace() {
  const workspace = useContext(WorkspaceContext);
  if (!workspace) throw new Error("WorkspaceProvider is required");
  return workspace;
}
