"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ChangeEvent } from "react";
import { Plus, Play, Mic } from "lucide-react";
import { useWorkspace } from "@/features/content-factory/workspace-provider";
import { latestKnowledge } from "@/features/content-factory/model";
import { useStudio } from "./provider";
import { usePreferences } from "./preferences";
import { Modal } from "./common";
import { p1AspectRatios, p1Durations, estimateTokens, normalizeSource, productIsConfirmed, requirementsSnapshot, requirementsAreConfirmed, approveRequirements, videoTemplates, templateForStyle, prepareAutomaticDraft, type Draft, type Request, type ProductReview } from "./model";
import { requestDraft } from "./projects";
import { referenceAccept, saveReferences } from "./references";
import { ReferenceFiles } from "./reference-files";
import { ProjectDetails } from "./project-details";
import { useProductProcessing } from "./product-progress";
import { useAuth } from "@/features/auth/provider";
import { RequirementsReview } from "./requirements-review";

export function CreatorStudio({ projectId, localP1Start }: { projectId?: string; localP1Start?: (draft: Draft) => void }) {
  const { draft, users, requests, ready, commit } = useStudio();
  const { projects } = useWorkspace();
  const { account } = useAuth();
  const processing = useProductProcessing();
  const { t, number, videoView, language } = usePreferences();
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const loadedProject = useRef<string | null>(null);
  const [custom, setCustom] = useState(false);
  const [requirementsOpen, setRequirementsOpen] = useState(false);
  const submitting = useRef(false);
  const [detailError, setDetailError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceLanguage, setVoiceLanguage] = useState("vi");
  const [voiceText, setVoiceText] = useState("");
  const [error, setError] = useState("");
  const [countInput, setCountInput] = useState<string | null>(null);
  const user = users.find(u => u.id === "demo")!;
  const validSource = (() => { try { normalizeSource(draft.sourceUrl); return true; } catch { return false; } })();
  const template = templateForStyle(draft.style);
  const estimate = estimateTokens(draft);
  const enteredCount = Number(countInput ?? draft.count);
  const validCountInput = Number.isSafeInteger(enteredCount) && enteredCount > 0 && Number.isSafeInteger(estimateTokens({ ...draft, count: enteredCount }));
  const activeProjectId = projectId ?? draft.projectId;
  const generations = activeProjectId ? requests.filter(r => (r.projectId ?? r.id) === activeProjectId).slice().reverse() : [];

  useEffect(() => {
    if (!projectId) { loadedProject.current = null; return; }
    if (!ready || loadedProject.current === projectId) return;
    const request = requests.find(r => (r.projectId ?? r.id) === projectId);
    if (request) { loadedProject.current = projectId; if (draft.projectId !== projectId) { try { commit(s => ({ ...s, draft: requestDraft(request) })); } catch { loadedProject.current = null; } } }
  }, [projectId, ready, draft.projectId, requests, commit]);
  useEffect(() => {
    const container = conversationRef.current;
    if (!container) return;
    const latest = container.querySelector(".conversation-turn:last-of-type .assistant-result");
    const top = latest ? latest.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop - 16 : 0;
    container.scrollTo({ top, behavior: "instant" });
  }, [activeProjectId, generations.length]);

  function update(patch: Partial<Draft>) {
    if (patch.sourceUrl !== undefined) processing.cancel();
    try { commit(s => ({ ...s, draft: { ...s.draft, ...patch, preparedUrl: "", requirementsReview: null } })); setError(""); }
    catch { setError(t("Chưa lưu được thay đổi. Hãy tải lại và thử lại.", "Could not save changes. Reload and retry.")); }
  }
  function prepareProduct() {
    try {
      const url = normalizeSource(draft.sourceUrl);
      if (draft.productReview?.sourceUrl === url) return true;
      const product = projects.find(item => normalizeSource(item.url) === url);
      const knowledge = product ? latestKnowledge(product) : null;
      const review: ProductReview = {
        sourceUrl: url, name: product?.name ?? new URL(url).hostname,
        description: knowledge?.data.facts.description.value ?? t("Mô tả mẫu của sản phẩm. Hãy sửa thông tin trước khi xác nhận.", "Sample product description. Edit the information before confirming."),
        features: knowledge?.data.facts.features.value ?? "", pricing: knowledge?.data.pricing.plans.map(plan => plan.priceText).join("\n") ?? "", variant: "",
        sources: knowledge?.sources.map(source => source.url).join("\n") || url, confirmedAt: null,
      };
      commit(state => ({ ...state, draft: { ...state.draft, productReview: review, preparedUrl: "" } }));
      setDetailError("");
      return true;
    } catch { setDetailError(t("Chưa chuẩn bị được thông tin. Kiểm tra link và bộ nhớ trình duyệt, rồi thử lại.", "Could not prepare product information. Check the link and browser storage, then retry.")); return false; }
  }
  function openDetails() {
    if (!validSource) return;
    setDetailError(""); setCustom(true);
    if (!draft.productReview) void processing.start(prepareProduct);
  }
  function closeDetails() { processing.cancel(); setCustom(false); }
  function changeProduct(patch: Partial<ProductReview>) {
    if (!draft.productReview) return;
    update({ productReview: { ...draft.productReview, ...patch, confirmedAt: null }, preparedUrl: "" });
    setDetailError("");
  }
  function confirmProduct() {
    if (!draft.productReview) return false;
    const review = { ...draft.productReview, confirmedAt: new Date().toISOString() };
    if (!productIsConfirmed({ ...draft, productReview: review })) { setDetailError(t("Kiểm tra tên, mô tả và các link nguồn trước khi xác nhận.", "Check the name, description, and source links before confirming.")); return false; }
    try { commit(state => ({ ...state, draft: { ...state.draft, productReview: review, preparedUrl: "" } })); setDetailError(""); setError(""); return true; }
    catch { setDetailError(t("Chưa lưu được xác nhận. Hãy thử lại.", "Could not save confirmation. Please retry.")); return false; }
  }
  function removeReference(id: string) {
    update({ references: draft.references.filter(file => file.id !== id), productReview: draft.productReview ? { ...draft.productReview, confirmedAt: null } : null, preparedUrl: "" });
  }
  function openVoice() {
    setVoiceLanguage(language);
    setVoiceText("");
    setVoiceOpen(true);
  }
  function useVoiceNotes() {
    const text = voiceText.trim();
    if (!text) return;
    update({ notes: [draft.notes.trim(), text].filter(Boolean).join("\n"), preparedUrl: "" });
    setVoiceOpen(false);
  }
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []); event.target.value = "";
    if (!files.length) return;
    setUploading(true); setError("");
    try {
      const saved = await saveReferences(files, draft.references.length, account?.id);
      commit(s => s.draft !== draft ? s : ({ ...s, draft: { ...s.draft, references: [...s.draft.references, ...saved], productReview: s.draft.productReview ? { ...s.draft.productReview, confirmedAt: null } : null, preparedUrl: "" } }));
    } catch (error) {
      const code = error instanceof Error ? error.message : "storage";
      setError(code === "count" ? t("Tối đa 6 tệp tham khảo.", "Attach up to 6 reference files.") : code === "type" ? t("Chọn ảnh PNG/JPG/WebP/GIF hoặc PDF/Word/TXT/MD.", "Choose PNG/JPG/WebP/GIF images or PDF/Word/TXT/MD documents.") : code === "size" ? t("Tệp phải lớn hơn 0 và tối đa 10 MB.", "Files must be non-empty and at most 10 MB.") : t("Chưa lưu được tệp tham khảo. Hãy thử lại.", "Could not save reference files. Please retry."));
    } finally { setUploading(false); }
  }
  function generate(event: FormEvent) {
    event.preventDefault();
    if (!validSource) { setError(t("Nhập link HTTP/HTTPS hợp lệ trước khi tạo video mẫu.", "Enter a valid HTTP/HTTPS link before creating a sample video.")); return; }
    if (localP1Start) { localP1Start({ ...draft, sourceUrl: normalizeSource(draft.sourceUrl) }); return; }
    if (!productIsConfirmed(draft)) { openDetails(); setDetailError(t("Kiểm tra và xác nhận thông tin sản phẩm trước khi tạo video mẫu.", "Review and confirm product information before creating a sample video.")); return; }
    submitting.current = false; setError(""); setRequirementsOpen(true);
  }
  function createSample() {
    if (submitting.current) return;
    submitting.current = true;
    let next: Draft;
    try {
      next = prepareAutomaticDraft(approveRequirements(draft, new Date().toISOString()));
      const reviewedSnapshot = requirementsSnapshot(next);
      const id = next.projectId ?? crypto.randomUUID();
      commit(s => {
        if (!productIsConfirmed(s.draft) || requirementsSnapshot(s.draft) !== reviewedSnapshot) throw new Error("stale-review");
        const currentUser = s.users.find(u => u.id === "demo")!;
        if (!currentUser.active || currentUser.tokens < estimate) throw new Error("balance");
        const now = new Date().toISOString();
        const request: Request = { ...next, projectId: id, id: crypto.randomUUID(), status: "completed", createdAt: now, estimatedTokens: estimate };
        return { ...s, draft: requestDraft(request), requests: [request, ...s.requests], users: s.users.map(u => u.id === "demo" ? { ...u, tokens: u.tokens - estimate } : u), transactions: [{ id: crypto.randomUUID(), userId: "demo", amount: -estimate, reason: `Video demo · ${request.id.slice(0, 8)}`, createdAt: now }, ...s.transactions] };
      });
      setRequirementsOpen(false); setError(""); router.push(`/creator/project/${id}`);
    } catch { submitting.current = false; setError(t("Chưa tạo được video mẫu. Kiểm tra lại yêu cầu, số dư hoặc tải lại trang.", "Could not create the sample. Review the requirements and balance, or reload.")); }
  }
  if (projectId && ready && !generations.length) return <div className="studio-empty"><p>{t("Không tìm thấy dự án.", "Project not found.")}</p><button type="button" className="secondary-button" onClick={() => router.push("/creator/create")}>{t("Về workspace", "Back to workspace")}</button></div>;

  return <div className={`chat-workspace ${!generations.length ? "chat-start" : ""}`}>
    <div className="chat-conversation" ref={conversationRef} aria-label={t("Nội dung dự án", "Project conversation")}>
      <div className="conversation-content">
        {!generations.length && <div className="chat-empty"><p>{t("Biến đường link thành video.", "Turn a link into a video.")}</p><span>{localP1Start ? t("Dán link và chọn cấu hình nhanh; mô tả sản phẩm ở bước tiếp theo.", "Paste a link and choose settings; describe the product in the next step.") : t("Dán link và mô tả video bạn muốn tạo.", "Paste a link and describe the video you want.")}</span><button type="button" className="text-button sample-link-button" onClick={() => update({ sourceUrl: "https://aisoeasy.com", productReview: null, notes: t("Giới thiệu AISoEasy cho nhân viên văn phòng, tập trung việc học AI để ứng dụng trong công việc, giọng thân thiện và dễ hiểu.", "Introduce AISoEasy to office workers, focusing on learning AI for work, with a friendly, clear tone."), preparedUrl: "" })}>{t("Thử với AISoEasy", "Try AISoEasy")} <span aria-hidden="true">↗</span></button></div>}
        {generations.map(request => <section className="conversation-turn" key={request.id}>
          <div className="user-message"><a href={request.sourceUrl} target="_blank" rel="noreferrer">{request.sourceUrl}</a>{request.notes && <p>{request.notes}</p>}<ReferenceFiles files={request.references} /></div>
          <div className={`assistant-result video-view-${videoView}`}>
            <div className="result-heading"><h2>{t("Video minh họa có sẵn", "Existing sample video")}</h2><span className="sample-preview-tag">{t("Bản xem thử", "Preview")}</span></div>
            <div className="result-meta"><span>{t("Yêu cầu", "Requested")}: {request.duration} {t("giây", "seconds")} · {request.ratio} · {request.resolution}</span><span>{number(request.estimatedTokens)} {t("token mẫu", "sample tokens")}</span></div>
            <p className="sample-video-notice">{t("Clip minh họa 15 giây có sẵn, chưa được tạo từ link và mô tả bạn vừa nhập.", "This existing 15-second sample clip was not generated from the link and description you entered.")}</p>
            <div className="result-videos">{Array.from({ length: request.count }, (_, index) => <article className="output-card" key={index}>
              <div className="output-card-heading"><strong>VIDEO {String(index + 1).padStart(2, "0")}</strong><span>MP4</span></div>
              <div className="output-player"><video controls playsInline preload="metadata" src="/media/leader-demo.mp4" poster="/media/sample-poster.jpg" style={{ aspectRatio: request.ratio.replace(":", " / ") }} aria-label={`${t("Video mẫu", "Sample video")} ${index + 1}`} /></div>
              <div className="output-card-footer"><span>{t("Clip minh họa", "Sample clip")} · 15s</span><a href="/media/leader-demo.mp4" download={`reviewlab-sample-${index + 1}.mp4`}>{t("Tải clip mẫu", "Download sample")} <span aria-hidden="true">↓</span></a></div>
            </article>)}</div>
            <div className="result-actions"><details className="result-prompt"><summary>{t("Xem yêu cầu & cấu hình", "View requirements & settings")}</summary><strong>{t("Mô tả / mong muốn về video", "Video description / preferences")}</strong><p>{request.notes || t("Chưa thêm mô tả.", "No description added.")}</p><p>{requirementsAreConfirmed(request) ? t("Yêu cầu đã xác nhận cho lần xem mẫu này.", "Requirements confirmed for this sample.") : t("Lịch sử cũ chưa có xác nhận yêu cầu.", "This older entry has no requirements approval.")}</p><details><summary>{t("Chi tiết kỹ thuật", "Technical details")}</summary><p>{request.prompt}</p><p>{request.opening}</p></details></details><button type="button" className="text-button" onClick={() => update(requestDraft(request))}>{t("Dùng lại", "Reuse")}</button></div>
          </div>
        </section>)}
      </div>
    </div>
    <div className="chat-dock">
      <form ref={formRef} onSubmit={generate} className={`chat-composer ${localP1Start ? "local-p1-quick-intake" : ""}`} aria-label={t("Tạo video", "Create video")}>
        <fieldset disabled={!ready || uploading}>
          <div className="composer-top-strip">
            <label className="composer-strip-control"><span>{t("Khung hình", "Frame")}</span><select aria-label={t("Tỷ lệ khung hình", "Aspect ratio")} value={draft.ratio} onChange={e => update({ ratio: e.target.value as Draft["ratio"] })}>{p1AspectRatios.map(ratio => <option key={ratio} value={ratio}>{ratio}</option>)}</select></label>
            <span className="composer-strip-cost" aria-live="polite" title={t("Token dự kiến (mẫu)", "Estimated tokens (sample)")}>{number(estimate)} <span>token</span></span>
          </div>
          <div className="composer-input-surface">
          <div className="chat-input-area">
            <label className="sr-only" htmlFor="source-url">{t("Link sản phẩm (bắt buộc)", "Product link (required)")}</label><input id="source-url" type="text" inputMode="url" value={draft.sourceUrl} onChange={e => update({ sourceUrl: e.target.value, productReview: null, preparedUrl: "" })} placeholder={t("Dán link sản phẩm · bắt buộc", "Paste a product link · required")} required />
            {!localP1Start && <><label className="composer-description-label" htmlFor="video-description">{t("Mô tả / mong muốn về video", "Video description / preferences")}</label>
            <textarea id="video-description" aria-describedby="video-description-hint" maxLength={2000} value={draft.notes} onChange={e => update({ notes: e.target.value, preparedUrl: "" })} placeholder={t("Video dành cho ai? Bạn muốn nhấn mạnh điều gì, giọng điệu ra sao?", "Who is it for? What should it focus on, and what tone should it use?")} rows={2} onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); formRef.current?.requestSubmit(); } }} />
            <p id="video-description-hint" className="field-hint">{t("Không cần viết sẵn kịch bản. Thông tin sản phẩm sẽ được kiểm tra ở bước xác nhận.", "No script needed. Product information is checked during review.")}</p>
            <ReferenceFiles files={draft.references} remove={removeReference} /></>}
          </div>
          <div className="compact-composer-actions">
            <div className="attachment-action"><button type="button" className="attach-button" aria-label={t("Thêm ảnh hoặc tài liệu tham khảo", "Add reference images or documents")} title={t("Thêm ảnh hoặc tài liệu tham khảo", "Add reference images or documents")} onClick={() => uploadRef.current?.click()}><Plus size={21} /></button><input ref={uploadRef} className="file-upload-input" type="file" aria-label={t("Tệp tham khảo", "Reference files")} accept={referenceAccept} multiple onChange={upload} /><button type="button" className="composer-custom-button" disabled={!validSource} title={validSource ? t("Xem thông tin sản phẩm và cấu hình", "Review product information and configuration") : t("Nhập link sản phẩm hợp lệ để mở Chi tiết", "Enter a valid product link to open Details")} onClick={openDetails}>{t("Chi tiết", "Details")} ↗</button>{uploading && <small role="status">{t("Đang thêm tệp…", "Adding files…")}</small>}</div>
            <div className="compact-build-controls">
              <span className="composer-auto-badge" title={t("AI sẽ tự chọn cách dựng phù hợp. Hiện đang là bản mẫu giao diện.", "AI will choose a suitable production approach. This is currently a UI demo.")}>{t("AI tự chọn", "AI auto")}</span>
              <button type="button" className="composer-mic-button" aria-label={t("Nhập bằng giọng nói", "Voice input")} title={t("Nhập bằng giọng nói", "Voice input")} aria-haspopup="dialog" onClick={openVoice}><Mic size={18} /></button>
              <button type="submit" className="compact-send-button" aria-label={t("Tạo video", "Create video")} title={localP1Start ? t("Vào luồng P1", "Open P1 flow") : `${t("Tạo video", "Create video")} · ${number(estimate)} token`} disabled={!validSource || (!localP1Start && (!validCountInput || estimate > user.tokens || !user.active))}><Play size={13} fill="currentColor" /><span>{t("Tạo", "Create")}</span></button>
            </div>
          </div>
          </div>
          <div className="composer-bottom-strip">
            <label className="composer-strip-control composer-count-control"><span>{t("Số lượng", "Count")}</span><input type="number" inputMode="numeric" min={1} step={1} required aria-label={t("Số lượng", "Video count")} value={countInput ?? draft.count} onFocus={() => setCountInput(String(draft.count))} onBlur={() => setCountInput(null)} onChange={e => { const text = e.target.value; const count = Number(text); setCountInput(text); if (Number.isSafeInteger(count) && count > 0 && Number.isSafeInteger(estimateTokens({ ...draft, count }))) update({ count }); }} /><span>video</span></label>
            <label className="composer-strip-control"><span>Template</span><select aria-label="Template" value={template.id} onChange={e => update({ style: e.target.value as Draft["style"] })}>{videoTemplates.map(item => <option key={item.id} value={item.id}>{t(item.vi, item.en)}</option>)}</select></label>
            <label className="composer-strip-control"><span>{t("Thời gian", "Duration")}</span><select aria-label={t("Thời gian", "Duration")} value={draft.duration} onChange={e => update({ duration: Number(e.target.value) })}>{p1Durations.map(n => <option key={n} value={n}>{n}s</option>)}</select></label>
          </div>
        </fieldset>
      </form>
      {error && <p role="alert" className="studio-error">{error}</p>}
      {estimate > user.tokens && <p className="studio-error">{t("Không đủ token mẫu. Giảm số lượng hoặc độ dài.", "Insufficient sample tokens. Reduce the count or duration.")}</p>}
      {!user.active && <p className="studio-error">{t("Tài khoản mẫu đang tạm dừng.", "The demo account is paused.")}</p>}
    </div>
    {requirementsOpen && draft.productReview && <Modal title={t("Duyệt yêu cầu video", "Review video requirements")} close={() => { setRequirementsOpen(false); setError(""); }}><RequirementsReview draft={draft} busy={uploading} error={error} changeDescription={notes => update({ notes })} confirm={createSample} /></Modal>}
    {voiceOpen && <Modal title={t("Nhập bằng giọng nói", "Voice input")} close={() => setVoiceOpen(false)}>
      <div className="editor-form">
        <p className="voice-demo-hint">{t("Bản mô phỏng: dùng đoạn nói mẫu để thử thêm ghi chú.", "Demo: use a sample transcript to try adding voice notes.")}</p>
        <label>{t("Ngôn ngữ nói", "Spoken language")}<select aria-label={t("Ngôn ngữ nói", "Spoken language")} value={voiceLanguage} onChange={e => { setVoiceLanguage(e.target.value); setVoiceText(""); }}><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label>
        <button type="button" className="voice-sample-button" onClick={() => setVoiceText(voiceLanguage === "vi" ? "Tạo video giới thiệu sản phẩm với nhịp nhanh, ánh sáng tự nhiên và kết thúc bằng lời mời tìm hiểu thêm." : "Create a product introduction with a brisk pace, natural lighting, and an invitation to learn more at the end.")}><Mic size={18} /><span>{t("Thử đoạn nói mẫu", "Try a sample transcript")}</span></button>
        <label>{t("Nội dung nhận được", "Transcript")}<textarea aria-label={t("Nội dung nhận được", "Transcript")} rows={3} value={voiceText} onChange={e => setVoiceText(e.target.value)} placeholder={t("Nội dung sẽ được thêm vào ghi chú…", "This text will be added to your notes…")} /></label>
        <div className="dialog-actions"><button type="button" className="primary-button" disabled={!voiceText.trim()} onClick={useVoiceNotes}>{t("Thêm vào ghi chú", "Add to notes")}</button></div>
      </div>
    </Modal>}
    {custom && <Modal title={t("Chi tiết dự án", "Project details")} close={closeDetails}><ProjectDetails review={draft.productReview} confirmed={productIsConfirmed(draft)} files={draft.references} error={detailError} phase={processing.phase} prepare={() => { setDetailError(""); void processing.start(prepareProduct); }} change={changeProduct} confirm={confirmProduct} removeFile={removeReference}>
      <div className="editor-form">
        <div className="automatic-design-summary">
          <strong>{t("AI phụ trách thiết kế", "AI handles the design")}</strong>
          <p>{t("Phong cách đã chọn", "Selected style")}: {t(template.vi, template.en)}</p>
          <ul>
            <li>{t("Màu và kiểu chữ theo nhận diện sản phẩm từ link và tư liệu.", "Colors and typography based on the product link and references.")}</li>
            <li>{t("Bố cục từng cảnh, tư liệu minh họa và khung mở đầu theo nội dung.", "Scene layouts, supporting media and opening frame based on the content.")}</li>
            <li>{t("Chuyển động, máy quay và nhịp dựng theo template.", "Motion, camera and pacing based on the template.")}</li>
          </ul>
          <p className="field-hint">{t("Bản mẫu chưa phân tích màu hoặc tự dựng video. Bạn không cần nhập prompt hay chọn màu thủ công.", "This demo does not analyze colors or generate videos yet. You do not need to write prompts or choose colors manually.")}</p>
        </div>
        <div className="config-grid">
          <label>{t("Độ phân giải", "Resolution")}<select aria-label={t("Độ phân giải", "Resolution")} value={draft.resolution} onChange={e => update({ resolution: e.target.value as Draft["resolution"] })}><option>1080p</option><option>720p</option></select></label>
          <label>{t("Ngôn ngữ video", "Video language")}<select aria-label={t("Ngôn ngữ video", "Video language")} value={draft.outputLanguage} onChange={e => update({ outputLanguage: e.target.value as Draft["outputLanguage"] })}><option value="vi">Tiếng Việt</option><option value="en">English</option></select></label>
        </div>
        <div className="dialog-actions"><button type="button" className="primary-button" onClick={closeDetails}>{t("Xong", "Done")}</button></div>
      </div>
    </ProjectDetails></Modal>}
  </div>;
}
