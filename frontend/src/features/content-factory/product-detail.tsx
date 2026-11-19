"use client";

import Link from "next/link";
import Image from "next/image";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { openUpload } from "./uploads";
import { useWorkspace } from "./workspace-provider";
import {
  updatePricingMeta,
  changeJob,
  startRecrawl,
  knowledgeErrors,
  knowledgeFields,
  latestKnowledge,
  newDraft,
  saveKnowledge,
  transitionKnowledge,
  type Fact,
  type KnowledgeData,
  type KnowledgeField,
  type KnowledgeVersion,
  type PricingPlan,
  type Project,
} from "./model";
import { confirmDiscard, useUnsavedChanges } from "./use-unsaved-changes";

const statusLabels = {
  draft: "Bản nháp",
  in_review: "Đang review",
  approved: "Đã duyệt",
  rejected: "Từ chối",
};

export function ProductDetail({
  id,
}: {
  id: string;
}) {
  const productPath = "/admin/pkb";
  const { projects, ready, storageError } = useWorkspace();
  const project = projects.find((p) => p.id === id);
  if (!ready) return <p role="status">Đang khôi phục sản phẩm…</p>;
  if (!project)
    return (
      <section className="empty-list">
        <h1>Không tìm thấy sản phẩm</h1>
        <Link href={productPath}>Về danh sách sản phẩm</Link>
      </section>
    );
  return (
    <>
      <Link href={productPath} className="back-link">
        ← Danh sách sản phẩm
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">
            ADMIN · KIỂM TRA CHÍNH SÁCH
          </p>
          <div className="product-title">
            <Image
              unoptimized
              src={project.merchantInput?.logo || "/media/product-mark.svg"}
              alt="Logo sản phẩm"
              width={48}
              height={48}
            />
            <h1>{project.name}</h1>
          </div>
          <p>
            Product: {project.status} · PKB đã duyệt hiện tại:{" "}
            {project.currentKnowledgeVersion
              ? `v${project.currentKnowledgeVersion}`
              : "chưa có"}
          </p>
        </div>
      </div>
      <p className="review-demo-banner">
        Mock M1 · Vai trò và duyệt chỉ mô phỏng giao diện. PKB tiếng Anh;
        nguồn/giá là dữ liệu minh họa chưa xác minh.
      </p>
      {storageError && (
        <p role="alert" className="form-error">
          {storageError}
        </p>
      )}
      <ProductWorkspace key={id} project={project} actor="admin" />
    </>
  );
}
function ProductWorkspace({
  project,
  actor,
}: {
  project: Project;
  actor?: "merchant" | "admin";
}) {
  const { updateProject } = useWorkspace();
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [error, setError] = useState("");
  const latest = latestKnowledge(project);
  const version =
    project.knowledge.find((v) => v.version === selectedVersion) ?? latest;
  function jobAction(status: Project["job"]["status"]) {
    try {
      updateProject(project.id, (p) => changeJob(p, status));
      setError("");
      setSelectedVersion(null);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Không thể cập nhật job.",
      );
    }
  }
  return (
    <>
      <section className="pkb-identity">
        <div>
          <span>Website URL</span>
          <a href={project.url} target="_blank" rel="noopener noreferrer">
            {project.url} ↗
          </a>
        </div>
        <div>
          <span>Merchant affiliate URL</span>
          <a href={project.affiliate} target="_blank" rel="noopener noreferrer">
            {project.affiliate} ↗
          </a>
        </div>
      </section>
      <section className="job-panel" aria-label="Job crawl mock">
        <div className="section-title">
          <h2>Job crawl</h2>
          <span
            className={`state-tag ${project.job.status === "completed" ? "ready" : ""}`}
          >
            {project.job.status}
          </span>
        </div>
        <p>{project.job.step}</p>
        <small>
          Job {project.job.id} · số lần thử: {project.job.attempts}
        </small>
        {project.job.error && (
          <p role="alert" className="form-error">
            {project.job.error}
          </p>
        )}
        {actor !== "admin" && project.job.status !== "completed" && (
          <details className="mock-job-controls" open>
            <summary>Điều khiển job mock</summary>
            <p>
              Chọn trạng thái để kiểm tra UI. Không có crawler hoặc thời gian
              hoàn tất thật.
            </p>
            <div className="pkb-actions">
              {["queued", "failed"].includes(project.job.status) && (
                <Button onClick={() => jobAction("running")}>
                  {project.job.status === "failed"
                    ? "Thử lại job mock"
                    : "Bắt đầu job mock"}
                </Button>
              )}
              {project.job.status === "running" && (
                <>
                  <Button onClick={() => jobAction("completed")}>
                    Hoàn tất job mock
                  </Button>
                  <Button variant="outline" onClick={() => jobAction("failed")}>
                    Mô phỏng lỗi crawl
                  </Button>
                </>
              )}
            </div>
          </details>
        )}
      </section>
      {project.merchantInput?.uploads.length ? (
        <section className="portal-panel portal-spacing">
          <h3>Tài liệu Merchant cung cấp</h3>
          {project.merchantInput.uploads.map((file) => (
            <Button
              key={file.id}
              variant="ghost"
              onClick={() => {
                void openUpload(file).catch((cause) => setError(cause.message));
              }}
            >
              {file.name}
            </Button>
          ))}
          <p className="demo-note">
            File được giữ trong trình duyệt; dữ liệu PKB vẫn là template mock.
          </p>
        </section>
      ) : null}
      {actor !== "admin" && (
        <Button
          className="portal-spacing"
          variant="outline"
          disabled={
            ["queued", "running"].includes(project.job.status) ||
            (!!latest && ["draft", "in_review"].includes(latest.status))
          }
          onClick={() => {
            try {
              updateProject(project.id, startRecrawl);
              setError("");
            } catch (cause) {
              setError(
                cause instanceof Error ? cause.message : "Không thể cào lại.",
              );
            }
          }}
        >
          Cào lại website (mock)
        </Button>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {version ? (
        <KnowledgeEditor
          key={`${project.id}-${version.version}`}
          project={project}
          version={version}
          latest={version.version === latest?.version}
          selectedVersion={version.version}
          onSelectVersion={setSelectedVersion}
          onNewVersion={() => setSelectedVersion(null)}
          actor={actor}
        />
      ) : (
        <div className="empty-list">
          <h2>Chưa có PKB</h2>
          <p>Hoàn tất job mock để tạo draft tiếng Anh.</p>
        </div>
      )}
    </>
  );
}
function KnowledgeEditor({
  project,
  version,
  latest,
  selectedVersion,
  onSelectVersion,
  onNewVersion,
  actor,
}: {
  project: Project;
  version: KnowledgeVersion;
  latest: boolean;
  selectedVersion: number;
  onSelectVersion: (version: number) => void;
  onNewVersion: () => void;
  actor?: "merchant" | "admin";
}) {
  const {
    role: demoRole,
    setRole,
    updateProject,
  } = useWorkspace();
  const role = actor ?? demoRole;
  const [data, setData] = useState<KnowledgeData>(() =>
    structuredClone(version.data),
  );
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const editable = latest && version.status === "draft" && role === "merchant";
  const dirty = JSON.stringify(data) !== JSON.stringify(version.data);
  useUnsavedChanges(dirty);
  const validation = knowledgeErrors({ ...version, data });
  function action(callback: () => void, message: string) {
    try {
      callback();
      setError("");
      setMessage(message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể lưu.");
      setMessage("");
    }
  }
  function updateFact(key: KnowledgeField, value: string) {
    setData((current) => ({
      ...current,
      facts: {
        ...current.facts,
        [key]: { value, origin: "merchant", sourceId: null, evidence: "" },
      },
    }));
  }
  function updatePlan(index: number, patch: Partial<PricingPlan>) {
    setData((current) => ({
      ...current,
      pricing: {
        ...current.pricing,
        plans: current.pricing.plans.map((p, i) =>
          i === index
            ? {
                ...p,
                ...patch,
                ...(patch.listPrice !== undefined
                  ? { priceConfirmed: true }
                  : {}),
                origin: "merchant",
                sourceId: null,
                evidence: "",
              }
            : p,
        ),
      },
    }));
  }
  return (
    <section className="pkb-section">
      <div className="section-heading">
        <div>
          <h2>Product Knowledge Base</h2>
          <span
            className={`status-chip ${version.status}`}
            aria-label="Trạng thái PKB"
          >
            {version.status === "approved"
              ? "Approved"
              : statusLabels[version.status]}{" "}
            v{version.version}
          </span>
          <p>
            v{version.version} · {statusLabels[version.status]} · English
            {dirty ? " · Có thay đổi chưa lưu" : " · Bản đã lưu"}
          </p>
        </div>
        <div className="pkb-selectors">
          <div>
            <label htmlFor="pkb-version">Phiên bản PKB</label>
            <select
              id="pkb-version"
              value={selectedVersion}
              onChange={(e) => {
                if (confirmDiscard(dirty))
                  onSelectVersion(Number(e.target.value));
              }}
            >
              {[...project.knowledge].reverse().map((v) => (
                <option key={v.version} value={v.version}>
                  v{v.version} · {v.status}
                </option>
              ))}
            </select>
          </div>
          {!actor && (
            <div>
              <label htmlFor="demo-role">Vai trò demo</label>
              <select
                id="demo-role"
                value={role}
                onChange={(e) => {
                  if (!dirty)
                    action(
                      () => setRole(e.target.value as "merchant" | "admin"),
                      "Đã đổi vai trò demo.",
                    );
                  else setError("Lưu hoặc bỏ thay đổi trước khi đổi vai trò.");
                }}
              >
                <option value="merchant">Merchant</option>
                <option value="admin">Admin (chỉ từ chối PKB)</option>
              </select>
            </div>
          )}
        </div>
      </div>
      {version.status === "approved" && (
        <p className="pkb-readonly">
          Tri thức đã được khóa để đưa vào sản xuất video. Bản đã duyệt chỉ đọc
          · Người duyệt: merchant demo · {version.approvedAt}. Muốn sửa, hãy tạo
          draft mới.
        </p>
      )}
      {version.rejectionReason && (
        <p className="form-error">Lý do từ chối: {version.rejectionReason}</p>
      )}
      <div className="pkb-grid">
        {knowledgeFields
          .filter((field) => field.key === "description")
          .map(({ key, label }) => (
            <article className="fact-panel" key={key}>
              <label htmlFor={`pkb-${key}`}>{label}</label>
              {editable ? (
                <Textarea
                  id={`pkb-${key}`}
                  value={data.facts[key].value}
                  placeholder="Chưa có thông tin"
                  onChange={(e) => updateFact(key, e.target.value)}
                />
              ) : (
                <div className="fact-value" id={`pkb-${key}`}>
                  {data.facts[key].value || "Chưa có thông tin"}
                </div>
              )}
              <FactSource
                fact={data.facts[key]}
                sources={version.sources}
                approved={version.status === "approved"}
              />
            </article>
          ))}
      </div>
      <Dialog>
        <DialogTrigger render={<Button variant="outline" />}>
          Lịch sử thay đổi
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Lịch sử PKB · {project.name}</DialogTitle>
          <DialogDescription>
            Mỗi lần duyệt giữ nguyên snapshot trước đó.
          </DialogDescription>
          {project.knowledge.map((item, i) => (
            <article className="history-item" key={item.version}>
              <strong>
                v{item.version} · {statusLabels[item.status]}
              </strong>
              <p>
                {item.updatedAt} · {item.approvedBy || "chưa duyệt"}
              </p>
              {i > 0 && (
                <ul>
                  {knowledgeFields
                    .filter(
                      (field) =>
                        item.data.facts[field.key].value !==
                        project.knowledge[i - 1].data.facts[field.key].value,
                    )
                    .map((field) => (
                      <li key={field.key}>
                        {field.label}:{" "}
                        {project.knowledge[i - 1].data.facts[field.key].value ||
                          "(trống)"}{" "}
                        → {item.data.facts[field.key].value || "(trống)"}
                      </li>
                    ))}
                  {JSON.stringify(item.data.pricing) !==
                    JSON.stringify(project.knowledge[i - 1].data.pricing) && (
                    <li>
                      Giá / gói thay đổi:{" "}
                      {project.knowledge[i - 1].data.pricing.plans
                        .map((p) => p.priceText)
                        .join("; ")}{" "}
                      →{" "}
                      {item.data.pricing.plans
                        .map((p) => p.priceText)
                        .join("; ")}
                    </li>
                  )}
                </ul>
              )}
            </article>
          ))}
        </DialogContent>
      </Dialog>
      {data.conflicts?.map((conflict, index) => (
        <fieldset className="conflict-panel" key={conflict.field}>
          <legend>Xung đột · {conflict.field}</legend>
          <p>Chọn giá trị giữ lại. Merchant được ưu tiên nhưng cần xác nhận.</p>
          {editable ? (
            (["merchant", "crawled"] as const).map((choice) => (
              <label key={choice}>
                <input
                  type="radio"
                  name={`conflict-${index}`}
                  checked={conflict.resolved === choice}
                  disabled={!editable}
                  onChange={() =>
                    setData((current) => {
                      const next = structuredClone(current);
                      next.conflicts![index].resolved = choice;
                      if (conflict.field === "pricing") {
                        const plan = next.pricing.plans[0];
                        if (choice === "crawled" && conflict.crawledPlan)
                          Object.assign(
                            plan,
                            structuredClone(conflict.crawledPlan),
                          );
                        plan.priceText = conflict[choice];
                        plan.priceConfirmed = choice === "crawled";
                        plan.origin = choice;
                        plan.sourceId = choice === "crawled" ? "pricing" : null;
                        plan.evidence =
                          choice === "crawled"
                            ? "Mock pricing excerpt; not the product's actual price."
                            : "";
                      } else
                        next.facts[conflict.field] = {
                          value: conflict[choice],
                          origin: choice,
                          sourceId: choice === "crawled" ? "homepage" : null,
                          evidence:
                            choice === "crawled"
                              ? "Sample website excerpt, not collected from the website."
                              : "",
                        };
                      return next;
                    })
                  }
                />
                {choice === "merchant" ? "Merchant" : "Website (mock)"}:{" "}
                {conflict[choice]}
              </label>
            ))
          ) : (
            <p>
              Giá trị đã chọn ({conflict.resolved}):{" "}
              {conflict.resolved
                ? conflict[conflict.resolved]
                : "Chưa giải quyết"}
            </p>
          )}
          {editable && conflict.resolved && (
            <small>Đã chọn {conflict.resolved} · lưu draft để xác nhận</small>
          )}
        </fieldset>
      ))}
      <Tabs defaultValue="pricing">
        <TabsList className="pkb-tabs" aria-label="Nhóm thông tin PKB">
          <TabsTrigger value="pricing">Giá & Gói</TabsTrigger>
          <TabsTrigger value="features">Tính năng</TabsTrigger>
          <TabsTrigger value="audience">Đối tượng / JTBD</TabsTrigger>
          <TabsTrigger value="brand">Thương hiệu & USP</TabsTrigger>
        </TabsList>
        <TabsContent value="pricing">
          <section className="pricing-panel">
            <h3>Giá / Gói</h3>
            <p>
              Vùng giá: {data.pricing.region} · {data.pricing.currency} ·{" "}
              {data.pricing.locale}. Giá có thể khác theo quốc gia.
            </p>
            <p>
              Chu kỳ khác:{" "}
              {(data.pricing.otherViews ?? ["yearly", "quarterly"]).join(", ")}{" "}
              · Không tự quy đổi.
            </p>
            <div className="table-scroll">
              <table className="leader-table">
                <thead>
                  <tr>
                    {[
                      "Gói",
                      "Niêm yết",
                      "Khuyến mãi",
                      "Chu kỳ",
                      "Đơn vị",
                      "Giới hạn",
                    ].map((label) => (
                      <th key={label}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.pricing.plans.map((plan, i) => (
                    <tr key={i}>
                      <td>{plan.name}</td>
                      <td>
                        {plan.listPrice}{" "}
                        {plan.currency || data.pricing.currency}
                      </td>
                      <td>
                        {plan.promoPrice === null
                          ? "—"
                          : `${plan.promoPrice} ${plan.currency || data.pricing.currency}`}
                        <small>{plan.promoTerms}</small>
                      </td>
                      <td>{plan.billingCycle}</td>
                      <td>{plan.priceUnit}</td>
                      <td>{plan.limits || "Chưa có thông tin"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="demo-note">
              Giá minh họa để kiểm tra UI, không phải giá thực tế. Không tự quy
              đổi giá theo chu kỳ.
            </p>
            <div>
              {editable && (
                <>
                  <div className="pricing-meta">
                    {(
                      ["currency", "region", "locale", "defaultView"] as const
                    ).map((key) => (
                      <div key={key}>
                        <label htmlFor={`pricing-${key}`}>
                          {
                            {
                              currency: "Tiền tệ",
                              region: "Vùng giá",
                              locale: "Locale",
                              defaultView: "Tab giá mặc định",
                            }[key]
                          }
                        </label>
                        <Input
                          id={`pricing-${key}`}
                          value={data.pricing[key]}
                          disabled={!editable}
                          onChange={(e) =>
                            setData((current) =>
                              updatePricingMeta(current, key, e.target.value),
                            )
                          }
                        />
                      </div>
                    ))}
                  </div>
                  {data.pricing.plans.map((plan, index) => (
                    <div className="pricing-plan" key={index}>
                      <div className="pricing-meta">
                        <div>
                          <label htmlFor={`plan-name-${index}`}>Tên gói</label>
                          <Input
                            id={`plan-name-${index}`}
                            value={plan.name}
                            disabled={!editable}
                            onChange={(e) =>
                              updatePlan(index, { name: e.target.value })
                            }
                          />
                        </div>
                        <div>
                          <label htmlFor={`plan-price-${index}`}>
                            Giá niêm yết
                          </label>
                          <Input
                            id={`plan-price-${index}`}
                            type="number"
                            min={0}
                            step="any"
                            value={plan.listPrice}
                            disabled={!editable}
                            onChange={(e) =>
                              updatePlan(index, {
                                listPrice: Number(e.target.value),
                              })
                            }
                          />
                        </div>
                        <div>
                          <label htmlFor={`plan-promo-${index}`}>
                            Giá khuyến mãi (tùy chọn)
                          </label>
                          <Input
                            id={`plan-promo-${index}`}
                            type="number"
                            min={0}
                            step="any"
                            value={plan.promoPrice ?? ""}
                            disabled={!editable}
                            onChange={(e) =>
                              updatePlan(index, {
                                promoPrice: e.target.value
                                  ? Number(e.target.value)
                                  : null,
                              })
                            }
                          />
                        </div>
                        <div>
                          <label htmlFor={`plan-terms-${index}`}>
                            Điều kiện khuyến mãi
                          </label>
                          <Input
                            id={`plan-terms-${index}`}
                            value={plan.promoTerms}
                            disabled={!editable}
                            onChange={(e) =>
                              updatePlan(index, { promoTerms: e.target.value })
                            }
                          />
                        </div>
                        <div>
                          <label htmlFor={`plan-unit-${index}`}>
                            Đơn vị giá
                          </label>
                          <select
                            id={`plan-unit-${index}`}
                            value={plan.priceUnit}
                            disabled={!editable}
                            onChange={(e) =>
                              updatePlan(index, {
                                priceUnit: e.target
                                  .value as PricingPlan["priceUnit"],
                              })
                            }
                          >
                            <option value="month">month</option>
                            <option value="year">year</option>
                            <option value="seat_month">seat_month</option>
                            <option value="seat_year">seat_year</option>
                            <option value="one_time">one_time</option>
                          </select>
                        </div>
                        <div>
                          <label htmlFor={`plan-cycle-${index}`}>
                            Chu kỳ thanh toán
                          </label>
                          <select
                            id={`plan-cycle-${index}`}
                            value={plan.billingCycle}
                            disabled={!editable}
                            onChange={(e) =>
                              updatePlan(index, {
                                billingCycle: e.target
                                  .value as PricingPlan["billingCycle"],
                              })
                            }
                          >
                            <option value="monthly">monthly</option>
                            <option value="yearly">yearly</option>
                            <option value="quarterly">quarterly</option>
                            <option value="one_time">one_time</option>
                          </select>
                        </div>
                      </div>
                      <label htmlFor={`plan-limits-${index}`}>
                        Giới hạn sử dụng
                      </label>
                      <Input
                        id={`plan-limits-${index}`}
                        value={plan.limits ?? ""}
                        disabled={!editable}
                        onChange={(e) =>
                          updatePlan(index, { limits: e.target.value })
                        }
                      />
                      <label htmlFor={`plan-text-${index}`}>
                        price_text nguyên văn
                      </label>
                      <Textarea
                        id={`plan-text-${index}`}
                        value={plan.priceText}
                        disabled={!editable}
                        onChange={(e) =>
                          updatePlan(index, { priceText: e.target.value })
                        }
                      />
                      <FactSource
                        fact={{
                          value: plan.priceText,
                          origin: plan.origin,
                          sourceId: plan.sourceId,
                          evidence: plan.evidence,
                        }}
                        sources={version.sources}
                      />
                      {editable && data.pricing.plans.length > 1 && (
                        <Button
                          variant="outline"
                          onClick={() =>
                            setData((current) => ({
                              ...current,
                              pricing: {
                                ...current.pricing,
                                plans: current.pricing.plans.filter(
                                  (_, i) => i !== index,
                                ),
                              },
                            }))
                          }
                        >
                          Xóa gói giá
                        </Button>
                      )}
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    onClick={() =>
                      setData((current) => ({
                        ...current,
                        pricing: {
                          ...current.pricing,
                          plans: [
                            ...current.pricing.plans,
                            {
                              name: "New plan",
                              listPrice: 0,
                              promoPrice: null,
                              promoTerms: "",
                              priceUnit: "month",
                              billingCycle: "monthly",
                              priceText: "Unverified merchant draft",
                              origin: "merchant",
                              sourceId: null,
                              evidence: "",
                              limits: "",
                              currency: current.pricing.currency,
                            },
                          ],
                        },
                      }))
                    }
                  >
                    Thêm gói giá
                  </Button>
                </>
              )}
              {!editable &&
                data.pricing.plans.map((plan, i) => (
                  <div key={i} className="pricing-plan">
                    <strong>{plan.name}</strong>
                    <p>{plan.priceText}</p>
                    <FactSource
                      fact={{
                        value: plan.priceText,
                        origin: plan.origin,
                        sourceId: plan.sourceId,
                        evidence: plan.evidence,
                      }}
                      sources={version.sources}
                    />
                  </div>
                ))}
            </div>
            <h4>Giá theo mức sử dụng</h4>
            {(data.pricing.usagePrices ?? []).map((item, i) => (
              <p key={i}>
                {item.name}: {item.price} {item.currency} / {item.unit}
              </p>
            ))}
            {!data.pricing.usagePrices?.length && (
              <p>Chưa có thông tin usage price.</p>
            )}
          </section>
        </TabsContent>
        {["features", "audience", "brand"].map((tab) => (
          <TabsContent value={tab} key={tab}>
            <div>
              {tab === "brand" && (
                <p className="brand-note">
                  Tagline:{" "}
                  {data.tagline || project.merchantInput?.tagline || "Chưa có"}{" "}
                  · Màu thương hiệu:{" "}
                  {data.color || project.merchantInput?.color || "#333333"}
                </p>
              )}
              <div className="pkb-grid">
                {knowledgeFields
                  .filter(({ key }) =>
                    tab === "features"
                      ? ["features", "models"].includes(key)
                      : tab === "audience"
                        ? ["audiences", "useCases"].includes(key)
                        : [
                            "brand",
                            "usp",
                            "limitations",
                            "approvedClaims",
                            "forbiddenClaims",
                          ].includes(key),
                  )
                  .map(({ key, label }) => (
                    <article className="fact-panel" key={key}>
                      <label htmlFor={`pkb-${key}`}>{label}</label>
                      {editable ? (
                        <Textarea
                          id={`pkb-${key}`}
                          value={data.facts[key].value}
                          onChange={(e) => updateFact(key, e.target.value)}
                        />
                      ) : (
                        <div className="fact-value">
                          {data.facts[key].value || "Chưa có thông tin"}
                        </div>
                      )}
                      <FactSource
                        fact={data.facts[key]}
                        sources={version.sources}
                        approved={version.status === "approved"}
                      />
                    </article>
                  ))}
              </div>
              {tab === "features" && (
                <div className="feature-grid">
                  {data.facts.features.value
                    .split("\n")
                    .filter(Boolean)
                    .map((name, i) => (
                      <article className="fact-panel" key={i}>
                        <Image
                          src="/media/feature-evidence.svg"
                          alt={`Screenshot minh họa: ${name}`}
                          width={480}
                          height={270}
                        />
                        <h3>{name}</h3>
                        <p>
                          Screenshot mẫu để kiểm tra bố cục; chưa có ảnh crawl
                          thực.
                        </p>
                        <FactSource
                          fact={data.facts.features}
                          sources={version.sources}
                        />
                      </article>
                    ))}
                </div>
              )}
            </div>
          </TabsContent>
        ))}
      </Tabs>
      <section className="sources-panel">
        <h3>Nguồn / Evidence</h3>
        <p className="demo-note">
          Các URL và excerpt dưới đây là tham chiếu mock, chưa được crawl; ảnh
          trong tab tính năng là screenshot mẫu, chưa phải bằng chứng crawl.
        </p>
        {version.sources.map((source) => (
          <div key={source.id}>
            <strong>
              {source.id} · {source.pageType}
            </strong>
            <a href={source.url} target="_blank" rel="noopener noreferrer">
              {source.url} ↗
            </a>
            <small>Ngày crawl / hash: chưa có trong mock</small>
          </div>
        ))}
      </section>
      {editable && validation.length > 0 && (
        <div className="validation-panel">
          <strong>Cần bổ sung trước khi gửi duyệt:</strong>
          <ul>
            {validation.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="pkb-actions">
        {editable && (
          <>
            <Button
              variant="outline"
              onClick={() =>
                document.getElementById("pkb-description")?.focus()
              }
            >
              Chỉnh sửa trực tiếp
            </Button>
            <Button
              disabled={!dirty}
              onClick={() =>
                action(
                  () =>
                    updateProject(project.id, (p) =>
                      saveKnowledge(p, data, version.updatedAt),
                    ),
                  "Đã lưu draft trong trình duyệt.",
                )
              }
            >
              Lưu draft
            </Button>
            <Button
              variant="outline"
              disabled={!dirty}
              onClick={() => {
                if (confirmDiscard(dirty)) {
                  setData(structuredClone(version.data));
                  setError("");
                }
              }}
            >
              Bỏ thay đổi
            </Button>
            <Button
              variant="outline"
              disabled={dirty || validation.length > 0}
              onClick={() =>
                action(
                  () =>
                    updateProject(project.id, (p) =>
                      transitionKnowledge(p, "in_review", role),
                    ),
                  "PKB đã chuyển sang in_review.",
                )
              }
            >
              Gửi review
            </Button>
          </>
        )}
        {latest && version.status === "in_review" && (
          <>
            {role === "merchant" && (
              <Button
                onClick={() => {
                  if (
                    window.confirm(
                      "Duyệt PKB mẫu này? Bản đã duyệt sẽ chỉ đọc; các suy luận được xác nhận trong phạm vi demo.",
                    )
                  )
                    action(
                      () =>
                        updateProject(project.id, (p) =>
                          transitionKnowledge(p, "approved", role),
                        ),
                      "Đã duyệt PKB mock; giữ snapshot bất biến.",
                    );
                }}
              >
                Merchant duyệt PKB
              </Button>
            )}
            {role === "admin" && (
              <>
                <div className="reject-input">
                  <label htmlFor="reject-reason">Lý do từ chối</label>
                  <Input
                    id="reject-reason"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                  />
                </div>
                <Button
                  variant="outline"
                  disabled={!rejectReason.trim()}
                  onClick={() =>
                    action(
                      () =>
                        updateProject(project.id, (p) =>
                          transitionKnowledge(
                            p,
                            "rejected",
                            role,
                            rejectReason,
                          ),
                        ),
                      "Đã từ chối PKB mock.",
                    )
                  }
                >
                  Từ chối PKB
                </Button>
              </>
            )}
          </>
        )}
        {latest &&
          role === "merchant" &&
          ["approved", "rejected"].includes(version.status) && (
            <Button
              onClick={() =>
                action(() => {
                  updateProject(project.id, (p) => newDraft(p, role));
                  onNewVersion();
                }, "Đã tạo draft mới. Phiên bản trước được giữ nguyên.")
              }
            >
              Tạo draft mới
            </Button>
          )}

      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="notice">
          {message}
        </p>
      )}
    </section>
  );
}
function FactSource({
  fact,
  sources,
  approved = false,
}: {
  fact: Fact;
  sources: KnowledgeVersion["sources"];
  approved?: boolean;
}) {
  const source = sources.find((s) => s.id === fact.sourceId);
  const label = {
    crawled: "Website (mock)",
    merchant: "Merchant nhập",
    inferred: "AI suy luận (mock)",
  }[fact.origin];
  return (
    <div className="fact-source">
      <span className={`origin-tag origin-${fact.origin}`}>{label}</span>
      {fact.origin === "inferred" && (
        <small>
          {approved
            ? "Đã được Merchant xác nhận (mock)."
            : "Cần Merchant xác nhận."}
        </small>
      )}
      <Popover>
        <PopoverTrigger render={<Button size="sm" variant="ghost" />}>
          Nguồn / Evidence
        </PopoverTrigger>
        <PopoverContent>
          <strong>{label}</strong>
          {source ? (
            <a href={source.url} target="_blank" rel="noopener noreferrer">
              {source.url} ↗
            </a>
          ) : (
            <p>
              {fact.origin === "merchant"
                ? "Merchant nhập; không có nguồn website."
                : "Suy luận mẫu; chưa có bằng chứng."}
            </p>
          )}
          <p>{fact.evidence.slice(0, 200) || "Không có excerpt."}</p>
          <small>Evidence tối đa 200 ký tự · nguồn minh họa</small>
        </PopoverContent>
      </Popover>
    </div>
  );
}
