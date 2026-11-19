"use client";

import { useState, type ReactNode } from "react";
import { usePreferences } from "./preferences";
import { ReferenceFiles } from "./reference-files";
import type { ProductReview, ReferenceFile } from "./model";
import { ProductProgress, type ProductPhase } from "./product-progress";

export function ProjectDetails({ review, confirmed, files, error, phase, prepare, change, confirm, removeFile, children }: {
  review: ProductReview | null; confirmed: boolean; files: ReferenceFile[]; error: string;
  phase: ProductPhase;
  prepare: () => void; change: (patch: Partial<ProductReview>) => void;
  confirm: () => boolean; removeFile: (id: string) => void; children: ReactNode;
}) {
  const { t } = usePreferences();
  const [tab, setTab] = useState("product");
  const busy = phase === "crawl" || phase === "extract";
  return <>
    <div className="project-details-tabs" role="tablist" aria-label={t("Chi tiết dự án", "Project details")}>
      <button type="button" role="tab" id="product-details-tab" aria-controls="product-details-panel" aria-selected={tab === "product"} onClick={() => setTab("product")}>{t("Sản phẩm", "Product")}</button>
      <button type="button" role="tab" id="video-details-tab" aria-controls="video-details-panel" aria-selected={tab === "video"} disabled={!review || busy} onClick={() => setTab("video")}>{t("Cấu hình", "Configuration")}</button>
    </div>
    <div role="tabpanel" id="product-details-panel" aria-labelledby="product-details-tab" aria-busy={busy} hidden={tab !== "product"}>
      <ProductProgress phase={review ? "review" : phase} confirmed={confirmed} />
      {review ? <form className="editor-form product-review-form" onSubmit={event => { event.preventDefault(); if (confirm()) setTab("video"); }}>
        <div className="product-review-source"><span>{t("Link sản phẩm", "Product link")}</span><a href={review.sourceUrl} target="_blank" rel="noreferrer">{review.sourceUrl}</a></div>
        <label>{t("Tên sản phẩm", "Product name")}<input required aria-label={t("Tên sản phẩm", "Product name")} value={review.name} onChange={event => change({ name: event.target.value })} /></label>
        <label>{t("Mô tả sản phẩm", "Product description")}<textarea required aria-label={t("Mô tả sản phẩm", "Product description")} rows={3} value={review.description} onChange={event => change({ description: event.target.value })} /></label>
        <label>{t("Tính năng / thông số", "Features / specifications")}<textarea aria-label={t("Tính năng / thông số", "Features / specifications")} rows={3} value={review.features} onChange={event => change({ features: event.target.value })} /></label>
        <div className="config-grid">
          <label>{t("Giá / gói", "Price / plans")}<textarea aria-label={t("Giá / gói", "Price / plans")} rows={2} value={review.pricing} onChange={event => change({ pricing: event.target.value })} placeholder={t("Chưa có thông tin giá", "No pricing information")} /></label>
          <label>{t("Biến thể", "Variant")}<textarea aria-label={t("Biến thể", "Variant")} rows={2} value={review.variant} onChange={event => change({ variant: event.target.value })} placeholder={t("Màu, kích thước hoặc phiên bản…", "Color, size, or version…")} /></label>
        </div>
        <label>{t("Nguồn thông tin", "Information sources")}<textarea required aria-label={t("Nguồn thông tin", "Information sources")} rows={2} value={review.sources} onChange={event => change({ sources: event.target.value })} /><span className="field-hint">{t("Mỗi dòng một link. Thông tin sửa tay do bạn cung cấp.", "One link per line. Edited information is supplied by you.")}</span></label>
        <div className="product-review-media"><strong>{t("Ảnh / tài liệu tham khảo", "Reference images / documents")}</strong>{files.length ? <ReferenceFiles files={files} remove={removeFile} /> : <p className="field-hint">{t("Thêm tư liệu bằng nút + trong khung nhập.", "Add references using + in the composer.")}</p>}</div>
        {error && <p role="alert" className="studio-error">{error}</p>}
        <div className="product-review-confirmation"><span className={confirmed ? "review-confirmed" : "review-pending"}>{confirmed ? t("Đã xác nhận thông tin", "Information confirmed") : t("Chưa xác nhận", "Not confirmed")}</span><button className="primary-button" disabled={confirmed || !review.name.trim() || !review.description.trim() || !review.sources.trim()}>{t("Xác nhận sản phẩm", "Confirm product")}</button></div>
      </form> : <div className="product-review-empty"><p>{busy ? t("Thông tin sản phẩm sẽ hiển thị khi xử lý hoàn tất.", "Product information will appear when processing finishes.") : t("Chuẩn bị thông tin mẫu để kiểm tra và chỉnh sửa.", "Prepare sample information to review and edit.")}</p>{!busy && <button type="button" className="secondary-button" onClick={prepare}>{phase === "failed" ? t("Thử lại", "Retry") : t("Phân tích sản phẩm", "Analyze product")}</button>}{error && <p role="alert" className="studio-error">{error}</p>}</div>}
    </div>
    <div role="tabpanel" id="video-details-panel" aria-labelledby="video-details-tab" hidden={tab !== "video"}>{children}</div>
  </>;
}
