"use client";

import { useEffect, useRef, useState } from "react";
import { usePreferences } from "./preferences";
import "./product-progress.css";

export type ProductPhase = "idle" | "crawl" | "extract" | "review" | "failed";

function pause(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => { signal.removeEventListener("abort", cancel); resolve(); }, 700);
    function cancel() { clearTimeout(timer); reject(new DOMException("Cancelled", "AbortError")); }
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
  });
}

// Delays demonstrate the UI states only. No website or provider is called.
export function useProductProcessing() {
  const [phase, setPhase] = useState<ProductPhase>("idle");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  function cancel() {
    controller.current?.abort();
    controller.current = null;
    setPhase("idle");
  }
  async function start(prepare: () => boolean) {
    if (controller.current) return;
    const run = new AbortController();
    controller.current = run;
    try {
      setPhase("crawl");
      await pause(run.signal);
      setPhase("extract");
      await pause(run.signal);
      if (!run.signal.aborted) setPhase(prepare() ? "review" : "failed");
    } catch {
      if (!run.signal.aborted) setPhase("failed");
    } finally {
      if (controller.current === run) controller.current = null;
    }
  }
  return { phase, busy: phase === "crawl" || phase === "extract", start, cancel };
}

export function ProductProgress({ phase, confirmed }: { phase: ProductPhase; confirmed: boolean }) {
  const { t } = usePreferences();
  const steps = [t("Thu thập nguồn", "Collect sources"), t("Chuẩn hóa thông tin", "Organize information"), t("Review sản phẩm", "Review product")];
  const current = phase === "crawl" ? 0 : phase === "extract" ? 1 : phase === "review" ? 2 : -1;
  const status = phase === "idle" ? t("Sẵn sàng phân tích", "Ready to analyze")
    : phase === "failed" ? t("Xử lý chưa hoàn tất", "Processing incomplete")
    : confirmed ? t("Đã xác nhận sản phẩm", "Product confirmed")
    : phase === "review" ? t("Kiểm tra thông tin bên dưới trước khi xác nhận.", "Check the information below before confirming.")
    : t(`Đang ${current === 0 ? "thu thập nguồn" : "chuẩn hóa thông tin"}…`, current === 0 ? "Collecting sources…" : "Organizing information…");

  return <section className="product-progress" aria-label={t("Tiến trình xử lý sản phẩm", "Product processing progress")}>
    <ol>{steps.map((label, index) => {
      const done = index < current || (index === 2 && confirmed);
      return <li key={label} className={done ? "done" : index === current ? "current" : ""} aria-current={index === current && !confirmed ? "step" : undefined}><span className="product-step-number" aria-hidden="true">{index + 1}</span><span>{label}<small>{done ? t("Hoàn tất", "Complete") : index === current ? t("Bước hiện tại", "Current step") : t("Chờ xử lý", "Waiting")}</small></span></li>;
    })}</ol>
    <p role="status" aria-live="polite">{status}</p>
    <p className="field-hint">{t("Tiến trình mô phỏng. Dữ liệu mẫu, không truy cập website.", "Simulated progress. Sample data; no website is accessed.")}</p>
  </section>;
}
