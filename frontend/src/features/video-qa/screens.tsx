"use client";

import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { ArrowLeft, ArrowRight, Download, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useUnsavedChanges } from "../content-factory/use-unsaved-changes";
import { Textarea } from "@/components/ui/textarea";
import { VideoPlayer } from "../reviews/video-player";
import { useWorkspace } from "../content-factory/workspace-provider";
import { DemoNotice } from "../portals/dashboards";
import { useVideos } from "./provider";
import {
  distributionCaption,
  hookCategory,
  hookTypes,
  angles,
  checks,
  decideVideo,
  displayVideoStatus,
  videoLabels,
  type VideoAsset,
} from "./model";

function Status({ asset }: { asset: VideoAsset }) {
  return (
    <span
      className={`status-chip ${asset.flaggedAt ? "flagged" : asset.status}`}
    >
      {asset.flaggedAt ? "Merchant báo sai" : displayVideoStatus(asset)}
    </span>
  );
}
export function VideoList({
  admin = false,
}: {
  admin?: boolean;
}) {
  const creator = !admin;
  const { assets, ready, error } = useVideos();
  const [query, setQuery] = useState(""),
    [product, setProduct] = useState("all"),
    [angle, setAngle] = useState("all"),
    [hook, setHook] = useState("all");
  const [filter, setFilter] = useState(admin ? "pending_review" : "approved"),
    [preview, setPreview] = useState<string | null>(
      admin ? "notion-workspace" : null,
    );
  const actualFilter = filter;
  const visible = assets.filter(
    (a) =>
      (!creator || a.status === "approved") &&
      `${a.review.title} ${a.review.product}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (product === "all" || a.productId === product) &&
      (angle === "all" || a.angle === angle) &&
      (hook === "all" || hookCategory(a) === hook) &&
      (actualFilter === "all" ||
        (actualFilter === "flagged"
          ? !!a.flaggedAt
          : actualFilter === "processing"
            ? a.render?.status !== "completed"
            : actualFilter === "ready"
              ? a.status === "pending_review" &&
                a.render?.status === "completed"
              : actualFilter === "pending_review" && admin
                ? (a.status === "pending_review" &&
                    a.render?.status === "completed") ||
                  !!a.flaggedAt
                : a.status === actualFilter)),
  );
  const base = admin ? "/admin/videos" : "/creator/library";
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            {admin ? "ADMIN · VIDEO QA" : "CREATOR · CONTENT LIBRARY"}
          </p>
          <h1>{admin ? "QA Video" : "Thư viện nội dung"}</h1>
          <p>
            {admin
              ? "Chọn video mới / báo sai để kiểm tra trong khung bên cạnh."
              : "Video dọc 9:16, preview scene, captions và audio."}
          </p>
        </div>

      </div>
      <DemoNotice />
      <div className="portal-filters library-filters">
        <div className="search-input">
          <Search size={16} />
          <Input
            aria-label="Tìm nội dung"
            value={query}
            placeholder="Tìm nội dung…"
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        {[
          {
            label: "Product",
            value: product,
            set: setProduct,
            options: [
              ...new Map(
                assets.map((a) => [a.productId, a.review.product]),
              ).entries(),
            ],
          },
          {
            label: "Angle",
            value: angle,
            set: setAngle,
            options: [
              ...new Set([...angles, ...assets.map((a) => a.angle || "Demo")]),
            ].map((v) => [v, v]),
          },
          {
            label: "Hook",
            value: hook,
            set: setHook,
            options: [
              ...new Set([...hookTypes, ...assets.map(hookCategory)]),
            ].map((v) => [v, v]),
          },
        ].map((field) => (
          <div key={field.label}>
            <label htmlFor={`filter-${field.label}`}>{field.label}</label>
            <select
              id={`filter-${field.label}`}
              value={field.value}
              onChange={(e) => field.set(e.target.value)}
            >
              <option value="all">Tất cả</option>
              {field.options.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        ))}
        {!creator && (
          <div>
            <label htmlFor="video-status">Trạng thái</label>
            <select
              id="video-status"
              value={actualFilter}
              onChange={(e) => setFilter(e.target.value)}
            >
              {[
                "approved",
                "pending_review",
                "processing",
                "ready",
                "rejected",
                "archived",
                "flagged",
                "all",
              ].map((value) => (
                <option key={value} value={value}>
                  {
                    {
                      approved: "Đã duyệt",
                      pending_review: "Cần xử lý",
                      processing: "Processing",
                      ready: "Ready",
                      rejected: "Từ chối",
                      archived: "Đã lưu trữ",
                      flagged: "Merchant báo sai",
                      all: "Tất cả",
                    }[value]
                  }
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {!ready ? (
        <p role="status">Đang khôi phục thư viện…</p>
      ) : (
        <>
          <p role="status" className="review-result-count">
            {visible.length} video · dữ liệu mẫu
          </p>
          {admin ? (
            <div className="qa-split">
              <div className="table-scroll">
                <table className="leader-table">
                  <thead>
                    <tr>
                      <th>Video / sản phẩm</th>
                      <th>Ngày tạo</th>
                      <th>Angle / Hook</th>
                      <th>Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((asset) => (
                      <tr key={asset.review.id}>
                        <td>
                          <Link href={`${base}/${asset.review.id}`}>
                            {asset.review.title}
                          </Link>
                          <small>{asset.review.product}</small>
                          <Button
                            variant="ghost"
                            onClick={() => setPreview(asset.review.id)}
                          >
                            Kiểm tra tại đây
                          </Button>
                        </td>
                        <td>
                          {new Date(
                            asset.createdAt || asset.updatedAt,
                          ).toLocaleString("vi-VN")}
                        </td>
                        <td>
                          {asset.angle}
                          <small>
                            {hookCategory(asset)} · {asset.hook}
                          </small>
                        </td>
                        <td>
                          <Status asset={asset} />
                          <small>
                            {asset.flaggedAt ? "Báo sai" : "Video mới"}
                          </small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <section className="qa-preview">
                {preview ? (
                  <VideoDetail key={preview} id={preview} admin embedded />
                ) : (
                  <p>Chọn “Kiểm tra tại đây” để mở player và checklist QA.</p>
                )}
              </section>
            </div>
          ) : (
            <section className="asset-grid" aria-label="Thư viện video">
              {visible.map((asset) => (
                <article className="asset-card" key={asset.review.id}>
                  <button
                    className="asset-cover"
                    onClick={() => setPreview(asset.review.id)}
                    aria-label={`Preview ${asset.review.title}`}
                  >
                    <Image
                      src={asset.review.thumbnailUrl}
                      alt={`Ảnh minh họa ${asset.review.product}`}
                      width={1080}
                      height={1920}
                    />
                    <span>15s · 1080×1920 · MP4</span>
                  </button>
                  <div className="asset-body">
                    <div className="asset-meta">
                      <span>{asset.review.product}</span>
                      <Status asset={asset} />
                    </div>
                    <h2>
                      <Link href={`${base}/${asset.review.id}`}>
                        {asset.review.title}
                      </Link>
                    </h2>
                    <p>
                      Hook ({hookCategory(asset)}): {asset.hook}
                      <br />
                      Angle: {asset.angle} · PKB v{asset.knowledgeVersion}
                    </p>
                    {asset.reason && (
                      <p className="asset-reason">{asset.reason}</p>
                    )}
                    <Link
                      className="asset-link"
                      href={`${base}/${asset.review.id}`}
                    >
                      Xem nội dung
                      <ArrowRight size={14} />
                    </Link>
                  </div>
                </article>
              ))}
            </section>
          )}
          {!visible.length && (
            <div className="empty-list">
              <h2>Không có video phù hợp</h2>
              <Button
                variant="outline"
                onClick={() => {
                  setQuery("");
                  setProduct("all");
                  setAngle("all");
                  setHook("all");
                  setFilter("all");
                }}
              >
                Xóa bộ lọc
              </Button>
            </div>
          )}
        </>
      )}
      {!admin && (
        <Dialog
          open={!!preview}
          onOpenChange={(open) => {
            if (!open) setPreview(null);
          }}
        >
          <DialogContent className="video-dialog">
            <DialogTitle>Preview video</DialogTitle>
            <DialogDescription>
              Video mẫu local có TTS; scene và caption dùng để kiểm tra UI.
            </DialogDescription>
            {preview && <VideoDetail id={preview} embedded />}
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
export function VideoDetail({
  id,
  admin = false,
  embedded = false,
}: {
  id: string;
  admin?: boolean;
  embedded?: boolean;
}) {
  const { assets, ready, error } = useVideos();
  const [safeZone, setSafeZone] = useState(false);
  const asset = assets.find((a) => a.review.id === id),
    base = admin ? "/admin/videos" : "/creator/library";
  if (!ready) return <p role="status">Đang tải video…</p>;
  if (!asset)
    return (
      <section className="empty-list">
        <h1>Không tìm thấy video</h1>
        <Link href={base}>Về danh sách</Link>
      </section>
    );
  const processing = asset.render?.status !== "completed";
  return (
    <>
      {!embedded && (
        <>
          <Link href={base} className="back-link">
            <ArrowLeft size={14} />
            {admin ? "Hàng đợi QA" : "Thư viện nội dung"}
          </Link>
          <div className="page-heading">
            <div>
              <h1>{asset.review.title}</h1>
              <p>
                {asset.review.product} · PKB v{asset.knowledgeVersion} · English
              </p>
            </div>
            <Status asset={asset} />
          </div>
          <DemoNotice />
        </>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <p className="demo-note">
        MP4 · 1080×1920 · 15 giây · audio TTS mẫu (giọng hệ thống, không nhạc
        nền). Phụ đề là transcript theo scene. Footage workspace tự tạo, chưa
        render theo sản phẩm thật.
      </p>
      {admin && (
        <Button
          variant="outline"
          aria-pressed={safeZone}
          onClick={() => setSafeZone(!safeZone)}
        >
          {safeZone ? "Ẩn" : "Hiện"} Safe Zone
        </Button>
      )}
      <div className={admin ? "inspection-layout" : undefined}>
        <div>
          {processing ? (
            <p className="report-box">
              {asset.render?.step} · Chưa có video sẵn sàng QA. Chờ job render hoàn tất.
            </p>
          ) : (
            asset.review.videoUrl && (
              <VideoPlayer
                portrait
                safeZone={safeZone}
                src={asset.review.videoUrl}
                title={asset.review.title}
                poster={asset.review.thumbnailUrl}
                transcript={asset.review.transcript}
              />
            )
          )}
        </div>
        <div className={admin ? "inspection-actions" : undefined}>
          <VideoActions
            key={`${id}-${admin}-${asset.updatedAt}`}
            asset={asset}
            admin={admin}
          />
        </div>
      </div>
    </>
  );
}
function VideoActions({
  asset,
  admin,
}: {
  asset: VideoAsset;
  admin: boolean;
}) {
  const { updateVideo } = useVideos();
  const { projects } = useWorkspace();
  const project = projects.find((p) => p.id === asset.productId);
  const pkb = project?.knowledge.find(
    (v) => v.version === asset.knowledgeVersion,
  );
  const [checklist, setChecklist] = useState({ ...asset.checklist });
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [failure, setFailure] = useState("");
  useUnsavedChanges(reason.trim().length > 0);
  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setMessage("Đã sao chép.");
    } catch {
      setFailure("Không truy cập được clipboard; sao chép trực tiếp nội dung.");
    }
  }
  const actionable =
    (asset.render?.status === "completed" &&
      asset.status === "pending_review") ||
    (asset.status === "approved" && !!asset.flaggedAt);
  const previouslyApproved = asset.firstApprovedAt !== null;
  function run(action: () => void, success: string) {
    try {
      action();
      setFailure("");
      setMessage(success);
      setReason("");
    } catch (cause) {
      setMessage("");
      setFailure(
        cause instanceof Error ? cause.message : "Không thể lưu thay đổi.",
      );
    }
  }
  function downloadCaption() {
    const url = URL.createObjectURL(
      new Blob(
        [
          `DEMO — not approved for real publishing\n${distributionCaption(asset)}`,
        ],
        {
          type: "text/plain;charset=utf-8",
        },
      ),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${asset.review.id}-caption-demo.txt`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <div className="portal-columns portal-spacing">
      <section className="portal-panel">
        <h2>Thông tin nội dung</h2>
        <p className="panel-description">
          Snapshot PKB dùng để đối chiếu nội dung.
        </p>
        <dl className="asset-facts">
          <div>
            <dt>Sản phẩm</dt>
            <dd>{asset.review.product}</dd>
          </div>
          <div>
            <dt>PKB nguồn</dt>
            <dd>
              v{asset.knowledgeVersion} · {pkb?.status ?? "không tìm thấy"}
            </dd>
          </div>
          <div>
            <dt>Kiểm duyệt</dt>
            <dd>{videoLabels[asset.status]}</dd>
          </div>
          {asset.firstApprovedAt && (
            <div>
              <dt>Duyệt lần đầu</dt>
              <dd>
                {asset.firstApprovedAt} · {asset.reviewedBy}
              </dd>
            </div>
          )}
        </dl>
        {admin && project && (
          <Link
            className="asset-link"
            href={`/admin/pkb/${project.id}`}
          >
            Đối chiếu PKB
            <ArrowRight size={14} />
          </Link>
        )}
        <details className="portal-spacing">
          <summary>PKB snapshot v{asset.knowledgeVersion}</summary>
          <p className="caption-preview">
            Tính năng: {pkb?.data.facts.features.value || "Chưa có"}
            <br />
            Giá:{" "}
            {pkb?.data.pricing.plans.map((plan) => plan.priceText).join("; ") ||
              "Chưa có"}
            <br />
            Forbidden claims:{" "}
            {pkb?.data.facts.forbiddenClaims.value || "Chưa có"}
          </p>
        </details>
        <h3 className="portal-spacing">Caption mẫu</h3>
        <p className="caption-preview">{distributionCaption(asset)}</p>
        {asset.reason && (
          <p className="report-box">
            {asset.status === "archived" ? "Lý do lưu trữ" : "Lý do từ chối"}:{" "}
            {asset.reason}
          </p>
        )}
        {asset.flaggedAt && (
          <p className="report-box">
            Merchant báo sai: {asset.flagReason}
            <br />
            Thời điểm: {asset.flaggedAt}
          </p>
        )}
        {!admin && asset.status === "approved" && (
          <div className="portal-actions">
            <a
              className="portal-primary"
              href={asset.review.videoUrl!}
              download={`${asset.review.id}-demo.mp4`}
            >
              <Download size={15} />
              Tải video demo
            </a>
            <Button variant="outline" onClick={downloadCaption}>
              Tải caption
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                void copy(distributionCaption(asset));
              }}
            >
              Copy Caption / Hashtags
            </Button>
          </div>
        )}
        {!admin && asset.status !== "approved" && (
          <p className="panel-description">
            {asset.status === "archived"
              ? "Video đã lưu trữ, không thể tải để phát hành mới."
              : "Nội dung chưa được duyệt, chưa thể tải để sử dụng."}
          </p>
        )}
      </section>
      <section className="portal-panel">
        <h2>
          {admin ? "Quyết định QA" : "Tracking cá nhân"}
        </h2>
        <p className="panel-description">
          {admin
            ? "Kiểm tra từng mục trước khi duyệt. Từ chối cần lý do để Merchant biết phần cần sửa."
            : "Tham gia campaign và dùng link tracking mẫu để thử luồng phân phối."}
        </p>
        {admin ? (
          <>
            <div className="qa-checklist">
              {checks.map((check) => (
                <label key={check.key}>
                  <input
                    type="checkbox"
                    checked={checklist[check.key]}
                    disabled={!actionable}
                    onChange={(e) =>
                      setChecklist((current) => ({
                        ...current,
                        [check.key]: e.target.checked,
                      }))
                    }
                  />
                  {check.label}
                </label>
              ))}
            </div>
            {actionable ? (
              <>
                {pkb?.status !== "approved" && (
                  <p className="report-box">
                    PKB nguồn chưa được Merchant duyệt. Chưa thể duyệt video
                    này.
                  </p>
                )}
                <label className="portal-label" htmlFor="qa-reason">
                  {previouslyApproved ? "Lý do lưu trữ" : "Lý do từ chối"}
                </label>
                <Textarea
                  id="qa-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Nêu thông tin sai và phần cần sửa…"
                />
                <div className="portal-actions">
                  <Button
                    disabled={
                      pkb?.status !== "approved" ||
                      !checks.every(({ key }) => checklist[key])
                    }
                    onClick={() =>
                      run(
                        () =>
                          updateVideo(asset.review.id, (current) =>
                            decideVideo(
                              current,
                              "approved",
                              checklist,
                              "",
                              pkb?.status === "approved",
                            ),
                          ),
                        "Đã duyệt video demo.",
                      )
                    }
                  >
                    {asset.flaggedAt
                      ? "Giữ duyệt, đóng báo sai"
                      : "Duyệt video"}
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!reason.trim()}
                    onClick={() =>
                      run(
                        () =>
                          updateVideo(asset.review.id, (current) =>
                            decideVideo(
                              current,
                              previouslyApproved ? "archived" : "rejected",
                              checklist,
                              reason,
                              pkb?.status === "approved",
                            ),
                          ),
                        previouslyApproved
                          ? "Đã lưu trữ video demo."
                          : "Đã từ chối video demo.",
                      )
                    }
                  >
                    {previouslyApproved ? "Lưu trữ video" : "Từ chối video"}
                  </Button>
                </div>
              </>
            ) : (
              <p className="panel-description">
                {asset.status === "archived"
                  ? "Video đã lưu trữ, không thể duyệt lại. Tạo bản video mới nếu cần sửa nội dung."
                  : "Video đã được xử lý. Khi Merchant báo sai, video sẽ quay lại hàng đợi."}
              </p>
            )}
          </>
        ) : (
          <>
            <p>
              Creator demo · Link chia sẻ dùng slug; click_id sẽ do backend cấp
              cho từng click.
            </p>
            {project?.campaign?.active &&
            project.campaign.joined &&
            asset.status === "approved" ? (
              <>
                <Input
                  readOnly
                  aria-label="Tracking link cá nhân"
                  value={`https://tracking.example/r/demo-${asset.review.id}`}
                />
                <Button
                  variant="outline"
                  onClick={() => {
                    void copy(
                      `https://tracking.example/r/demo-${asset.review.id}`,
                    );
                  }}
                >
                  Copy tracking link
                </Button>
                <p className="demo-note">
                  Link mẫu chưa có redirect hoặc ghi nhận click thật.
                </p>
              </>
            ) : (
              <p>
                Tham gia campaign đang mở để nhận link.{" "}
                <Link href="/creator/campaigns">Mở campaigns</Link>
              </p>
            )}
          </>
        )}
        {failure && (
          <p className="form-error" role="alert">
            {failure}
          </p>
        )}
        {message && (
          <p className="notice" role="status">
            {message}
          </p>
        )}
      </section>
    </div>
  );
}
