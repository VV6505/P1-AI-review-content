"use client";

import { usePreferences } from "./preferences";
import { templateForStyle, type Draft } from "./model";

export function RequirementsReview({ draft, busy, error, changeDescription, confirm }: {
  draft: Draft; busy: boolean; error: string;
  changeDescription: (notes: string) => void; confirm: () => void;
}) {
  const { t } = usePreferences();
  const product = draft.productReview!;
  const template = templateForStyle(draft.style);
  return <form className="editor-form requirements-review" onSubmit={event => { event.preventDefault(); confirm(); }}>
    <p className="field-hint">{t("Kiểm tra thông tin và mong muốn trước khi tiếp tục. Bạn không cần viết kịch bản.", "Review the information and preferences before continuing. You do not need to write a script.")}</p>
    <div className="requirements-product"><strong>{product.name}</strong><a href={product.sourceUrl} target="_blank" rel="noreferrer">{product.sourceUrl}</a><p>{product.description}</p><p className="sample-information-note">{t("Thông tin mẫu hoặc do bạn cung cấp; hệ thống chưa thu thập và xác minh từ website.", "Sample information or information you provided; the system has not collected or verified it from the website.")}</p></div>
    <label htmlFor="review-video-description">{t("Mô tả / mong muốn về video", "Video description / preferences")}</label>
    <textarea id="review-video-description" rows={4} maxLength={2000} value={draft.notes} onChange={event => changeDescription(event.target.value)} placeholder={t("Ví dụ: giới thiệu cho nhân viên văn phòng, tập trung việc học AI, giọng thân thiện.", "For example: introduce it to office workers, focus on learning AI, use a friendly tone.")} />
    <p className="field-hint">{t("Mong muốn định hướng nội dung; số liệu hoặc thông tin sản phẩm mới cần được kiểm tra trước khi đưa vào kịch bản.", "Preferences guide the content; new product facts or metrics need checking before use in the script.")}</p>
    <dl className="requirements-settings">
      <div><dt>{t("Phong cách", "Style")}</dt><dd>{t(template.vi, template.en)}</dd></div>
      <div><dt>{t("Đầu ra", "Output")}</dt><dd>{draft.ratio} · {draft.resolution} · {draft.count} video</dd></div>
      <div><dt>{t("Thời lượng mục tiêu", "Target duration")}</dt><dd>{draft.duration}s</dd></div>
      <div><dt>{t("Ngôn ngữ", "Language")}</dt><dd>{draft.outputLanguage === "vi" ? "Tiếng Việt" : "English"}</dd></div>
    </dl>
    <details className="requirements-facts"><summary>{t("Thông tin sản phẩm và tư liệu tham khảo", "Product information and references")}</summary>
      {product.features && <div><strong>{t("Tính năng / thông số", "Features / specifications")}</strong><p>{product.features}</p></div>}
      {product.pricing && <div><strong>{t("Giá / gói", "Price / plans")}</strong><p>{product.pricing}</p></div>}
      {product.variant && <div><strong>{t("Biến thể", "Variant")}</strong><p>{product.variant}</p></div>}
      <div><strong>{t("Nguồn", "Sources")}</strong><p>{product.sources}</p></div>
      {!!draft.references.length && <ul>{draft.references.map(file => <li key={file.id}>{file.name}</li>)}</ul>}
    </details>
    <ol className="requirements-next-steps" aria-label={t("Các bước tiếp theo", "Next steps")}>
      <li>{t("Duyệt hướng nội dung và dàn ý", "Review the direction and outline")}</li>
      <li>{t("Xem, chỉnh và xác nhận kịch bản", "Review, edit and approve the script")}</li>
      <li>{t("Dựng video, xem và góp ý", "Produce the video, watch and give feedback")}</li>
    </ol>
    <p className="field-hint">{t("Luồng AI đang được tích hợp. Lần này chỉ mở clip minh họa có sẵn; chưa sinh hướng nội dung, kịch bản hoặc video từ yêu cầu này.", "The AI workflow is being integrated. This opens an existing sample clip; it does not generate a direction, script or video from this request yet.")}</p>
    {error && <p className="studio-error" role="alert">{error}</p>}
    <div className="dialog-actions"><button className="primary-button" disabled={busy}>{t("Xác nhận và xem mẫu", "Confirm and view sample")}</button></div>
  </form>;
}
