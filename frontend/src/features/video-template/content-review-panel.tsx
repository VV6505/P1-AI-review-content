"use client";

import { usePreferences } from "@/features/studio/preferences";
import { contentReview } from "./content-review";
import type { Project } from "./model";

export function ContentReviewPanel({ project, activeScene, seek }: { project: Project; activeScene: string; seek: (time: number) => void }) {
  const { t } = usePreferences();
  const review = contentReview(project);
  if (!review) return null;
  const roleLabels: Record<string, string> = { hook: t("Mở đầu", "Hook"), problem: t("Vấn đề", "Problem"), demo: t("Minh họa", "Demo"), result: t("Kết quả", "Result"), proof: t("Bằng chứng", "Proof"), cta: t("Kêu gọi hành động", "Call to action") };
  const visualLabels: Record<string, string> = { screen_recording: t("Clip thao tác", "Screen recording"), screenshot: t("Ảnh trang", "Screenshot"), product_asset: t("Tư liệu sản phẩm", "Product asset"), ai_generated_image: t("Ảnh AI", "AI image"), text_card: t("Chỉ có chữ", "Text card"), logo: "Logo" };
  return <details className="content-review-panel" open>
    <summary>{t("Hướng nội dung và kịch bản", "Direction and script")}</summary>
    <header><h2>{review.title}</h2><p>{t("Đối tượng", "Audience")}: {review.audience}</p><p><strong>{t("Mở đầu", "Hook")}: </strong>{review.hook}</p></header>
    <dl className="requirements-settings">
      <div><dt>{t("Mục tiêu MP4", "MP4 target")}</dt><dd>{review.target}s</dd></div>
      <div><dt>{t("Ước tính trước giọng đọc", "Estimate before speech")}</dt><dd>{review.estimated === undefined ? t("Chưa có", "Unavailable") : `${review.estimated.toFixed(2)}s`}</dd></div>
      <div><dt>{t("Timeline bàn giao", "Supplied timeline")}</dt><dd>{review.timeline.toFixed(2)}s · {review.timing === "measured" ? t("đánh dấu đo từ audio", "marked measured from audio") : t("dữ liệu thử", "fixture")}</dd></div>
      <div><dt>{t("Thời lượng cảnh dùng clip/ảnh trang", "Scenes using recordings/screenshots")}</dt><dd>{Math.round(review.footageRatio * 100)}%</dd></div>
    </dl>
    <p className="field-hint">{t("Các số trên theo dữ liệu bàn giao, chưa phải số đo MP4 cuối. Tỷ lệ clip/ảnh trang là chỉ báo theo khai báo tư liệu, không xác minh thao tác thật.", "These values come from the handoff, not the final MP4. The footage ratio reflects declared media, not verification of recorded interactions.")}</p>
    {(review.footageRatio < .5 || review.consecutiveTextCards) && <p className="content-review-advisory">{t("Gợi ý review", "Review suggestions")}: {review.footageRatio < .5 && t("Thời lượng cảnh dùng clip/ảnh trang dưới 50%. ", "Scenes using recordings/screenshots account for less than 50%. ")}{review.consecutiveTextCards && t("Có hai cảnh chỉ có chữ liên tiếp. ", "Two text-only scenes are adjacent. ")}{t("Đây là gợi ý cải thiện, không phải điều kiện chặn P1.", "These are suggestions, not P1 blocking conditions.")}</p>}
    <ol className="content-review-scenes" aria-label={t("Dàn ý theo cảnh", "Scene outline")}>
      {review.scenes.map(scene => <li key={scene.id} aria-current={scene.id === activeScene ? "step" : undefined}>
        <button type="button" className="content-scene-seek" onClick={() => seek(scene.start)}><strong>{scene.id} · {roleLabels[scene.role]}</strong><span>{scene.start.toFixed(2)}–{scene.end.toFixed(2)}s</span></button>
        <p className="content-scene-meta">{visualLabels[scene.visual]} · {scene.wordCount} {t("từ", "words")}</p>
        <div className="content-scene-copy"><strong>{t("Lời đọc", "Narration")}</strong>{scene.narration.map(segment => <p key={segment.id}><small>{segment.id}</small>{segment.text}</p>)}</div>
        <div className="content-scene-copy"><strong>{t("Chữ trên hình", "On-screen text")}</strong><p>{scene.subtitle}</p></div>
        {!!scene.claims.length && <details><summary>{t("Thông tin sản phẩm và nguồn fact", "Product claims and fact references")}</summary><ul>{scene.claims.map((claim, index) => <li key={index}><p>{claim.text}</p><small>{claim.segmentIds.join(", ")} · {claim.refs.map(ref => `${ref.source_id ? `${ref.source_id} · ` : ""}${ref.field_path}`).join("; ")}</small></li>)}</ul></details>}
      </li>)}
    </ol>
    <p className="field-hint">{t("Nội dung giữ nguyên từ kịch bản M2. Khi sửa lời, cần revision mới cùng audio/timeline tương ứng trước khi dựng lại.", "Content is unchanged from M2. Narration edits require a new revision with matching audio and timing before rendering again.")}</p>
  </details>;
}
