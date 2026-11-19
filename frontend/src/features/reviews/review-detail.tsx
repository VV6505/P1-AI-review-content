"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getReview, ReviewApiError } from "@/lib/api/reviews";
import type { ReviewResult } from "./types";
import { VideoPlayer } from "./video-player";

export function ReviewDetail({ id }: { id: string }) {
  const [attempt, setAttempt] = useState(0);
  const [response, setResponse] = useState<{ id: string; attempt: number; data?: ReviewResult; missing?: boolean; error?: string } | null>(null);
  const loading = !response || response.id !== id || response.attempt !== attempt;
  useEffect(() => {
    const controller = new AbortController();
    getReview(id, controller.signal).then((data) => {
      if (!controller.signal.aborted) setResponse({ id, attempt, data });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setResponse({ id, attempt, missing: error instanceof ReviewApiError && error.status === 404, error: "Không thể tải review. Hãy thử lại." });
    });
    return () => controller.abort();
  }, [id, attempt]);
  const data = loading ? undefined : response?.data;
  const review = data?.review;
  return (
    <>
      <Link href="/reviews" className="back-link"><ArrowLeft size={16} /> Thư viện review</Link>
      {loading ? <div className="empty-list" role="status"><LoaderCircle className="spin" size={24} />Đang tải review…</div> : review ? (
        <>
          <div className="page-heading review-detail-heading"><div><p>{review.product}</p><h1>{review.title}</h1></div><div className="detail-score"><strong>{review.score ?? "—"}</strong><span>{review.score !== null ? "/100 · " : ""}{data?.source === "demo" ? "Điểm mẫu" : "Điểm AI"}</span></div></div>
          {data?.source === "demo" && <p className="review-demo-banner">Video minh họa workspace · Điểm và transcript là dữ liệu mẫu, chưa phải kết quả AI hoặc footage sản phẩm thật.</p>}
          <p className="review-summary">{review.summary}</p>
          {review.status === "completed" && review.videoUrl ? <VideoPlayer key={`${review.id}-${review.videoUrl}`} src={review.videoUrl} poster={review.thumbnailUrl} title={review.title} transcript={review.transcript} /> : (
            <div className="empty-list" role="status"><p>{review.status === "failed" ? "Quá trình tạo review thất bại." : review.status === "completed" ? "Review chưa có nguồn video." : "Review đang được xử lý. Bạn có thể kiểm tra lại sau."}</p><Button variant="outline" onClick={() => setAttempt(attempt + 1)}>Kiểm tra lại</Button></div>
          )}
        </>
      ) : <div className="empty-list" role="alert"><h1>{response?.missing ? "Không tìm thấy review" : "Không thể mở review"}</h1><p>{response?.missing ? "Review có thể đã bị xóa hoặc đường dẫn không chính xác." : response?.error}</p>{!response?.missing && <Button variant="outline" onClick={() => setAttempt(attempt + 1)}>Thử lại</Button>}<Link href="/reviews">Về thư viện review</Link></div>}
    </>
  );
}
