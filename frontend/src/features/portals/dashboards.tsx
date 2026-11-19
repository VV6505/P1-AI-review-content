"use client";

import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useWorkspace } from "../content-factory/workspace-provider";
import { latestKnowledge } from "../content-factory/model";
import { useVideos } from "../video-qa/provider";

export function DemoNotice() {
  return <p className="review-demo-banner">Bản demo local · Dữ liệu mẫu và thao tác lưu trong trình duyệt. Chuyển khu vực để thử vai trò, chưa có đăng nhập hoặc phân quyền thật.</p>;
}
export function AdminDashboard() {
  const { assets, ready, error } = useVideos();
  const { projects } = useWorkspace();
  const pending = assets.filter(a => a.status === "pending_review" || a.flaggedAt);
  return <>
    <div className="page-heading"><div><p className="eyebrow">ADMIN · KIỂM DUYỆT NỀN TẢNG</p><h1>Tổng quan QA</h1><p>Kiểm duyệt video và xử lý báo sai từ Merchant.</p></div><Link className="portal-primary" href="/admin/videos"><ShieldCheck size={16} />Mở hàng đợi QA</Link></div>
    <DemoNotice />{error && <p role="alert" className="form-error">{error}</p>}
    {!ready ? <p role="status">Đang khôi phục hàng đợi…</p> : <>
      <section className="overview-grid" aria-label="Tình trạng Admin">{[{ label: "Video chờ duyệt", value: assets.filter(a => a.status === "pending_review").length, href: "/admin/videos" }, { label: "Báo sai từ Merchant", value: assets.filter(a => a.flaggedAt).length, href: "/admin/videos" }, { label: "PKB đang review", value: projects.filter(p => latestKnowledge(p)?.status === "in_review").length, href: "/admin/pkb" }].map(item => <Link className="overview-card" href={item.href} key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>Kiểm tra hàng đợi<ArrowRight size={14} /></small></Link>)}</section>
      <section className="portal-panel portal-spacing"><div className="section-heading"><div><h2>Cần kiểm duyệt</h2><p>Admin duyệt video; Merchant tự duyệt PKB của mình.</p></div></div>{pending.length ? pending.map(a => <Link className="task-row" href={`/admin/videos/${a.review.id}`} key={a.review.id}><span><strong>{a.review.title}</strong><small>{a.flaggedAt ? `Merchant báo sai: ${a.flagReason}` : `${a.review.product} · PKB v${a.knowledgeVersion}`}</small></span><span className={`status-chip ${a.flaggedAt ? "flagged" : "pending_review"}`}>{a.flaggedAt ? "Cần kiểm tra lại" : "Chờ duyệt"}</span></Link>) : <div className="empty-list"><p>Đã xử lý hết hàng đợi.</p></div>}</section>
    </>}
  </>;
}
export function AdminPkbList() {
  const { projects, ready, storageError } = useWorkspace();
  return <><div className="page-heading"><div><p className="eyebrow">ADMIN · CHÍNH SÁCH</p><h1>Kiểm tra PKB</h1><p>Chỉ từ chối bản đang review khi vi phạm chính sách, kèm lý do. Quyền duyệt thuộc Merchant.</p></div></div><DemoNotice />{storageError && <p role="alert" className="form-error">{storageError}</p>}{!ready ? <p role="status">Đang tải PKB…</p> : <section className="portal-panel">{projects.filter(p => latestKnowledge(p)?.status === "in_review").map(p => <Link className="task-row" key={p.id} href={`/admin/pkb/${p.id}`}><span><strong>{p.name}</strong><small>PKB v{latestKnowledge(p)?.version} · in_review</small></span><ArrowRight size={16} /></Link>)}{!projects.some(p => latestKnowledge(p)?.status === "in_review") && <div className="empty-list"><h2>Không có PKB đang review</h2><p>Merchant gửi review thì bản PKB sẽ xuất hiện ở đây.</p></div>}</section>}</>;
}
