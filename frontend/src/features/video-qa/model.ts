import { demoReviews } from "../reviews/demo";
import type { Project } from "../content-factory/model";
import type { Review } from "../reviews/types";

export const hookTypes = ["Curiosity", "Pain", "Challenge"] as const;
export const angles = ["Problem", "Comparison", "Tutorial", "Demo"] as const;
export const VIDEO_KEY = "reviewlab.video-qa.mock.v1";
export const checks = [
  { key: "facts", label: "Thông tin và giá khớp PKB đã duyệt" },
  { key: "claims", label: "Không có claim cấm hoặc trải nghiệm bịa đặt" },
  { key: "format", label: "MP4 1080×1920 · 9:16 · thời lượng 15–60 giây" },
  {
    key: "captions",
    label: "Caption nằm trong Safe Zone, đọc được và đúng thời điểm",
  },
  { key: "audio", label: "Audio / TTS rõ ràng, kiểm tra đồng bộ lời và hình" },
  { key: "disclosure", label: "Nhãn AI và affiliate disclosure phù hợp" },
] as const;
export type CheckKey = (typeof checks)[number]["key"];
export type VideoStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "archived";
export type VideoAsset = {
  angle?: string;
  hook?: string;
  hookType?: (typeof hookTypes)[number];
  createdAt?: string;
  duration?: number;
  width?: number;
  height?: number;
  render?: {
    status: "queued" | "running" | "completed" | "failed";
    step: string;
    error: string | null;
  };
  review: Review;
  productId: string;
  knowledgeVersion: number;
  status: VideoStatus;
  caption: string;
  checklist: Record<CheckKey, boolean>;
  reason: string;
  flaggedAt: string | null;
  flagReason: string;
  updatedAt: string;
  firstApprovedAt: string | null;
  reviewedAt: string | null;
  reviewedBy: string | null;
};
export type VideoState = { schema: 2; revision: number; assets: VideoAsset[] };
export const videoLabels: Record<VideoStatus, string> = {
  pending_review: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Từ chối",
  archived: "Đã lưu trữ",
};
export const initialVideos: VideoState = {
  schema: 2,
  revision: 0,
  assets: demoReviews.map((review) => ({
    review: verticalReview(review),
    angle: "Demo",
    hookType: "Curiosity",
    hook: "Could this fit your workflow?",
    createdAt: "2026-10-08T00:00:00.000Z",
    duration: 15,
    width: 1080,
    height: 1920,
    render: { status: "completed", step: "Render mẫu có sẵn", error: null },
    productId: review.product.toLowerCase(),
    knowledgeVersion: 1,
    status:
      review.product === "Gamma"
        ? "approved"
        : review.product === "Linear"
          ? "rejected"
          : "pending_review",
    caption: `${review.title}\nIllustrative demo content. AI-assisted content and affiliate disclosure must be reviewed before publishing.`,
    checklist: {
      facts: review.product === "Gamma",
      claims: review.product === "Gamma",
      format: review.product === "Gamma",
      captions: review.product === "Gamma",
      audio: review.product === "Gamma",
      disclosure: review.product === "Gamma",
    },
    reason:
      review.product === "Linear"
        ? "Mẫu từ chối: cần đối chiếu claim trong caption với PKB."
        : "",
    flaggedAt: null,
    flagReason: "",
    updatedAt: "2026-10-08T00:00:00.000Z",
    firstApprovedAt:
      review.product === "Gamma" ? "2026-10-08T00:00:00.000Z" : null,
    reviewedAt: review.product === "Notion" ? null : "2026-10-08T00:00:00.000Z",
    reviewedBy: review.product === "Notion" ? null : "demo-admin",
  })),
};

export function decideVideo(
  asset: VideoAsset,
  target: "approved" | "rejected" | "archived",
  checklist: Record<CheckKey, boolean>,
  reason: string,
  pkbApproved: boolean,
): VideoAsset {
  if (asset.status === "archived")
    throw new Error("Video đã lưu trữ không thể duyệt lại.");
  if (
    asset.status !== "pending_review" &&
    !(asset.status === "approved" && asset.flaggedAt)
  )
    throw new Error("Video không nằm trong hàng đợi cần xử lý.");
  if (
    target === "rejected" &&
    (asset.status !== "pending_review" || asset.firstApprovedAt)
  )
    throw new Error(
      "Video đã duyệt chỉ có thể lưu trữ, không chuyển sang rejected.",
    );
  if (
    target === "archived" &&
    (asset.status !== "approved" || !asset.firstApprovedAt)
  )
    throw new Error("Chỉ lưu trữ video đã được duyệt.");
  if (
    target === "approved" &&
    (asset.render?.status !== "completed" ||
      asset.width !== 1080 ||
      asset.height !== 1920 ||
      !asset.duration ||
      asset.duration < 15 ||
      asset.duration > 60)
  )
    throw new Error("Cần render hoàn tất, 1080×1920 và thời lượng 15–60 giây.");
  if (
    target === "approved" &&
    (!pkbApproved ||
      !checks.every(({ key }) => checklist[key]) ||
      !asset.review.videoUrl)
  )
    throw new Error(
      "Cần PKB nguồn đã duyệt, video và đủ các mục kiểm tra trước khi duyệt.",
    );
  if (target !== "approved" && !reason.trim())
    throw new Error("Nhập lý do xử lý video.");
  const now = new Date().toISOString();
  const locked = asset.firstApprovedAt !== null;
  return {
    ...asset,
    status: target,
    checklist: locked ? asset.checklist : { ...checklist },
    reason: target === "approved" ? "" : reason.trim(),
    flaggedAt: null,
    flagReason: "",
    updatedAt: now,
    firstApprovedAt:
      asset.firstApprovedAt ?? (target === "approved" ? now : null),
    reviewedAt: locked ? asset.reviewedAt : now,
    reviewedBy: locked ? asset.reviewedBy : "demo-admin",
  };
}
export function flagVideo(asset: VideoAsset, reason: string): VideoAsset {
  if (asset.status !== "approved" || asset.flaggedAt)
    throw new Error("Chỉ báo sai video đã duyệt chưa có báo cáo đang xử lý.");
  if (!reason.trim()) throw new Error("Nhập nội dung cần Admin kiểm tra.");
  return {
    ...asset,
    flaggedAt: new Date().toISOString(),
    flagReason: reason.trim(),
  };
}
export function parseVideos(raw: string): VideoState {
  const stored = JSON.parse(raw);
  if (
    !stored ||
    ![1, 2].includes(stored.schema) ||
    !Number.isInteger(stored.revision) ||
    stored.revision < 0 ||
    !Array.isArray(stored.assets)
  )
    throw new Error("Invalid video storage");
  // Keep the existing storage key. Older demo saves gain the new lifecycle and
  // synthetic audit metadata in memory; write schema 2 on the next user action.
  if (stored.schema === 1) {
    for (const asset of stored.assets) {
      if (!asset || typeof asset.updatedAt !== "string")
        throw new Error("Invalid legacy video asset");
      if (asset.status === "in_review") asset.status = "pending_review";
      const seed = initialVideos.assets.find(
        (item) => item.review.id === asset.review?.id,
      );
      if (asset.status === "rejected" && seed?.firstApprovedAt)
        asset.status = "archived";
      const approved =
        asset.status === "approved" || asset.status === "archived";
      asset.firstApprovedAt = approved
        ? (seed?.firstApprovedAt ?? asset.updatedAt)
        : null;
      asset.reviewedAt =
        asset.firstApprovedAt ??
        (asset.status === "rejected" ? asset.updatedAt : null);
      asset.reviewedBy = asset.reviewedAt ? "demo-admin" : null;
    }
    stored.schema = 2;
  }
  const state = stored as VideoState;
  const ids = new Set<string>();
  for (const asset of state.assets) {
    const seed = initialVideos.assets.find(
      (item) => item.review.id === asset.review?.id,
    );
    if (seed) {
      for (const key of ["format", "captions", "audio"] as const)
        if (typeof asset.checklist?.[key] !== "boolean")
          asset.checklist[key] = !!(
            asset.checklist as unknown as { media?: boolean }
          ).media;
      delete (asset.checklist as unknown as { media?: boolean }).media;
    }

    if (
      !asset.review ||
      !(
        initialVideos.assets.some(
          (item) =>
            item.review.id === asset.review.id &&
            item.productId === asset.productId,
        ) ||
        (asset.review.id.startsWith("generated-") &&
          typeof asset.productId === "string" &&
          asset.productId &&
          Number.isInteger(asset.knowledgeVersion) &&
          asset.knowledgeVersion > 0)
      ) ||
      ids.has(asset.review.id) ||
      !["pending_review", "approved", "rejected", "archived"].includes(
        asset.status,
      ) ||
      !checks.every(({ key }) => typeof asset.checklist?.[key] === "boolean") ||
      typeof asset.reason !== "string" ||
      typeof asset.caption !== "string" ||
      typeof asset.updatedAt !== "string" ||
      typeof asset.flagReason !== "string" ||
      (asset.flaggedAt !== null && typeof asset.flaggedAt !== "string")
    )
      throw new Error("Invalid video asset");
    for (const key of ["firstApprovedAt", "reviewedAt", "reviewedBy"] as const)
      if (
        asset[key] !== null &&
        (typeof asset[key] !== "string" || !asset[key])
      )
        throw new Error("Invalid video audit metadata");
    const approved = asset.status === "approved" || asset.status === "archived";
    if (
      approved !== (asset.firstApprovedAt !== null) ||
      (approved && (!asset.reviewedAt || !asset.reviewedBy)) ||
      (asset.flaggedAt &&
        (asset.status !== "approved" || !asset.flagReason.trim()))
    )
      throw new Error("Invalid video lifecycle");
    ids.add(asset.review.id);
    // Media and PKB references come from the local fixture, never from localStorage.
    const source = initialVideos.assets.find(
      (item) => item.review.id === asset.review.id,
    );
    if (source) {
      asset.review = source.review;
      asset.knowledgeVersion = source.knowledgeVersion;
      for (const key of [
        "angle",
        "hook",
        "createdAt",
        "duration",
        "width",
        "height",
        "render",
      ] as const)
        if (asset[key] === undefined)
          Object.assign(asset, { [key]: source[key] });
    } else {
      if (
        typeof asset.review.title !== "string" ||
        typeof asset.review.product !== "string" ||
        !asset.render ||
        !["queued", "running", "completed", "failed"].includes(
          asset.render.status,
        ) ||
        typeof asset.angle !== "string" ||
        typeof asset.hook !== "string" ||
        typeof asset.createdAt !== "string" ||
        asset.width !== 1080 ||
        asset.height !== 1920 ||
        asset.duration !== 15
      )
        throw new Error("Invalid generated mock");
      asset.review = verticalReview(asset.review);
    }
  }
  if (!initialVideos.assets.every((asset) => ids.has(asset.review.id)))
    throw new Error("Missing video assets");
  return state;
}

function verticalReview(review: Review): Review {
  return {
    ...review,
    videoUrl: "/media/leader-demo.mp4",
    thumbnailUrl: "/media/vertical-poster.svg",
    transcript: [
      { start: 0, end: 5, text: "This is a sample review workspace." },
      {
        start: 5,
        end: 10,
        text: "Check product facts against the approved knowledge base.",
      },
      {
        start: 10,
        end: 15,
        text: "Review the draft before sharing. This video is a demonstration.",
      },
    ],
  };
}
export function requestVideo(
  project: Project,
  angle: string,
  hook: string,
  hookType: (typeof hookTypes)[number] = "Curiosity",
): VideoAsset {
  const pkb = project.knowledge.find(
    (v) =>
      v.version === project.currentKnowledgeVersion && v.status === "approved",
  );
  if (!pkb)
    throw new Error("Cần PKB đã được Merchant duyệt trước khi tạo video.");
  const now = new Date().toISOString();
  return {
    review: verticalReview({
      ...demoReviews[0],
      id: `generated-${crypto.randomUUID()}`,
      product: project.name,
      title: `${project.name}: ${angle}`,
      summary: "Local template preview, not generated product footage.",
      score: null,
    }),
    productId: project.id,
    knowledgeVersion: pkb.version,
    status: "pending_review",
    caption: `${project.name} — ${hook}\nDemo template. AI-assisted content. Affiliate link disclosure.\n#ProductReview #Demo`,
    checklist: {
      facts: false,
      claims: false,
      format: false,
      captions: false,
      audio: false,
      disclosure: false,
    },
    reason: "",
    flaggedAt: null,
    flagReason: "",
    updatedAt: now,
    firstApprovedAt: null,
    reviewedAt: null,
    reviewedBy: null,
    angle,
    hook,
    hookType,
    createdAt: now,
    duration: 15,
    width: 1080,
    height: 1920,
    render: {
      status: "queued",
      step: "Chờ render template (mock)",
      error: null,
    },
  };
}
export function changeRender(
  asset: VideoAsset,
  status: "running" | "completed" | "failed",
): VideoAsset {
  if (
    asset.firstApprovedAt ||
    !asset.render ||
    (status === "running"
      ? !["queued", "failed"].includes(asset.render.status)
      : asset.render.status !== "running")
  )
    throw new Error("Trạng thái render không phù hợp.");
  return {
    ...asset,
    render: {
      status,
      step:
        status === "completed"
          ? "Sẵn sàng QA (mock)"
          : status === "running"
            ? "Render template (mock)"
            : "Render thất bại (mock)",
      error: status === "failed" ? "Demo render error; thử lại job." : null,
    },
    updatedAt: new Date().toISOString(),
  };
}
export function displayVideoStatus(asset: VideoAsset) {
  return asset.flaggedAt
    ? "Flagged"
    : asset.render && asset.render.status !== "completed"
      ? asset.render.status === "failed"
        ? "Render failed"
        : "Processing"
      : asset.status === "pending_review"
        ? "Ready · chờ QA"
        : videoLabels[asset.status];
}

export function hookCategory(asset: VideoAsset): string {
  return (
    asset.hookType ??
    (asset.hook === "Could this fit your workflow?"
      ? "Curiosity"
      : "Chưa phân loại")
  );
}

export function distributionCaption(asset: VideoAsset): string {
  return /#[\p{L}\p{N}_]+/u.test(asset.caption)
    ? asset.caption
    : `${asset.caption}\n#ProductReview #Demo`;
}
