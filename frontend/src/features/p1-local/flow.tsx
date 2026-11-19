"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import Image from "next/image";
import "./local-p1.css";
import { P1_OPEN_EVENT, P1_PENDING_OPEN_KEY, P1_SESSIONS_EVENT, P1_SESSION_HISTORY_KEY, P1_SESSION_KEY, readP1Sessions, type P1Session } from "./sessions";

type Json = Record<string, unknown>;
type Stage = "intake" | "crawl" | "pkb" | "script" | "production" | "done";
type SceneDraft = { id: string; headline: string; subtitle: string; assetId: string; motion: string };
type VideoPreferences = { template: string; ratio: string; resolution: string; transition: string };
type Session = P1Session;

const STORAGE_KEY = P1_SESSION_KEY;
const SESSION_HISTORY_KEY = P1_SESSION_HISTORY_KEY;
const VIDEO_PREFS_KEY = "reviewlab.p1-local.video-preferences.v1";
const INTAKE_KEY = "reviewlab.p1-local.intake.v1";
const DEFAULT_VIDEO_PREFS: VideoPreferences = {
  template: "reels-aurora",
  ratio: "9:16",
  resolution: "1080p",
  transition: "fade",
};
const TEMPLATE_CATALOG = [
  { id: "short-countdown", name: "Short đếm ngược", use: "Khung demo, màu mạnh, chữ bật theo lời đọc", badge: "SHORT" },
  { id: "reels-aurora", name: "Aurora Hero", use: "Hook hiện đại, sản phẩm AI/SaaS", badge: "HOOK" },
  { id: "reels-editorial", name: "Editorial Bold", use: "Thông điệp mạnh, thương hiệu và con số", badge: "BOLD" },
  { id: "reels-neon", name: "Neon Stat", use: "Benchmark, tính năng công nghệ", badge: "STAT" },
  { id: "reels-comparison", name: "Comparison", use: "Trước/sau, cũ/mới, lợi ích", badge: "VS" },
  { id: "review-pro", name: "Review Pro", use: "Clip thao tác trong khung macOS", badge: "DEMO" },
  { id: "cinematic", name: "Cinematic", use: "Hình ảnh điện ảnh, tương phản", badge: "FILM" },
  { id: "animation", name: "Animation", use: "Khung sản phẩm macOS, chữ nhấn và icon chuyển động", badge: "POP" },
  { id: "vintage", name: "Vintage", use: "Phong cách hoài cổ", badge: "RETRO" },
] as const;
const stages: Array<[Stage, string]> = [
  ["intake", "Cung cấp sản phẩm"],
  ["crawl", "Khám phá sản phẩm"],
  ["pkb", "Duyệt PKB"],
  ["script", "Duyệt concept & kịch bản"],
  ["production", "Dựng video & QA"],
  ["done", "Tải MP4"],
];

const P1_DURATION_INSTRUCTION =
  "Độ dài lời đọc phải phù hợp lượng thông tin sản phẩm đã xác minh, khoảng 80–150 từ tiếng Việt và tuyệt đối để TTS/video hoàn chỉnh dưới 60 giây. Không kéo dài cho đủ thời gian, ưu tiên đủ ý, câu ngắn, không lặp và không thêm claim ngoài PKB.";
const P1_DURATION_REVISION_FEEDBACK =
  "Rút lời đọc vừa đủ giới thiệu sản phẩm và bảo đảm TTS/video hoàn chỉnh dưới 60 giây. Giữ đủ ý chính, claim có nguồn và tối thiểu hai tư liệu sản phẩm; bỏ câu lặp hoặc từ đệm.";
const VIDEO_DESCRIPTION_LIMIT = 1900;

function record(value: unknown): Json {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Json : {};
}

function list(value: unknown): Json[] {
  return Array.isArray(value) ? value.map(record) : [];
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function factValue(value: unknown): string {
  if (typeof value === "string") return value;
  const item = record(value);
  return text(item.value);
}

function suggestedProductDescription(data: Json): string {
  const identity = record(data.identity);
  const productName = factValue(identity.name) || "Sản phẩm";
  const featureSummaries = list(data.features).map(feature => (
    text(feature.description) || text(feature.name)
  )).map(value => value.trim()).filter(Boolean).slice(0, 3);
  if (!featureSummaries.length) return "";
  const joined = featureSummaries.join(" ").replace(/\s+/gu, " ").trim();
  return `${productName} cung cấp ${joined.charAt(0).toLocaleLowerCase("vi")}${joined.slice(1)}`.slice(0, 900);
}

function isVideoAsset(asset: Json | undefined): boolean {
  return text(asset?.kind) === "screen_recording" || /\.(webm|mp4|mov)$/iu.test(text(asset?.path));
}

function narrationWordCount(script: Json): number {
  return list(record(script.content).scenes).reduce((total, scene) => (
    total + list(scene.narration_segments).reduce((sceneTotal, segment) => (
      sceneTotal + text(segment.text).trim().split(/\s+/u).filter(Boolean).length
    ), 0)
  ), 0);
}

function boundedVideoDescription(parts: string[]): string {
  const normalized = parts.filter(Boolean).join("\n").replace(/\s+/gu, " ").trim();
  if (normalized.length <= VIDEO_DESCRIPTION_LIMIT) return normalized;
  const clipped = normalized.slice(0, VIDEO_DESCRIPTION_LIMIT - 1);
  const boundary = Math.max(clipped.lastIndexOf(". "), clipped.lastIndexOf("; "), clipped.lastIndexOf(" "));
  return `${clipped.slice(0, boundary > 1200 ? boundary : clipped.length).trim()}…`;
}

function scriptIntent(goal: string): string {
  if (goal === "education") return "education";
  if (goal === "sales") return "conversion";
  if (goal === "traffic" || goal === "follow") return "consideration";
  return "awareness";
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Có lỗi không xác định.";
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/p1/${path}`, {
    ...init,
    cache: "no-store",
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(text(record(body).detail, `Yêu cầu thất bại (${response.status}).`));
  }
  return response.json() as Promise<T>;
}

async function post<T>(path: string, body: Json): Promise<T> {
  return api<T>(path, { method: "POST", body: JSON.stringify(body) });
}

async function waitForJob(jobId: string, onTick: (job: Json) => void): Promise<Json> {
  for (let attempt = 0; attempt < 900; attempt += 1) {
    const job = await api<Json>(`jobs/${jobId}`);
    onTick(job);
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(text(job.error, "Tác vụ thất bại."));
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  throw new Error("Tác vụ chạy quá 30 phút. Có thể mở lại trang để tiếp tục theo dõi.");
}

function idempotency(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

export function LocalP1Flow({ onReset }: { onReset?: () => void }) {
  const [stage, setStage] = useState<Stage>("intake");
  const [session, setSession] = useState<Session>({});
  const sessionRef = useRef<Session>({});
  const [savedSessions, setSavedSessions] = useState<Session[]>([]);
  const [url, setUrl] = useState("");
  const [ownerContext, setOwnerContext] = useState("");
  const [preferences, setPreferences] = useState("");
  const [audience, setAudience] = useState("");
  const [videoGoal, setVideoGoal] = useState("brand");
  const [manualLogin, setManualLogin] = useState(false);
  const [discoveryMode, setDiscoveryMode] = useState<"public" | "authenticated">("public");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [crawlJob, setCrawlJob] = useState<Json | null>(null);
  const [pkb, setPkb] = useState<Json | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [descriptionSuggested, setDescriptionSuggested] = useState(false);
  const [script, setScript] = useState<Json | null>(null);
  const [feedback, setFeedback] = useState("");
  const [template, setTemplate] = useState(DEFAULT_VIDEO_PREFS.template);
  const [ratio, setRatio] = useState(DEFAULT_VIDEO_PREFS.ratio);
  const [resolution, setResolution] = useState(DEFAULT_VIDEO_PREFS.resolution);
  const [transition, setTransition] = useState(DEFAULT_VIDEO_PREFS.transition);
  const [requestedDuration, setRequestedDuration] = useState(42);
  const [entryUrl, setEntryUrl] = useState(false);
  const [sceneDrafts, setSceneDrafts] = useState<SceneDraft[]>([]);
  const [videoJob, setVideoJob] = useState<Json | null>(null);

  useEffect(() => {
    queueMicrotask(() => {
      try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Session;
        const history = JSON.parse(localStorage.getItem(SESSION_HISTORY_KEY) ?? "[]") as Session[];
        const validHistory = Array.isArray(history) ? history.filter(item => Boolean(item.productId)) : [];
        const sessions = saved.productId
          ? [saved, ...validHistory.filter(item => item.productId !== saved.productId)]
          : validHistory;
        setSavedSessions(sessions);
        if (sessions.length) localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(sessions));
        window.dispatchEvent(new Event(P1_SESSIONS_EVENT));
        sessionRef.current = saved;
        setSession(saved);
        setUrl(saved.url ?? "");
        if (!saved.productId) {
          const intake = JSON.parse(localStorage.getItem(INTAKE_KEY) ?? "null") as { url?: string; template?: string; ratio?: string; resolution?: string; duration?: number } | null;
          if (intake?.url) {
            setUrl(intake.url);
            setEntryUrl(true);
            setRequestedDuration(intake.duration || 42);
            localStorage.setItem(VIDEO_PREFS_KEY, JSON.stringify({ template: intake.template || DEFAULT_VIDEO_PREFS.template, ratio: intake.ratio || DEFAULT_VIDEO_PREFS.ratio, resolution: intake.resolution || DEFAULT_VIDEO_PREFS.resolution, transition: DEFAULT_VIDEO_PREFS.transition }));
          }
        }
        setOwnerContext(saved.ownerContext ?? "");
        setPreferences(saved.preferences ?? "");
        setAudience(saved.audience ?? "");
        setVideoGoal(saved.videoGoal ?? "brand");
        setManualLogin(saved.manualLogin ?? false);
        setDiscoveryMode(saved.discoveryMode ?? (saved.manualLogin ? "authenticated" : "public"));
        setFeedback(saved.revisionFeedback ?? "");
        const videoPreferences = JSON.parse(
          localStorage.getItem(VIDEO_PREFS_KEY) ?? JSON.stringify(DEFAULT_VIDEO_PREFS),
        ) as VideoPreferences;
        setTemplate(videoPreferences.template || DEFAULT_VIDEO_PREFS.template);
        setRatio(videoPreferences.ratio || DEFAULT_VIDEO_PREFS.ratio);
        setResolution(videoPreferences.resolution || DEFAULT_VIDEO_PREFS.resolution);
        setTransition(videoPreferences.transition || DEFAULT_VIDEO_PREFS.transition);
        if (saved.videoJobId || saved.scriptApproved) setStage("production");
        else if (saved.scriptRevision) setStage("script");
        else if (saved.pkbVersion) setStage("pkb");
        else if (saved.crawlJobId || saved.loginRequired) setStage("crawl");
        const pendingId = localStorage.getItem(P1_PENDING_OPEN_KEY);
        if (pendingId) {
          const target = sessions.find(item => item.productId === pendingId) ?? readP1Sessions(localStorage).find(item => item.productId === pendingId);
          localStorage.removeItem(P1_PENDING_OPEN_KEY);
          if (target) openSavedProject(target);
        }
      } catch { localStorage.removeItem(STORAGE_KEY); }
    });
  }, []);

  useEffect(() => {
    const handleOpen = (event: Event) => {
      const target = (event as CustomEvent<Session>).detail;
      if (target?.productId) openSavedProject(target);
    };
    window.addEventListener(P1_OPEN_EVENT, handleOpen);
    return () => window.removeEventListener(P1_OPEN_EVENT, handleOpen);
  }, []);

  const pkbData = record(pkb?.data);
  const features = list(pkbData.features);
  const sources = list(pkb?.sources);
  const scriptContent = record(script?.content);
  const scenes = list(scriptContent.scenes);
  const scriptNarrationWords = script ? narrationWordCount(script) : 0;
  const manifest = record(videoJob?.result_manifest);
  const qa = record(manifest.qa);
  const stageIndex = stages.findIndex(([key]) => key === stage);
  const assets = useMemo(() => list(record(crawlJob?.result_manifest).assets), [crawlJob]);

  function save(patch: Partial<Session>) {
    const current = sessionRef.current;
    const next = { ...current, ...patch, ...(current.productId || patch.productId ? { savedAt: new Date().toISOString() } : {}) };
    sessionRef.current = next;
    setSession(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    if (next.productId) {
      const history = [next, ...savedSessions.filter(item => item.productId !== next.productId)].slice(0, 50);
      localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(history));
      setSavedSessions(history);
      window.dispatchEvent(new Event(P1_SESSIONS_EVENT));
    }
  }

  function clearError() { setError(""); }

  async function loadPkb(productId: string, version: number) {
    const value = await api<Json>(`products/${productId}/pkb/${version}`);
    setPkb(value);
    const data = record(value.data);
    const item = record(data.identity);
    setName(factValue(item.name));
    const verifiedDescription = factValue(item.description);
    const suggestion = verifiedDescription || suggestedProductDescription(data);
    setDescription(suggestion);
    setDescriptionSuggested(!verifiedDescription && Boolean(suggestion));
    setStage("pkb");
  }

  async function loadScript(productId: string, revision: number) {
    const value = await api<Json>(`products/${productId}/scripts/${revision}`);
    setScript(value);
    setSceneDrafts(list(record(value.content).scenes).map((scene, index) => ({
      id: text(scene.scene_id, `s${String(index + 1).padStart(2, "0")}`),
      headline: text(scene.role, "Khám phá sản phẩm").replaceAll("_", " ").toUpperCase(),
      subtitle: text(scene.subtitle_text) || list(scene.narration_segments).map(segment => text(segment.text)).join(" "),
      assetId: text(record(scene.visual_plan).asset_id),
      motion: ["zoom_in", "pan_right", "zoom_out", "pan_left"][index % 4],
    })));
    if (narrationWordCount(value) > 150) {
      setFeedback(current => current.trim() ? current : P1_DURATION_REVISION_FEEDBACK);
    }
    setStage("script");
  }

  async function runCrawl(productId: string, authSessionId?: string) {
    setStage("crawl");
    setStatus("M1 đang nhận phiên truy cập, crawl dữ kiện và chụp tư liệu thật…");
    const created = await post<Json>(`products/${productId}/crawl`, {
      idempotency_key: idempotency("crawl"),
      owner_context: [
        audience.trim() ? `Đối tượng khán giả chủ sở hữu xác định: ${audience.trim()}` : "",
        ownerContext.trim(),
      ].filter(Boolean).join("\n") || null,
      creative_preferences: [
        `Mục tiêu video: ${videoGoal}`,
        preferences.trim(),
      ].filter(Boolean).join("\n") || null,
      auth_session_id: authSessionId ?? null,
    });
    const crawlJobId = text(created.job_id);
    save({ crawlJobId, loginRequired: false, authSessionId });
    const job = await waitForJob(crawlJobId, value => {
      setCrawlJob(value);
      setStatus(value.status === "running" ? "M1 đang crawl, trích xuất dữ kiện, chụp ảnh và quay clip thao tác đọc-only…" : "M1 đang chờ runner local…");
    });
    setCrawlJob(job);
    const version = Number(job.pkb_version);
    if (!Number.isInteger(version) || version < 1) throw new Error("M1 hoàn tất nhưng chưa tạo PKB.");
    const captured = list(record(job.result_manifest).assets);
    if (!captured.length) throw new Error("M1 chưa thu được ảnh sản phẩm hợp lệ; không cho tạo video chỉ có nền trắng.");
    save({ pkbVersion: version });
    await loadPkb(productId, version);
    setStatus(`M1 đã tạo PKB và thu ${captured.length} tư liệu. Chủ sản phẩm cần kiểm tra trước khi tạo kịch bản.`);
  }

  async function openLogin() {
    if (!session.productId || !session.loginUrl) return;
    clearError(); setBusy(true);
    try {
      await post(`products/${session.productId}/login/browser`, { login_url: session.loginUrl });
      setStatus("Cửa sổ Chromium đã mở. Hãy đăng nhập trực tiếp trên website thật, rồi quay lại đây xác nhận.");
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  async function finishLogin() {
    if (!session.productId) return;
    clearError(); setBusy(true);
    try {
      const result = await post<Json>(`products/${session.productId}/login/finish`, {});
      if (!result.authenticated) throw new Error("Trang vẫn đang ở màn hình đăng nhập. Hãy đăng nhập xong rồi xác nhận lại.");
      const authSessionId = text(result.auth_session_id);
      save({ authSessionId, loginRequired: false });
      await runCrawl(session.productId, authSessionId);
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  async function restartDiscovery() {
    if (!session.productId) return;
    clearError(); setBusy(true);
    try {
      setCrawlJob(null); setPkb(null); setScript(null); setVideoJob(null); setStage("crawl");
      save({
        crawlJobId: undefined, pkbVersion: undefined, scriptRevision: undefined,
        scriptApproved: false, videoJobId: undefined, loginRequired: false,
      });
      setStatus("Đang kiểm tra lại quyền truy cập trước khi thu tư liệu mới…");
      const preflight = await post<Json>(`products/${session.productId}/discovery/preflight`, {});
      if (preflight.requires_login) {
        save({
          loginRequired: true,
          loginUrl: text(preflight.login_url, session.url),
          loginReason: text(preflight.reason),
        });
        setStatus("M1 cần chủ sản phẩm đăng nhập trước khi khám phá lại.");
        return;
      }
      await runCrawl(session.productId, session.authSessionId);
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  async function resume(target: Session = session) {
    clearError(); setBusy(true);
    try {
      if (target.loginRequired) {
        setStage("crawl");
        setStatus("Website cần đăng nhập. Hệ thống đang chờ chủ sản phẩm mở phiên truy cập.");
        return;
      }
      if (target.crawlJobId) {
        const sourceJob = await api<Json>(`jobs/${target.crawlJobId}`);
        setCrawlJob(sourceJob);
      }
      if (target.videoJobId) {
        if (target.scriptRevision && target.productId) await loadScript(target.productId, target.scriptRevision);
        setStage("production"); setStatus("Đang kiểm tra tác vụ dựng video…");
        const job = await waitForJob(target.videoJobId, setVideoJob);
        setVideoJob(job); setStage("done"); setStatus("Video đã dựng xong và đã chạy QA.");
      } else if (target.scriptApproved) {
        if (target.scriptRevision && target.productId) await loadScript(target.productId, target.scriptRevision);
        setStage("production");
        setStatus("Kịch bản đã duyệt. Có thể tiếp tục chọn cấu hình dựng video.");
      } else if (target.scriptRevision && target.productId) {
        await loadScript(target.productId, target.scriptRevision);
      } else if (target.pkbVersion && target.productId) {
        await loadPkb(target.productId, target.pkbVersion);
      } else if (target.crawlJobId && target.productId) {
        setStage("crawl"); setStatus("Đang tiếp tục theo dõi M1…");
        const job = await waitForJob(target.crawlJobId, setCrawlJob);
        const version = Number(job.pkb_version);
        if (!Number.isInteger(version) || version < 1) throw new Error("M1 hoàn tất nhưng chưa tạo PKB.");
        save({ pkbVersion: version });
        await loadPkb(target.productId, version);
      }
    } catch (cause) {
      setError(message(cause));
      if (target.videoJobId) {
        save({ videoJobId: undefined });
        setVideoJob(null); setStage("production");
        setStatus("Video job đã dừng. Bạn có thể dựng lại mà không làm lại PKB/kịch bản.");
      } else {
        setStage("crawl");
        setStatus("M1 chưa hoàn tất. Có thể tải lại trạng thái sau khi xử lý lỗi truy cập.");
      }
    }
    finally { setBusy(false); }
  }

  async function start(event: FormEvent) {
    event.preventDefault(); clearError(); setBusy(true); setStage("crawl");
    try {
      setStatus("Đang tạo Product và kiểm tra website có yêu cầu đăng nhập hay không…");
      let product: Json;
      try {
        product = await post<Json>("products", { website_url: url.trim() });
      } catch (cause) {
        if (!message(cause).includes("website_url đã tồn tại")) throw cause;
        product = await api<Json>(`products/by-url?website_url=${encodeURIComponent(url.trim())}`);
        setStatus("URL đã có trong dữ liệu local. Hệ thống đang tiếp tục Product cũ…");
      }
      const productId = text(product.id);
      const needsLogin = discoveryMode === "authenticated" || manualLogin;
      save({ productId, url: url.trim(), ownerContext, preferences, audience, videoGoal, manualLogin: needsLogin, discoveryMode, crawlJobId: undefined, loginRequired: needsLogin });
      if (needsLogin) {
        save({ loginRequired: true, loginUrl: url.trim(), loginReason: "owner_requested" });
        setStatus("Chủ sản phẩm yêu cầu đăng nhập trước. M1 đang chờ bạn mở phiên truy cập.");
        return;
      }
      const preflight = await post<Json>(`products/${productId}/discovery/preflight`, {});
      if (preflight.requires_login) {
        const loginUrl = text(preflight.login_url, url.trim());
        save({ loginRequired: true, loginUrl, loginReason: text(preflight.reason) });
        setStage("crawl");
        setStatus("M1 phát hiện màn hình đăng nhập và đã tạm dừng trước khi đọc sản phẩm.");
        return;
      }
      await runCrawl(productId);
    } catch (cause) {
      setStage("crawl");
      setStatus("Chưa thể bắt đầu khám phá sản phẩm.");
      setError(message(cause));
    }
    finally { setBusy(false); }
  }

  async function approvePkb() {
    if (!session.productId || !session.pkbVersion || !pkb) return;
    clearError(); setBusy(true);
    try {
      let version = session.pkbVersion;
      const original = record(record(pkb.data).identity);
      if (name.trim() !== factValue(original.name) || description.trim() !== factValue(original.description)) {
        setStatus("Đang lưu chỉnh sửa của chủ sản phẩm thành PKB version mới…");
        const revised = await post<Json>(`products/${session.productId}/pkb/${version}/revise`, { name: name.trim(), description: description.trim() });
        version = Number(revised.version);
        save({ pkbVersion: version });
        await loadPkb(session.productId, version);
      }
      const currentPkb = await api<Json>(`products/${session.productId}/pkb/${version}`);
      if (currentPkb.status === "draft") {
        await post(`products/${session.productId}/pkb/${version}/review`, { decision: "submit", note: null });
        await post(`products/${session.productId}/pkb/${version}/review`, { decision: "approve", note: "Chủ sản phẩm đã xác nhận PKB trên FE local." });
      } else if (currentPkb.status === "in_review") {
        await post(`products/${session.productId}/pkb/${version}/review`, { decision: "approve", note: "Chủ sản phẩm đã xác nhận PKB trên FE local." });
      } else if (currentPkb.status !== "approved") {
        throw new Error(`PKB đang ở trạng thái ${String(currentPkb.status)}; cần tạo version mới trước khi tiếp tục.`);
      }
      setStatus("PKB đã duyệt. AI đang tạo concept và kịch bản chỉ từ dữ kiện đã xác nhận…");
      const permitted = assets.map(asset => ({
        asset_id: asset.asset_id,
        product_id: session.productId,
        kind: asset.kind,
        allowed_use: asset.allowed_use,
        rights_basis: asset.rights_basis,
      }));
      const generated = await post<Json>(`products/${session.productId}/scripts/generate`, {
        knowledge_version: version,
        idempotency_key: idempotency("script"),
        parent_revision: null,
        permitted_assets: permitted,
        content_context: {
          platform: "shorts",
          intent: scriptIntent(videoGoal),
          audience: audience.trim() || null,
          video_description: boundedVideoDescription([
            ownerContext.trim() ? `Thông tin chủ sở hữu cung cấp để định hướng, không tự xem là fact: ${ownerContext.trim()}` : "",
            preferences.trim() ? `Mong muốn sáng tạo: ${preferences.trim()}` : "",
            assets.length >= 2 ? "Dùng tối thiểu hai permitted_assets khác nhau ở các cảnh để video thật sự giới thiệu sản phẩm; không lặp một ảnh cho toàn video." : "",
            template === "short-countdown" ? "Phong cách short đếm ngược: mở bằng vấn đề thật của sản phẩm, chọn tối đa ba điểm nổi bật có nguồn trong PKB, mỗi cảnh một ý và một thao tác/tư liệu phù hợp. Lời đọc tiếng Việt ngắn, tự nhiên, giàu nhịp, không thêm tính năng hay con số chưa xác minh; kết bằng lời mời hành động. Không đưa số thứ tự vào lời đọc." : "",
            "Dù website và tư liệu gốc viết bằng tiếng Anh hay ngôn ngữ khác, concept, hook, headline, phụ đề, CTA và toàn bộ narration_segments gửi TTS phải bằng tiếng Việt tự nhiên có dấu để người xem Việt hiểu cách dùng sản phẩm. Giữ nguyên tên thương hiệu, nhãn nút thật và thuật ngữ không nên dịch; diễn đạt lại đúng nghĩa, không thêm claim ngoài PKB.",
            P1_DURATION_INSTRUCTION,
            `Thời lượng người dùng chọn lúc bắt đầu: khoảng ${requestedDuration} giây; đây là mục tiêu biên tập, video hoàn chỉnh vẫn phải dưới 60 giây và không được thêm claim để kéo dài.`,
          ]) || "Tạo video giới thiệu sản phẩm trung thực, dễ hiểu.",
        },
      });
      const revision = Number(generated.revision);
      save({ pkbVersion: version, scriptRevision: revision });
      await loadScript(session.productId, revision);
      setStatus("Concept và kịch bản đã sẵn sàng để chủ sản phẩm duyệt.");
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  async function reviseScript() {
    if (!session.productId || !session.pkbVersion || !session.scriptRevision || !feedback.trim()) return;
    clearError(); setBusy(true);
    try {
      setStatus("AI đang tạo revision mới theo phản hồi; bản cũ vẫn được giữ nguyên…");
      const generated = await post<Json>(`products/${session.productId}/scripts/generate`, {
        knowledge_version: session.pkbVersion,
        idempotency_key: idempotency("script-revision"),
        parent_revision: session.scriptRevision,
        permitted_assets: assets.map(asset => ({
          asset_id: asset.asset_id,
          product_id: session.productId,
          kind: asset.kind,
          allowed_use: asset.allowed_use,
          rights_basis: asset.rights_basis,
        })),
        content_context: {
          platform: "shorts",
          intent: scriptIntent(videoGoal),
          audience: audience.trim() || null,
          video_description: boundedVideoDescription([`Phản hồi bắt buộc cho revision tiếp theo: ${feedback.trim()}`, P1_DURATION_INSTRUCTION, "Nếu có từ hai permitted_assets, phải dùng tối thiểu hai tư liệu khác nhau."]),
        },
      });
      const revision = Number(generated.revision);
      save({ scriptRevision: revision, revisionFeedback: undefined }); setFeedback("");
      await loadScript(session.productId, revision);
      setStatus(`Đã tạo kịch bản revision ${revision}.`);
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  async function approveScript() {
    if (!session.productId || !session.scriptRevision) return;
    clearError(); setBusy(true);
    try {
      await post(`products/${session.productId}/scripts/${session.scriptRevision}/review`, { decision: "submit", note: null });
      await post(`products/${session.productId}/scripts/${session.scriptRevision}/review`, { decision: "approve", note: "Chủ sản phẩm đã duyệt concept và kịch bản trên FE local." });
      save({ scriptApproved: true });
      setStage("production"); setStatus("Kịch bản đã khóa. Hãy chọn cấu hình dựng nhẹ cho máy local.");
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  async function render() {
    if (!session.productId || !session.pkbVersion || !session.scriptRevision) return;
    clearError(); setBusy(true); setStage("production");
    try {
      const assetPaths = Object.fromEntries(assets.filter(asset => text(asset.asset_id) && text(asset.path)).map(asset => [text(asset.asset_id), text(asset.path)]));
      const created = await post<Json>(`products/${session.productId}/videos`, {
        pkb_version: session.pkbVersion,
        script_revision: session.scriptRevision,
        idempotency_key: idempotency("video"),
        render_profile: template,
        n8n_execution_id: "local-direct-runner",
        options: {
          template,
          transition,
          aspect_ratio: ratio,
          resolution,
          asset_paths: assetPaths,
          scene_order: sceneDrafts.map(scene => scene.id),
          scene_overrides: Object.fromEntries(sceneDrafts.map(scene => [scene.id, {
            headline: scene.headline,
            subtitle: scene.subtitle,
            asset_id: scene.assetId,
            motion: scene.motion,
          }])),
        },
      });
      const videoJobId = text(created.job_id);
      save({ videoJobId }); setStatus("Đã xếp hàng dựng. Runner dùng TTS + FFmpeg, tối đa 2 luồng CPU mỗi cảnh…");
      const job = await waitForJob(videoJobId, value => {
        setVideoJob(value);
        setStatus(value.status === "running" ? "Đang tạo giọng, dựng từng cảnh và chạy ffprobe QA…" : "Đang chờ runner local nhận tác vụ video…");
      });
      setVideoJob(job); setStage("done"); setStatus("Video đã dựng xong và đã chạy QA.");
    } catch (cause) { setError(message(cause)); }
    finally { setBusy(false); }
  }

  function reset() {
    localStorage.removeItem(STORAGE_KEY);
    sessionRef.current = {};
    window.dispatchEvent(new Event(P1_SESSIONS_EVENT));
    setSession({}); setStage("intake"); setUrl(""); setOwnerContext(""); setPreferences("");
    setAudience(""); setVideoGoal("brand");
    setManualLogin(false); setDiscoveryMode("public"); setSceneDrafts([]);
    setDescriptionSuggested(false); setCrawlJob(null); setPkb(null); setScript(null); setVideoJob(null); setStatus(""); setError("");
    onReset?.();
  }

  function openSavedProject(target: Session) {
    localStorage.removeItem(P1_PENDING_OPEN_KEY);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(target));
    sessionRef.current = target;
    setSession(target);
    window.dispatchEvent(new Event(P1_SESSIONS_EVENT));
    setUrl(target.url ?? ""); setOwnerContext(target.ownerContext ?? ""); setPreferences(target.preferences ?? "");
    setAudience(target.audience ?? ""); setVideoGoal(target.videoGoal ?? "brand");
    setManualLogin(target.manualLogin ?? false);
    setDiscoveryMode(target.discoveryMode ?? (target.manualLogin ? "authenticated" : "public"));
    setFeedback(target.revisionFeedback ?? ""); setCrawlJob(null); setPkb(null); setScript(null); setVideoJob(null);
    void resume(target);
  }

  async function returnToScript() {
    if (!session.productId || !session.scriptRevision) return;
    const durationFailed = error.includes("TTS dài") || text(videoJob?.error).includes("TTS dài");
    save({ videoJobId: undefined, scriptApproved: false });
    setVideoJob(null);
    await loadScript(session.productId, session.scriptRevision);
    if (durationFailed) {
      setFeedback(P1_DURATION_REVISION_FEEDBACK);
      save({ videoJobId: undefined, scriptApproved: false, revisionFeedback: P1_DURATION_REVISION_FEEDBACK });
      setStatus("Đã điền sẵn yêu cầu rút kịch bản theo thời lượng TTS. Hãy bấm “Tạo revision mới”.");
    } else {
      setStatus("Bản đã duyệt được giữ nguyên. Hãy nhập phản hồi để AI tạo revision mới.");
    }
    setError("");
  }

  function retryProduction() {
    save({ videoJobId: undefined });
    setVideoJob(null); setStage("production");
    setStatus("Có thể đổi template, tỷ lệ hoặc độ phân giải rồi tạo một video job mới.");
  }

  function fillDurationFeedback() {
    setFeedback(P1_DURATION_REVISION_FEEDBACK);
    save({ revisionFeedback: P1_DURATION_REVISION_FEEDBACK });
  }

  function updateScene(id: string, patch: Partial<SceneDraft>) {
    setSceneDrafts(current => current.map(scene => scene.id === id ? { ...scene, ...patch } : scene));
  }

  function changeTemplate(value: string) {
    const isPro = value === "review-pro" || value === "short-countdown" || value.startsWith("reels-");
    const next = { template: value, ratio: isPro ? "9:16" : ratio, resolution: isPro ? "1080p" : resolution, transition };
    setTemplate(next.template); setRatio(next.ratio); setResolution(next.resolution);
    localStorage.setItem(VIDEO_PREFS_KEY, JSON.stringify(next));
  }

  function changeVideoPreference(patch: Partial<VideoPreferences>) {
    const next = { template, ratio, resolution, transition, ...patch };
    setTemplate(next.template); setRatio(next.ratio); setResolution(next.resolution); setTransition(next.transition);
    localStorage.setItem(VIDEO_PREFS_KEY, JSON.stringify(next));
  }

  function moveScene(index: number, direction: -1 | 1) {
    setSceneDrafts(current => {
      const target = index + direction;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  return <div className="local-p1">
    <header className="local-p1-heading">
      <div><span className="local-p1-kicker">P1 · LOCAL END-TO-END</span><h1>Từ link sản phẩm đến MP4 có kiểm soát</h1><p>M1 và AI chỉ đề xuất. Chủ sản phẩm duyệt PKB và duyệt kịch bản trước khi hệ thống được phép dựng video.</p></div>
      <button type="button" className="secondary-button" onClick={reset} disabled={busy}>Bắt đầu lại</button>
    </header>
    <ol className="local-p1-steps">{stages.map(([key, label], index) => <li key={key} className={index < stageIndex ? "done" : index === stageIndex ? "active" : ""}><span>{index < stageIndex ? "✓" : index + 1}</span><small>{label}</small></li>)}</ol>

    {session.productId && stage !== "intake" && <div className="local-p1-resume"><span>Phiên local: <code>{session.productId.slice(0, 8)}</code></span><button type="button" className="text-button" onClick={() => void resume()} disabled={busy}>Tiếp tục / tải lại trạng thái</button></div>}
    {status && <p className="local-p1-status" role="status">{busy && <span className="local-p1-spinner" aria-hidden="true" />} {status}</p>}
    {error && <div className="local-p1-error" role="alert">
      <strong>Chưa thể tiếp tục</strong><p>{error}</p>
      {stage === "production" && session.videoJobId && error.includes("icon Lucide") && <button type="button" className="secondary-button" onClick={retryProduction} disabled={busy}>Thử dựng lại video</button>}
      {stage === "production" && session.scriptRevision && <button type="button" className="secondary-button" onClick={() => void returnToScript()} disabled={busy}>Quay lại sửa kịch bản</button>}
    </div>}

    {stage === "intake" && <section className="local-p1-card">
      <div className="local-p1-card-title"><span>01</span><div><h2>Cung cấp sản phẩm</h2><p>Chỉ link là bắt buộc. Hai vùng mô tả giúp AI hiểu ý chủ sở hữu nhưng không tự trở thành dữ kiện đã xác minh.</p></div></div>
      <form className="local-p1-form" onSubmit={start}>
        {entryUrl ? <div className="local-p1-note"><strong>Link sản phẩm đã chọn</strong><span>{url}</span></div> : <label>Link sản phẩm <b>*</b><input type="url" required value={url} onChange={event => setUrl(event.target.value)} placeholder="https://san-pham-cua-ban.com" /></label>}
        <fieldset className="local-p1-discovery-modes"><legend>Cách Agent khám phá</legend><button type="button" className={discoveryMode === "public" ? "active" : ""} onClick={() => { setDiscoveryMode("public"); setManualLogin(false); }}><strong>Website công khai</strong><span>Agent đọc menu và tối đa các trang nội bộ an toàn; không thao tác ghi.</span></button><button type="button" className={discoveryMode === "authenticated" ? "active" : ""} onClick={() => { setDiscoveryMode("authenticated"); setManualLogin(true); }}><strong>Cần chủ sở hữu đăng nhập</strong><span>Bạn tự nhập mật khẩu/OTP trên website thật, sau đó Agent mới được tiếp tục.</span></button></fieldset>
        <div className="local-p1-grid"><label>Đối tượng khán giả <small>Không bắt buộc</small><input value={audience} maxLength={500} onChange={event => setAudience(event.target.value)} placeholder="Ví dụ: chủ shop online 22–35 tuổi cần làm video nhanh" /></label><label>Mục tiêu video<select value={videoGoal} onChange={event => setVideoGoal(event.target.value)}><option value="brand">Nhận diện thương hiệu</option><option value="sales">Thúc đẩy mua hàng</option><option value="traffic">Đưa người xem về website</option><option value="education">Giải thích sản phẩm</option><option value="follow">Tăng theo dõi</option></select></label></div>
        <label>Thông tin sản phẩm từ chủ sở hữu <small>Không bắt buộc</small><textarea rows={5} maxLength={4000} value={ownerContext} onChange={event => setOwnerContext(event.target.value)} placeholder="Sản phẩm dành cho ai, vấn đề giải quyết, tính năng muốn nhấn mạnh, thông tin nội bộ cần AI hiểu…" /></label>
        <div className="local-p1-note"><strong>Cấu hình đã chọn</strong><span>{template} · {ratio} · khoảng {requestedDuration}s. Bạn có thể đổi template và tỷ lệ ở bước dựng sau khi duyệt kịch bản.</span></div>
        {discoveryMode === "authenticated" && <div className="local-p1-note"><strong>Đăng nhập có kiểm soát</strong><span>Google có thể chặn trình duyệt tự động. Khi đó hãy dùng API cho dịch vụ Google; Browser Agent chỉ dành cho website sản phẩm cho phép phiên truy cập này.</span></div>}
        <div className="local-p1-note"><strong>Luật an toàn nội dung</strong><span>Claim trong video phải trỏ về PKB đã duyệt; ý tưởng sáng tạo không được biến thành thông tin sản phẩm.</span></div>
        <button className="primary-button" disabled={busy}>Khám phá sản phẩm</button>
      </form>
    </section>}

    {stage === "crawl" && session.loginRequired && <section className="local-p1-card">
      <div className="local-p1-card-title"><span>02</span><div><h2>Sản phẩm yêu cầu đăng nhập</h2><p>M1 đã dừng trước màn hình đăng nhập. Tài khoản và mật khẩu không được gửi cho AI hoặc lưu trong Reviewlab.</p></div></div>
      <div className="local-p1-note"><strong>Trang đăng nhập thật</strong><span>{session.loginUrl}</span></div>
      <ol><li>Bấm mở cửa sổ và đăng nhập trực tiếp trên website sản phẩm.</li><li>Hoàn tất OTP/Google nếu có.</li><li>Quay lại đây và xác nhận đã đăng nhập xong.</li></ol>
      <div className="local-p1-actions"><button type="button" className="secondary-button" onClick={openLogin} disabled={busy}>Mở cửa sổ đăng nhập</button><button type="button" className="primary-button" onClick={finishLogin} disabled={busy}>Tôi đã đăng nhập xong</button></div>
    </section>}

    {stage === "crawl" && !session.loginRequired && <section className="local-p1-card local-p1-wait"><div className="local-p1-card-title"><span>02</span><div><h2>M1 đang khám phá sản phẩm</h2><p>Crawl website, lưu nguồn, trích xuất PKB, chụp ảnh và quay clip thao tác đọc-only; tư liệu trắng hoặc trùng sẽ bị loại.</p></div></div><div className="local-p1-pipeline"><span>Crawl</span><i>→</i><span>Trích xuất fact</span><i>→</i><span>Browser Agent</span><i>→</i><span>PKB + tư liệu</span></div></section>}

    {stage === "pkb" && pkb && <section className="local-p1-card">
      <div className="local-p1-card-title"><span>03</span><div><h2>Chủ sản phẩm duyệt PKB v{session.pkbVersion}</h2><p>Hãy sửa tên hoặc mô tả nếu crawler hiểu sai. Mọi sửa đổi được lưu thành version mới, không ghi đè bản crawl.</p></div></div>
      <div className="local-p1-grid"><label>Tên sản phẩm<input value={name} onChange={event => setName(event.target.value)} /></label><label className="wide">{descriptionSuggested ? "Mô tả AI tổng hợp — cần chủ sở hữu xác minh" : "Mô tả đã xác minh"}<textarea rows={5} value={description} onChange={event => { setDescription(event.target.value); setDescriptionSuggested(true); }} />{descriptionSuggested && <small className="local-p1-field-note">Mô tả này chỉ ghép từ các tính năng có nguồn bên dưới. Hãy sửa nếu chưa đúng; bấm xác nhận sẽ lưu thành PKB version mới.</small>}</label></div>
      <h3>Tính năng có bằng chứng</h3><div className="local-p1-facts">{features.length ? features.map((feature, index) => <article key={text(feature.id, String(index))}><strong>{text(feature.name, "Tính năng")}</strong><p>{text(feature.description, "Chưa có mô tả chi tiết.")}</p><small>{text(feature.source_id)} · “{text(feature.evidence)}”</small></article>) : <p>PKB chưa trích xuất được tính năng rõ ràng.</p>}</div>
      {!!assets.length && session.crawlJobId && <><h3>Tư liệu sản phẩm M1 đã thu</h3><div className="local-p1-media-review">{assets.map((asset, index) => <figure key={text(asset.asset_id, String(index))}>{isVideoAsset(asset) ? <video controls muted playsInline preload="metadata" src={`/api/p1/jobs/${session.crawlJobId}/assets/${index}`} /> : <Image unoptimized width={1280} height={720} src={`/api/p1/jobs/${session.crawlJobId}/assets/${index}`} alt={`Tư liệu sản phẩm ${index + 1}`} />}<figcaption>{text(asset.asset_id)} · {text(asset.kind)}</figcaption></figure>)}</div></>}
      <h3>Bản đồ khám phá của Agent</h3><div className="local-p1-discovery-map">{sources.length ? sources.map((source, index) => <article key={text(source.id, String(index))}><span>{String(index + 1).padStart(2, "0")}</span><div><strong>{text(source.page_type, "Trang sản phẩm").replaceAll("_", " ")}</strong><a href={text(source.url)} target="_blank" rel="noreferrer">{text(source.url)}</a></div><i>Đã đọc</i></article>) : <p>Chưa có trang nào được lập bản đồ.</p>}</div>
      <div className="local-p1-note"><strong>Phạm vi an toàn</strong><span>Agent chỉ đọc, cuộn, hover, mở tab/menu nội bộ. Đăng xuất, mua hàng, thanh toán, xóa dữ liệu và gửi biểu mẫu đều bị loại khỏi kế hoạch tự động.</span></div>
      <details className="local-p1-sources"><summary>{sources.length} nguồn đã crawl</summary>{sources.map(source => <a key={text(source.id)} href={text(source.url)} target="_blank" rel="noreferrer">{text(source.id)} · {text(source.page_type)} · {text(source.url)}</a>)}</details>
      <div className="local-p1-actions"><button type="button" className="primary-button" onClick={approvePkb} disabled={busy || !name.trim() || !description.trim()}>Xác nhận PKB và tạo kịch bản</button></div>
    </section>}

    {stage === "script" && script && <section className="local-p1-card">
      <div className="local-p1-card-title"><span>04</span><div><h2>Duyệt concept & kịch bản · revision {session.scriptRevision}</h2><p>Đây là cổng duyệt thứ hai. Chưa bấm xác nhận thì hệ thống không thể tạo video job.</p></div></div>
      <div className="local-p1-concept"><span>CONCEPT</span><h3>{text(record(scriptContent.concept).title, "Chưa đặt tiêu đề")}</h3><p>{text(record(scriptContent.concept).angle)}</p><blockquote>{text(record(scriptContent.hook).text)}</blockquote></div>
      <div className="local-p1-scenes">{scenes.map((scene, index) => <article key={text(scene.scene_id, String(index))}><div><b>{text(scene.scene_id, `Cảnh ${index + 1}`)}</b><span>{text(scene.role)}</span></div><p>{list(scene.narration_segments).map(segment => text(segment.text)).join(" ")}</p><small>Hình: {text(record(scene.visual_plan).kind)} · Asset: {text(record(scene.visual_plan).asset_id, "text/generated")}</small>{list(scene.claims).map((claim, claimIndex) => <details key={claimIndex}><summary>Claim: {text(claim.text)}</summary>{list(claim.fact_refs).map((ref, refIndex) => <code key={refIndex}>{text(ref.field_path)} · {text(ref.source_id, "owner fact")}</code>)}</details>)}</article>)}</div>
      <label className="local-p1-feedback">Yêu cầu AI sửa kịch bản <small>Kịch bản hiện khoảng {scriptNarrationWords} từ · short video phải dưới 60 giây</small><textarea rows={3} maxLength={1500} value={feedback} onChange={event => { setFeedback(event.target.value); save({ revisionFeedback: event.target.value || undefined }); }} placeholder="Ví dụ: mở đầu ngắn hơn, giọng tự nhiên hơn; không thay đổi dữ kiện sản phẩm…" /></label>
      <div className="local-p1-actions"><button type="button" className="secondary-button" onClick={fillDurationFeedback} disabled={busy}>Điền yêu cầu dưới 60 giây</button><button type="button" className="secondary-button" onClick={reviseScript} disabled={busy || !feedback.trim()}>Tạo revision mới</button><button type="button" className="primary-button" onClick={approveScript} disabled={busy}>Xác nhận concept & kịch bản</button></div>
    </section>}

    {stage === "production" && !session.videoJobId && <section className="local-p1-card">
      <div className="local-p1-card-title"><span>05</span><div><h2>Storyboard & cấu hình dựng</h2><p>Duyệt clip Browser Agent, chọn tư liệu, chuyển động, thứ tự và phụ đề trước khi tạo MP4.</p></div></div>
      <h3>Chọn template dùng lại</h3>
      <p className="local-p1-help">Bạn đã chọn {template} · {ratio} · khoảng {requestedDuration}s lúc bắt đầu. Muốn đổi trước khi dựng video thì chọn lại bên dưới.</p>
      <p className="local-p1-help">Lựa chọn được ghi nhớ cho những lần chạy sau. Preview bên dưới dùng chính tư liệu M1 đã thu.</p>
      <div className="local-p1-template-catalog">{TEMPLATE_CATALOG.map(item => <button type="button" key={item.id} className={template === item.id ? "active" : ""} onClick={() => changeTemplate(item.id)}><i>{item.badge}</i><strong>{item.name}</strong><span>{item.use}</span></button>)}</div>
      <div className="local-p1-config"><label>Tỷ lệ<select value={ratio} onChange={event => changeVideoPreference({ ratio: event.target.value })}><option>9:16</option><option>16:9</option></select></label><label>Chuyển cảnh<select value={transition} onChange={event => changeVideoPreference({ transition: event.target.value })}><option value="fade">Fade mềm</option><option value="none">Không hiệu ứng</option></select></label><label>Độ phân giải<select value={resolution} onChange={event => changeVideoPreference({ resolution: event.target.value })}><option>720p</option><option>1080p</option></select></label></div>
      <div className={`local-p1-template-preview ${template} ${ratio === "9:16" ? "portrait" : "landscape"}`}>
        {(() => {
          const selectedAssetIndex = assets.findIndex(asset => text(asset.asset_id) === sceneDrafts[0]?.assetId);
          const previewAssetIndex = selectedAssetIndex >= 0 ? selectedAssetIndex : 0;
          const previewAsset = assets[previewAssetIndex];
          return <>
            <div className="local-p1-template-copy"><span>✦ {TEMPLATE_CATALOG.find(item => item.id === template)?.badge} · {ratio}</span><strong>{sceneDrafts[0]?.headline || name || "Sản phẩm của bạn"}</strong><small>{sceneDrafts[0]?.subtitle || description || "Tư liệu và lời giới thiệu sản phẩm."}</small></div>
            <div className="local-p1-template-chrome"><span /><span /><span /></div>
            {previewAsset && session.crawlJobId ? (isVideoAsset(previewAsset) ? <video className="local-p1-template-media" muted autoPlay loop playsInline preload="metadata" src={`/api/p1/jobs/${session.crawlJobId}/assets/${previewAssetIndex}`} /> : <Image className="local-p1-template-media" unoptimized fill sizes="(max-width: 900px) 100vw, 640px" src={`/api/p1/jobs/${session.crawlJobId}/assets/${previewAssetIndex}`} alt="Tư liệu sản phẩm trong template" />) : <div className="local-p1-template-empty">Chưa có tư liệu sản phẩm</div>}
          </>;
        })()}
      </div>
      <h3>Chỉnh storyboard trước khi dựng</h3>
      <div className="local-p1-storyboard">{sceneDrafts.map((scene, index) => {
        const assetIndex = assets.findIndex(asset => text(asset.asset_id) === scene.assetId);
        const selectedAsset = assetIndex >= 0 ? assets[assetIndex] : undefined;
        const preview = assetIndex >= 0 && session.crawlJobId ? (isVideoAsset(selectedAsset) ? <video controls muted playsInline preload="metadata" src={`/api/p1/jobs/${session.crawlJobId}/assets/${assetIndex}`} /> : <Image unoptimized width={1280} height={720} src={`/api/p1/jobs/${session.crawlJobId}/assets/${assetIndex}`} alt={`Xem trước ${scene.id}`} />) : <span>Chưa chọn tư liệu</span>;
        return <article key={scene.id}><div className="local-p1-storyboard-preview">{preview}</div><div className="local-p1-storyboard-fields"><strong>{scene.id}</strong><label>Tiêu đề ngắn<input value={scene.headline} maxLength={72} onChange={event => updateScene(scene.id, { headline: event.target.value })} /></label><label>Tư liệu<select value={scene.assetId} onChange={event => updateScene(scene.id, { assetId: event.target.value })}>{assets.map(asset => <option key={text(asset.asset_id)} value={text(asset.asset_id)}>{text(asset.kind) === "screen_recording" ? "▶ Clip thao tác · " : "Ảnh · "}{text(asset.asset_id)}</option>)}</select></label><label>Chuyển động<select value={scene.motion} disabled={isVideoAsset(selectedAsset)} onChange={event => updateScene(scene.id, { motion: event.target.value })}><option value="zoom_in">Zoom vào nhẹ</option><option value="zoom_out">Zoom ra nhẹ</option><option value="pan_left">Trượt sang trái</option><option value="pan_right">Trượt sang phải</option><option value="none">Đứng yên</option></select></label><label>Phụ đề<textarea rows={3} value={scene.subtitle} onChange={event => updateScene(scene.id, { subtitle: event.target.value })} /></label><div><button type="button" className="text-button" onClick={() => moveScene(index, -1)} disabled={index === 0}>↑ Lên</button><button type="button" className="text-button" onClick={() => moveScene(index, 1)} disabled={index === sceneDrafts.length - 1}>↓ Xuống</button></div></div></article>;
      })}</div>
      <div className="local-p1-note"><strong>Browser Agent chỉ thao tác đọc-only</strong><span>Clip tự động chỉ cuộn, hover hoặc mở liên kết nội bộ an toàn; không gửi form, mua hàng, xóa dữ liệu hay thực hiện thao tác ghi.</span></div>
      <div className="local-p1-actions"><button type="button" className="primary-button" onClick={render} disabled={busy}>Tạo MP4 và chạy QA</button></div>
    </section>}

    {stage === "production" && session.videoJobId && <section className="local-p1-card local-p1-wait"><div className="local-p1-card-title"><span>05</span><div><h2>Đang sản xuất video</h2><p>TTS → dựng từng cảnh → ghép MP4 → ffprobe → kiểm tra có tư liệu sản phẩm.</p></div></div><div className="local-p1-pipeline"><span>TTS</span><i>→</i><span>FFmpeg 2 threads</span><i>→</i><span>MP4</span><i>→</i><span>QA</span></div></section>}

    {stage === "done" && videoJob && <section className="local-p1-card">
      <div className="local-p1-card-title"><span>06</span><div><h2>Kết quả dựng & QA</h2><p>Video chỉ được tải khi cả thông số kỹ thuật và tư liệu sản phẩm đều đạt.</p></div></div>
      <div className={`local-p1-qa ${qa.passed ? "pass" : "fail"}`}><strong>{qa.passed ? "QA ĐẠT — được phép tải" : "QA CHƯA ĐẠT — chặn tải"}</strong><span>H.264/AAC · {text(manifest.resolution)} · {text(manifest.ratio)} · {String(manifest.duration_s ?? "—")}s</span><span>Kỹ thuật: {qa.technical_passed ? "đạt" : "không đạt"} · Tư liệu sản phẩm: {qa.product_media_present ? "có" : "thiếu"}</span>{list(qa.warnings).map((warning, index) => <p key={index}>{String(warning)}</p>)}</div>
      {qa.passed ? <div className="local-p1-video"><video controls playsInline preload="metadata" src={`/api/p1/jobs/${session.videoJobId}/video`} /><a className="primary-button" href={`/api/p1/jobs/${session.videoJobId}/video`} download={`reviewlab-p1-${session.videoJobId}.mp4`}>Tải video MP4</a></div> : <><div className="local-p1-note"><strong>Cần sửa trước khi phát hành</strong><span>Kiểm tra lại asset mà kịch bản tham chiếu hoặc bổ sung tư liệu có quyền sử dụng, sau đó tạo revision/video job mới.</span></div><div className="local-p1-actions"><button type="button" className="secondary-button" onClick={retryProduction}>Dựng lại cấu hình khác</button><button type="button" className="primary-button" onClick={() => void returnToScript()}>Tạo revision kịch bản mới</button></div></>}
      <details className="local-p1-sources"><summary>Truy vết đầu ra</summary><code>Product {session.productId}</code><code>PKB v{session.pkbVersion}</code><code>Script revision {session.scriptRevision}</code><code>Video job {session.videoJobId}</code><code>Render {String(manifest.render_seconds ?? "—")}s</code></details>
      <div className="local-p1-actions"><button type="button" className="secondary-button" onClick={restartDiscovery} disabled={busy}>Thu lại tư liệu sản phẩm</button></div>
    </section>}
  </div>;
}
