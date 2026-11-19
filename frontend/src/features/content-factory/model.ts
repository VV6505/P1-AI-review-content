export type Origin = "crawled" | "merchant" | "inferred";
export type Fact = { value: string; origin: Origin; sourceId: string | null; evidence: string };
export const knowledgeFields = [
  { key: "description", label: "Mô tả sản phẩm" }, { key: "features", label: "Tính năng" },
  { key: "useCases", label: "Use cases" }, { key: "audiences", label: "Đối tượng / JTBD" },
  { key: "usp", label: "USP / Positioning" }, { key: "limitations", label: "Giới hạn" },
  { key: "brand", label: "Thương hiệu / Tone" }, { key: "models", label: "Phiên bản / Models" },
  { key: "approvedClaims", label: "Claim được phép" }, { key: "forbiddenClaims", label: "Claim không được phép" },
] as const;
export type KnowledgeField = typeof knowledgeFields[number]["key"];
export type PricingPlan = { priceConfirmed?: boolean; name: string; listPrice: number; promoPrice: number | null; promoTerms: string; priceUnit: "month" | "year" | "seat_month" | "seat_year" | "one_time"; billingCycle: "monthly" | "quarterly" | "yearly" | "one_time"; priceText: string; origin: Origin; sourceId: string | null; evidence: string; limits?: string; currency?: string };
export type MockUpload = { id: string; name: string; type: string; size: number };
export type MerchantInput = { name: string; tagline: string; pricing: string; features: string[]; forbiddenClaims: string; logo: string; color: string; uploads: MockUpload[] };
export type IntakeDraft = MerchantInput & { website: string; affiliate: string };
export type Conflict = { crawledPlan?: PricingPlan; field: KnowledgeField | "pricing"; merchant: string; crawled: string; resolved: "merchant" | "crawled" | null };
export type KnowledgeData = { facts: Record<KnowledgeField, Fact>; pricing: { currency: string; region: string; locale: string; defaultView: string; plans: PricingPlan[]; otherViews?: string[]; usagePrices?: { name: string; price: number; unit: string; currency: string }[] }; tagline?: string; logo?: string; color?: string; conflicts?: Conflict[]; featureCards?: { id: string; name: string; description: string; screenshot: string }[] };
export type Source = { id: string; url: string; pageType: string; retrievedAt: null; contentHash: null; sample: true };
export type KnowledgeVersion = { version: number; status: "draft" | "in_review" | "approved" | "rejected"; data: KnowledgeData; sources: Source[]; updatedAt: string; approvedAt: string | null; approvedBy: string | null; rejectionReason: string | null };
export type GenerationJob = { id: string; jobType: "crawl"; status: "queued" | "running" | "completed" | "failed"; step: string; error: string | null; attempts: number };
export type Content = { hook: string; script: string; caption: string; knowledgeVersion: number };
export type Project = { campaign?: { active: boolean; joined: boolean; views: number; clicks: number }; id: string; name: string; url: string; affiliate: string; category: string; status: "draft" | "active" | "archived"; currentKnowledgeVersion: number | null; knowledge: KnowledgeVersion[]; job: GenerationJob; content: Content | null; merchantInput?: MerchantInput };
export type DemoRole = "merchant" | "admin";
export type WorkspaceState = { schema: 2; revision: number; projects: Project[]; selectedId: string; role: DemoRole; intakeDraft?: IntakeDraft | null };
export const WORKSPACE_KEY = "reviewlab.m1.mock.v2";

export function normalizeWebsiteUrl(value: string): string {
  const url = new URL(value.trim());
  if (!["https:", "http:"].includes(url.protocol) || !url.hostname.includes(".") || url.username || url.password) throw new Error("Nhập URL HTTP/HTTPS hợp lệ, không chứa thông tin đăng nhập.");
  // Mock canonicalization only: collapse scheme/www/trailing slash, preserve product path/query.
  url.protocol = "https:"; url.hostname = url.hostname.toLowerCase().replace(/^www\./, ""); url.hash = "";
  url.pathname = url.pathname.replace(/\/+$/, "") || "/";
  return url.toString().replace(/\/$/, "");
}
export function validAffiliateUrl(value: string): boolean {
  try { const url = new URL(value.trim()); return ["https:", "http:"].includes(url.protocol) && url.hostname.includes(".") && !url.username && !url.password; } catch { return false; }
}
function fact(value: string, origin: Origin = "crawled"): Fact {
  return { value, origin, sourceId: origin === "crawled" ? "homepage" : null, evidence: origin === "crawled" ? "Mock excerpt for UI testing; no website content has been collected." : "" };
}
export function createKnowledge(name: string, url: string, version = 1): KnowledgeVersion {
  return { version, status: "draft", updatedAt: new Date().toISOString(), approvedAt: null, approvedBy: null, rejectionReason: null,
    sources: [{ id: "homepage", url, pageType: "homepage", retrievedAt: null, contentHash: null, sample: true }, { id: "pricing", url: `${url.split("?")[0]}/pricing`, pageType: "pricing", retrievedAt: null, contentHash: null, sample: true }],
    data: { facts: {
      description: fact(`${name} is used here as a sample product for the English-language review workflow.`),
      features: fact("Organize information\nCollaborate with your team\nShare your work"),
      useCases: fact("Prepare a product brief\nReview and organize a content draft"),
      audiences: fact("Content creators and small product teams\nJTBD: Turn verified product information into a clear review before publishing.", "inferred"),
      usp: fact("A simpler workflow for organizing product information", "inferred"),
      limitations: fact(""), brand: fact("Use clear, factual English and a neutral tone.", "merchant"),
      models: fact(""), approvedClaims: fact("Only use claims verified by the merchant.", "merchant"),
      forbiddenClaims: fact("Do not invent performance, pricing or revenue guarantees.", "merchant"),
    }, pricing: { currency: "USD", region: "US (mock)", locale: "en-US", defaultView: "monthly", plans: [{ name: "Demo plan", listPrice: 20, promoPrice: null, promoTerms: "", priceUnit: "month", billingCycle: "monthly", priceText: "$20 / month — illustrative value, not a real product price", origin: "crawled", sourceId: "pricing", evidence: "Mock pricing excerpt; not the product's actual price." }] } },
  };
}
export function createMockProject(url: string, affiliate: string, id: string = crypto.randomUUID()): Project {
  const canonical = normalizeWebsiteUrl(url);
  if (!validAffiliateUrl(affiliate)) throw new Error("Merchant affiliate URL không hợp lệ.");
  return { id, name: new URL(canonical).hostname, url: canonical, affiliate: affiliate.trim(), category: "Unclassified", status: "draft", currentKnowledgeVersion: null, knowledge: [], job: { id: `crawl-${id}`, jobType: "crawl", status: "queued", step: "Waiting for demo crawl", error: null, attempts: 0 }, content: null };
}
export function latestKnowledge(project: Project) { return project.knowledge.at(-1); }
export function approvedKnowledge(project: Project) { return project.knowledge.find((item) => item.version === project.currentKnowledgeVersion && item.status === "approved"); }
export function changeJob(project: Project, target: GenerationJob["status"]): Project {
  if (target === "running" && !["queued", "failed"].includes(project.job.status)) throw new Error("Job không thể bắt đầu ở trạng thái hiện tại.");
  if (["completed", "failed"].includes(target) && project.job.status !== "running") throw new Error("Hãy bắt đầu job trước khi hoàn tất hoặc báo lỗi.");
  if (target === "queued") throw new Error("Không thể đặt lại job đã tạo.");
  const job = { ...project.job, status: target, step: target === "running" ? "Crawling / extracting (mock)" : target === "completed" ? "PKB draft ready (mock)" : "Demo crawl failed", attempts: target === "running" ? project.job.attempts + 1 : project.job.attempts, error: target === "failed" ? "Demo error: source could not be processed. Retry this job." : null };
  if (target !== "completed") return { ...project, job };
  const latest = latestKnowledge(project);
  if (latest && ["draft", "in_review"].includes(latest.status)) throw new Error("Đã có bản PKB đang xử lý.");
  return { ...project, job, knowledge: [...project.knowledge, enrichKnowledge(createKnowledge(project.name, project.url, (latest?.version ?? 0) + 1), project.merchantInput)] };
}
export function knowledgeErrors(version: KnowledgeVersion): string[] {
  const errors: string[] = [];
  if (version.data.conflicts?.some(item => !item.resolved)) errors.push("Giải quyết các xung đột trước khi gửi duyệt.");
  if (!version.data.facts.description.value.trim()) errors.push("Cần mô tả sản phẩm.");
  if (!version.data.facts.features.value.trim()) errors.push("Cần ít nhất một tính năng.");
  for (const field of knowledgeFields) {
    const f = version.data.facts[field.key];
    if (f.value.trim() && f.origin === "crawled" && (!f.evidence.trim() || !version.sources.some((s) => s.id === f.sourceId))) errors.push(`${field.label}: thiếu nguồn hoặc evidence.`);
    if (f.evidence.length > 200) errors.push(`${field.label}: evidence tối đa 200 ký tự.`);
  }
  for (const plan of version.data.pricing.plans) {
    if (plan.priceConfirmed === false) errors.push("Xác nhận giá Merchant: nhập lại giá niêm yết trong bảng PKB trước khi gửi duyệt.");
    if (!plan.name.trim() || !Number.isFinite(plan.listPrice) || plan.listPrice < 0 || (plan.promoPrice !== null && (!Number.isFinite(plan.promoPrice) || plan.promoPrice < 0))) errors.push("Giá/gói không hợp lệ.");
    if (!plan.priceText.trim()) errors.push("Cần price_text nguyên văn cho gói.");
    if (plan.evidence.length > 200) errors.push("Evidence giá tối đa 200 ký tự.");
    if (plan.origin === "crawled" && (!plan.evidence.trim() || !version.sources.some((s) => s.id === plan.sourceId))) errors.push("Giá/gói thiếu nguồn hoặc evidence.");
  }
  return errors;
}
export function saveKnowledge(project: Project, data: KnowledgeData, expectedUpdatedAt: string): Project {
  const latest = latestKnowledge(project);
  if (!latest || latest.status !== "draft") throw new Error("Chỉ chỉnh sửa draft. Hãy tạo phiên bản mới từ bản đã duyệt.");
  if (latest.updatedAt !== expectedUpdatedAt) throw new Error("Bản draft đã thay đổi. Tải lại trước khi lưu.");
  return { ...project, knowledge: project.knowledge.map((v) => v.version === latest.version ? { ...v, data: structuredClone(data), updatedAt: new Date().toISOString() } : v) };
}
export function transitionKnowledge(project: Project, target: "in_review" | "approved" | "rejected", role: DemoRole, reason = ""): Project {
  const latest = latestKnowledge(project);
  if (!latest) throw new Error("Chưa có PKB draft.");
  if ((target === "in_review" && latest.status !== "draft") || (target !== "in_review" && latest.status !== "in_review")) throw new Error("Trạng thái PKB không phù hợp.");
  if ((target === "in_review" || target === "approved") && role !== "merchant") throw new Error("Chỉ merchant được gửi duyệt và approve PKB trong mock.");
  if (target === "rejected" && role !== "admin") throw new Error("Chỉ admin được từ chối PKB vi phạm chính sách.");
  if (target === "rejected" && !reason.trim()) throw new Error("Cần lý do từ chối.");
  if (target !== "rejected" && knowledgeErrors(latest).length) throw new Error(knowledgeErrors(latest).join(" "));
  const now = new Date().toISOString();
  const next = { ...latest, status: target, updatedAt: now, approvedAt: target === "approved" ? now : null, approvedBy: target === "approved" ? "demo-merchant" : null, rejectionReason: target === "rejected" ? reason.trim() : null };
  return { ...project, knowledge: project.knowledge.map((v) => v.version === latest.version ? next : v), currentKnowledgeVersion: target === "approved" ? latest.version : project.currentKnowledgeVersion, status: target === "approved" ? "active" : project.status };
}
export function newDraft(project: Project, role: DemoRole): Project {
  if (role !== "merchant") throw new Error("Chỉ merchant tạo draft mới trong mock.");
  const latest = latestKnowledge(project);
  if (!latest || !["approved", "rejected"].includes(latest.status)) throw new Error("Đã có draft hoặc chưa có PKB để sao chép.");
  return { ...project, knowledge: [...project.knowledge, { ...structuredClone(latest), version: latest.version + 1, status: "draft", updatedAt: new Date().toISOString(), approvedAt: null, approvedBy: null, rejectionReason: null }] };
}
export function createMockContent(project: Project, audience: string, platform: string): Content {
  const pkb = approvedKnowledge(project);
  if (!pkb) throw new Error("Cần PKB đã được merchant duyệt.");
  return { knowledgeVersion: pkb.version, hook: `Could ${project.name} fit your workflow as ${audience.toLowerCase()}?`, script: `[0–3s · Hook]\nCould ${project.name} fit your workflow?\n\n[3–10s · Introduction]\n${pkb.data.facts.description.value}\n\n[10–25s · Demonstration]\nUse authorized footage to demonstrate: ${pkb.data.facts.features.value.replace(/\n/g, "; ")}. Only use merchant-approved claims.\n\n[25–30s · CTA]\nLearn more through the product link.\n\nPlatform: ${platform}. Language: English. PKB version: ${pkb.version}. Demo template, not AI-generated content.`, caption: `${project.name} — a sample workflow for ${audience.toLowerCase()}.\nLearn more: ${project.affiliate}\n#ProductReview #AItools\nDemo content. Include the appropriate affiliate disclosure before publishing.` };
}

export function enrichKnowledge(version: KnowledgeVersion, input?: MerchantInput): KnowledgeVersion {
  const next = structuredClone(version);
  next.data.pricing.otherViews = ["yearly", "quarterly"];
  next.data.pricing.plans[0].limits = "100 credits / month (sample)";
  next.data.pricing.plans[0].currency = next.data.pricing.currency;
  next.data.pricing.usagePrices = [{ name: "Extra credits (sample)", price: 1, unit: "100 credits", currency: "USD" }];
  next.data.featureCards = next.data.facts.features.value.split("\n").map((name, i) => ({ id: `feature-${i}`, name, description: "Sample feature evidence for layout review.", screenshot: "/media/feature-evidence.svg" }));
  next.data.logo = input?.logo || "/media/product-mark.svg";
  next.data.color = input?.color || "#333333";
  next.data.tagline = input?.tagline || "A sample product workspace";
  next.data.conflicts = [];
  if (input) {
    for (const [field, value] of [["features", input.features.filter(Boolean).join("\n")], ["forbiddenClaims", input.forbiddenClaims]] as const) {
      if (!value.trim()) continue;
      const crawled = next.data.facts[field].value;
      next.data.facts[field] = fact(value, "merchant");
      if (value !== crawled) next.data.conflicts.push({ field, merchant: value, crawled, resolved: null });
    }
    if (input.pricing.trim()) {
      next.data.conflicts.push({ field: "pricing", crawledPlan: structuredClone(next.data.pricing.plans[0]), merchant: input.pricing, crawled: next.data.pricing.plans[0].priceText, resolved: null });
      next.data.pricing.plans[0] = { ...next.data.pricing.plans[0], priceText: input.pricing, priceConfirmed: false, origin: "merchant", sourceId: null, evidence: "" };
    }
  }
  return next;
}

export function startRecrawl(project: Project): Project {
  const latest = latestKnowledge(project);
  if (["queued", "running"].includes(project.job.status) || (latest && ["draft", "in_review"].includes(latest.status))) throw new Error("Hoàn tất job/PKB đang xử lý trước khi cào lại.");
  return { ...project, job: { ...project.job, id: `crawl-${project.id}-${crypto.randomUUID()}`, status: "queued", step: "Chờ cào lại (mock)", error: null, attempts: 0 } };
}
function seed(name: string, url: string, id: string, approved = false): Project {
  const project = createMockProject(url, url, id), version = enrichKnowledge(createKnowledge(name, project.url));
  version.updatedAt = "2026-10-07T00:00:00.000Z"; version.status = approved ? "approved" : "draft";
  if (approved) { version.approvedAt = version.updatedAt; version.approvedBy = "demo-merchant"; }
  return { ...project, campaign: { active: approved, joined: approved, views: 0, clicks: 0 }, name, category: "Productivity", status: approved ? "active" : "draft", currentKnowledgeVersion: approved ? 1 : null, knowledge: [version], job: { ...project.job, status: "completed", step: "PKB draft ready (mock)", attempts: 1 } };
}
export const initialProjects = [seed("Gamma", "https://gamma.app", "gamma", true), seed("Notion", "https://notion.so", "notion"), seed("Linear", "https://linear.app", "linear")];
export const initialWorkspace: WorkspaceState = { schema: 2, revision: 0, projects: initialProjects, selectedId: "gamma", role: "merchant" };

export function parseWorkspace(raw: string): WorkspaceState {
  const data = JSON.parse(raw) as WorkspaceState;
  if (!data || data.schema !== 2 || !Number.isInteger(data.revision) || data.revision < 0 || !Array.isArray(data.projects) || !["merchant", "admin"].includes(data.role)) throw new Error("Invalid mock workspace");
  if (data.intakeDraft) validateInput(data.intakeDraft);
  const ids = new Set<string>();
  for (const p of data.projects) {
    if (!p || typeof p.id !== "string" || ids.has(p.id) || typeof p.name !== "string" || typeof p.category !== "string" || normalizeWebsiteUrl(p.url) !== p.url || !validAffiliateUrl(p.affiliate) || !["draft", "active", "archived"].includes(p.status)) throw new Error("Invalid product");
    if (p.merchantInput) validateInput(p.merchantInput);
    if (p.campaign && (typeof p.campaign.active !== "boolean" || typeof p.campaign.joined !== "boolean" || !Number.isFinite(p.campaign.views) || p.campaign.views < 0 || !Number.isFinite(p.campaign.clicks) || p.campaign.clicks < 0)) throw new Error("Invalid campaign");
    ids.add(p.id);
    if (!p.job || p.job.jobType !== "crawl" || !["queued", "running", "completed", "failed"].includes(p.job.status) || typeof p.job.step !== "string" || !Array.isArray(p.knowledge)) throw new Error("Invalid job");
    let previous = 0;
    for (const v of p.knowledge) {
      if (!Number.isInteger(v.version) || v.version <= previous || !["draft", "in_review", "approved", "rejected"].includes(v.status) || typeof v.updatedAt !== "string" || !Array.isArray(v.sources)) throw new Error("Invalid version");
      previous = v.version;
      for (const s of v.sources) if (typeof s.id !== "string" || !validAffiliateUrl(s.url) || s.sample !== true) throw new Error("Invalid source");
      for (const field of knowledgeFields) { const f = v.data.facts[field.key]; if (typeof f.value !== "string" || !["crawled", "merchant", "inferred"].includes(f.origin) || typeof f.evidence !== "string") throw new Error("Invalid fact"); }
      if (!Array.isArray(v.data.pricing.plans) || typeof v.data.pricing.currency !== "string" || typeof v.data.pricing.region !== "string" || typeof v.data.pricing.defaultView !== "string") throw new Error("Invalid pricing");
      if (v.status === "approved" && (!v.approvedAt || !v.approvedBy || knowledgeErrors(v).length)) throw new Error("Invalid approval");
    }
    if (p.currentKnowledgeVersion !== null && !approvedKnowledge(p)) throw new Error("Invalid approved pointer");
    if (p.content && (typeof p.content.hook !== "string" || typeof p.content.script !== "string" || typeof p.content.caption !== "string" || !p.knowledge.some((v) => v.version === p.content!.knowledgeVersion && v.status === "approved"))) throw new Error("Invalid content snapshot");
  }
  if (!ids.has(data.selectedId)) throw new Error("Invalid selection");
  return data;
}

function validateInput(input: MerchantInput) {
  for (const key of ["name", "tagline", "pricing", "forbiddenClaims", "logo", "color"] as const) if (typeof input[key] !== "string") throw new Error("Invalid intake");
  if (!Array.isArray(input.features) || !input.features.every(item => typeof item === "string") || !Array.isArray(input.uploads) || input.uploads.length > 5 || !input.uploads.every(file => typeof file.id === "string" && typeof file.name === "string" && ["application/pdf", "image/png", "image/jpeg", "image/webp"].includes(file.type) && Number.isFinite(file.size) && file.size > 0 && file.size <= 5 * 1024 * 1024)) throw new Error("Invalid uploads");
}

export function updatePricingMeta(data: KnowledgeData, key: "currency" | "region" | "locale" | "defaultView", value: string): KnowledgeData {
  return { ...data, pricing: { ...data.pricing, [key]: value, plans: key === "currency" ? data.pricing.plans.map(plan => ({ ...plan, currency: value, origin: "merchant", sourceId: null, evidence: "" })) : data.pricing.plans } };
}
