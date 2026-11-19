import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, Play } from "lucide-react";
import type { Review } from "./types";

const statusLabel = { queued: "Đang chờ", processing: "Đang xử lý", completed: "Sẵn sàng", failed: "Xử lý thất bại" };

export function ReviewCard({ review, demo = false }: { review: Review; demo?: boolean }) {
  return (
    <Link href={`/review/${encodeURIComponent(review.id)}`} className="review-card">
      <div className="review-thumbnail">
        <Image src={review.thumbnailUrl} alt={`Ảnh minh họa review ${review.product}`} fill sizes="(max-width: 600px) 100vw, (max-width: 1100px) 50vw, 33vw" unoptimized />
        <span className="review-play" aria-hidden="true"><Play size={20} fill="currentColor" /></span>
        {demo && <span className="thumbnail-label">Video mẫu</span>}
      </div>
      <div className="review-card-body">
        <div className="review-card-meta"><span>{review.product}</span><span>{statusLabel[review.status]}</span></div>
        <h2>{review.title}</h2>
        <p>{review.summary}</p>
        <div className="review-card-bottom">
          <span className="review-score"><strong>{review.score ?? "—"}</strong>{review.score !== null && <span>/100</span>}<small>{demo ? "Điểm mẫu" : "Điểm AI"}</small></span>
          <span>Xem review <ArrowUpRight size={16} /></span>
        </div>
      </div>
    </Link>
  );
}
