"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { usePreferences } from "@/features/studio/preferences";
import { fromM2, sceneAt, type Project, type Ratio } from "./model";
import { buildFrame, loadResources, readMedia, type Resources } from "./frame";
import { sample } from "./sample";
import { loadS03Handoff } from "./load-handoff";
import { ContentReviewPanel } from "./content-review-panel";

type Status = { sceneId: string; mediaReady: boolean; missingMedia: boolean; textOverflow: string[]; document: string; time: number };
function download(value: string, name: string, type: string) { const url = URL.createObjectURL(new Blob([value], { type })); const link = document.createElement("a"); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
export function VideoTemplatePreview({ ratio, preset, close, handoff = false, initialProject, initialMedia }: { ratio: Ratio; preset: string; close: () => void; handoff?: boolean; initialProject?: Project; initialMedia?: Record<string, string> }) {
  const { t } = usePreferences();
  const [project, setProject] = useState<Project>(initialProject ?? sample);
  const [resources, setResources] = useState<Resources | null>(null);
  const [media, setMedia] = useState<Record<string, string>>(initialMedia ?? {});
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [frameVersion, setFrameVersion] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const uploadGeneration = useRef(0);
  const mediaBindings = useRef<Record<string, string>>(initialMedia ?? {});
  const seekRequest = useRef(0);
  const total = project.scenes.reduce((s, scene) => s + scene.duration, 0);
  const { index, scene, localTime } = sceneAt(project, time);
  const document = useMemo(() => resources ? buildFrame(project, scene, ratio, preset, media, resources) : "", [resources, project, scene, ratio, preset, media]);
  const currentStatus = status?.document === document && status.sceneId === scene.id ? status : null;
  const exportReady = currentStatus?.time === localTime && currentStatus.mediaReady && !currentStatus.textOverflow.length;

  useEffect(() => { let alive = true; void loadResources().then(value => { if (alive) setResources(value); }).catch(error => { if (alive) setError(String(error.message)); }); return () => { alive = false; }; }, []);
  useEffect(() => {
    if (!handoff || initialProject) return;
    let alive = true;
    void loadS03Handoff().then(({ project, media }) => { if (alive) { mediaBindings.current = media; setProject(project); setMedia(media); setFrameVersion(v => v + 1); setTime(0); setStatus(null); setError(""); } }).catch(error => { if (alive) setError(error instanceof Error ? error.message : "Không nạp được s03."); });
    return () => { alive = false; };
  }, [handoff, initialProject]);
  useEffect(() => { frame.current?.contentWindow?.postMessage({ type: "creator-template-seek", time: localTime, requestId: ++seekRequest.current }, "*"); }, [localTime, document]);
  useEffect(() => {
    function message(event: MessageEvent) { if (event.source === frame.current?.contentWindow && event.data?.type === "creator-template-status" && event.data.requestId === seekRequest.current && typeof event.data.mediaReady === "boolean" && Array.isArray(event.data.textOverflow)) setStatus({ ...event.data, document }); }
    window.addEventListener("message", message); return () => window.removeEventListener("message", message);
  }, [document]);
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const id = setInterval(() => { const now = performance.now(); const delta = (now - last) / 1000; last = now; setTime(previous => Math.min(total - .001, previous + delta)); }, 1000 / 30);
    return () => clearInterval(id);
  }, [playing, total]);
  function selectProject(value: Project) { uploadGeneration.current++; mediaBindings.current = {}; setProject(value); setMedia({}); setFrameVersion(v => v + 1); setTime(0); setPlaying(false); setStatus(null); setError(""); }
  async function importJson(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    try { if (!file.size || file.size > 1024 * 1024) throw new Error("Gói JSON phải lớn hơn 0 và tối đa 1 MB."); const value: unknown = JSON.parse(await file.text()); selectProject(fromM2(value)); }
    catch (error) { setError(error instanceof Error ? error.message : "JSON không hợp lệ."); }
  }
  async function bindFile(event: ChangeEvent<HTMLInputElement>, id: string, kind: string) {
    const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
    const generation = uploadGeneration.current;
    try { const value = await readMedia(file, kind); if (generation !== uploadGeneration.current) return; const next = { ...mediaBindings.current, [id]: value }; if (Object.values(next).reduce((n, value) => n + value.length, 0) > 70 * 1024 * 1024) throw new Error(t("Tổng tư liệu vượt 50 MB.", "Total media exceeds 50 MB.")); mediaBindings.current = next; setMedia(next); setFrameVersion(v => v + 1); setStatus(null); setError(""); }
    catch (error) { setError(error instanceof Error ? error.message : "Không đọc được tệp."); }
  }
  function togglePlay() { if (time >= total - .01) { setTime(0); setPlaying(true); } else setPlaying(!playing); }
  function exportHtml() { try { if (!resources || !exportReady) throw new Error(t("Cảnh chưa sẵn sàng: kiểm tra tư liệu và chữ tràn trước khi xuất.", "Scene not ready: check media and text overflow before export.")); download(document, `${scene.id}-${ratio.replace(":", "x")}.html`, "text/html"); } catch (error) { setError(error instanceof Error ? error.message : "Không xuất được HTML."); } }
  return <section className="creator-template-preview" aria-label={t("Preview dữ liệu AI bàn giao", "AI handoff preview")}>
    <div className="template-preview-heading"><strong>{project.title} · {ratio === "9:16" ? t("Bản dọc · 9:16", "Portrait · 9:16") : t("Bản ngang · 16:9", "Landscape · 16:9")}</strong><button type="button" className="text-button" onClick={close}>{t("Đóng preview", "Close preview")}</button></div>
    <div className="template-preview-toolbar">
      <span>{ratio} · {preset} · {total.toFixed(2)}s</span>
    </div>
    <div className={`template-preview-stage ${ratio === "9:16" ? "portrait" : "landscape"}`}>
      {document ? <iframe key={`${frameVersion}:${scene.id}:${ratio}:${preset}`} ref={frame} title={t("Khung hình template", "Template frame")} sandbox="allow-scripts" srcDoc={document} onLoad={() => frame.current?.contentWindow?.postMessage({ type: "creator-template-seek", time: localTime, requestId: ++seekRequest.current }, "*")} /> : <p role="status">{t("Đang mở template…", "Loading template…")}</p>}
    </div>
    <div className="template-timeline"><button type="button" className="secondary-button" disabled={!resources} onClick={togglePlay}>{playing && time < total - .01 ? t("Dừng", "Pause") : t("Phát hình", "Play visuals")}</button><input type="range" aria-label={t("Timeline preview", "Preview timeline")} min={0} max={Math.max(0, total - .001)} step={1 / 30} value={time} onChange={event => { setPlaying(false); setTime(Number(event.target.value)); }} /><output>{time.toFixed(2)} / {total.toFixed(2)}s</output></div>
    <div className="template-scene-list" aria-label={t("Các cảnh", "Scenes")}>{project.scenes.map((item, i) => <button key={item.id} type="button" aria-pressed={index === i} onClick={() => { setTime(project.scenes.slice(0, i).reduce((s, item) => s + item.duration, 0)); setPlaying(false); setStatus(null); }}>{item.id} · {item.layout}</button>)}</div>
    <p className="field-hint" role="status">{t("Preview chỉ hình, không phát audio/karaoke.", "Visual preview only, without audio or karaoke.")} {currentStatus?.missingMedia && t("Đang thiếu tư liệu; không thay bằng clip sản phẩm khác.", "Media is missing; another product's footage is not substituted.")} {!!currentStatus?.textOverflow.length && t("Có chữ tràn; cần review bố cục.", "Text overflows; layout review is required.")}</p>
    {(total < 40 || total > 45) && <p className="field-hint">{t("Timeline này nằm ngoài 40–45 giây; chỉ dùng review cảnh, chưa đạt thời lượng video P1.", "This timeline is outside 40–45 seconds; use it for scene review, not P1 duration acceptance.")}</p>}
    <ContentReviewPanel project={project} activeScene={scene.id} seek={time => { setTime(time); setPlaying(false); setStatus(null); }} />
    <details className="template-handoff-details"><summary>{t("Kiểm tra bàn giao và tư liệu", "Review handoff and media")}</summary>
      <p className="template-preview-provenance"><strong>{project.title}</strong> · {project.sourceUrl}<br />{project.source}<br />{project.timing === "fixture" ? t("Timeline giả để kiểm tra bố cục; không phải timing giọng thật.", "Synthetic layout timing; not real voice timing.") : t("Timeline do bên bàn giao đánh dấu đo thật; cần kiểm audio tương ứng.", "Timeline is marked measured by the sender; matching audio still needs verification.")}</p>
      <p>{t("Chỉ dùng để kiểm tra FE–AI; người dùng tạo video không phải chỉnh màu hay ghép tư liệu thủ công.", "For FE–AI review; creators do not need to manually set colors or assemble media.")}</p>
      {project.knowledgeVersion && <p>Product {project.productId} · PKB {project.pkbSchemaVersion} · knowledge {project.knowledgeVersion}</p>}
      <p>{scene.handoffRefs ? "Bằng chứng trong gói bàn giao" : "Fact refs"}: {JSON.stringify(scene.handoffRefs ?? scene.refs)}</p>
      <label>{t("Nạp gói M2 + presentation (JSON)", "Load M2 + presentation package (JSON)")}<input type="file" accept="application/json,.json" aria-label={t("Nạp gói M2", "Load M2 package")} onChange={importJson} /></label>
      <div className="template-export-actions"><button type="button" className="secondary-button" onClick={() => selectProject(sample)}>{t("Về mẫu bốn layout", "Reset four-layout sample")}</button><button type="button" className="secondary-button" disabled={!resources || !exportReady || playing && time < total - .01} onClick={exportHtml}>{t("Xuất HTML cảnh", "Export scene HTML")}</button></div>
      {project.assets.map(asset => <label className="template-asset" key={asset.id}><span>{asset.id} · {asset.kind}{media[asset.id] ? " ✓" : ""}<small>{asset.rights}</small></span><input aria-label={`Asset ${asset.id}`} type="file" accept={asset.kind === "video" ? "video/mp4,video/webm" : asset.kind === "image" ? "image/png,image/jpeg,image/webp" : "audio/wav,audio/mpeg,audio/mp4,audio/ogg,audio/webm"} onChange={event => { void bindFile(event, asset.id, asset.kind); }} /></label>)}
    </details>
    {<p className="field-hint">{t("Bốn layout và ba phong cách là bản FE thử, chờ Vũ review thiết kế.", "These layouts and styles are FE drafts pending Vu's design review.")}</p>}
    {error && <p role="alert" className="studio-error">{error}</p>}
  </section>;
}
