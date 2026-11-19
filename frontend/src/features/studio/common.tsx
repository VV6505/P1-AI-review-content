"use client";
import { useEffect, useRef, type ReactNode } from "react";
import { usePreferences } from "./preferences";
import { useStudio } from "./provider";

export function Modal({ title, children, close }: { title: string; children: ReactNode; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = usePreferences();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className="studio-dialog" aria-labelledby="dialog-title" onCancel={close} onClick={event => { if (event.target === event.currentTarget) { const box = event.currentTarget.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close(); } }}><div className="dialog-heading"><h2 id="dialog-title">{title}</h2><button type="button" className="text-button" onClick={close}>{t("Đóng", "Close")}</button></div>{children}</dialog>;
}
export function LocalNotice() {
  const { t } = usePreferences();
  return <p className="local-notice">{t("Bản xem thử · Dữ liệu mẫu", "Preview · Sample data")}</p>;
}
export function StorageNotice() {
  const { error } = useStudio(); const { t } = usePreferences();
  return error ? <p role="alert" className="studio-error">{t("Không thể đọc/lưu dữ liệu. Dữ liệu cũ được giữ nguyên; tải lại trang để thử lại.", "Could not read/save data. Existing data is preserved; reload to retry.")}</p> : null;
}
export function Status({ active }: { active: boolean }) { const { t } = usePreferences(); return <span className={`studio-status ${active ? "positive" : "muted"}`}>{active ? t("Hoạt động", "Active") : t("Tạm dừng", "Paused")}</span>; }
