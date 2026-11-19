"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { searchReviews } from "@/lib/api/reviews";
import type { SearchResult } from "./types";
import { ReviewCard } from "./review-card";
import { SearchBar } from "./search-bar";

export const SEARCH_DEBOUNCE_MS = 300;

export function ReviewLibrary() {
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [response, setResponse] = useState<{ query: string; attempt: number; data?: SearchResult; error?: string } | null>(null);
  const term = query.trim();
  const loading = !response || response.query !== term || response.attempt !== attempt;
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const data = await searchReviews(term, controller.signal);
        if (!controller.signal.aborted) setResponse({ query: term, attempt, data });
      } catch {
        if (!controller.signal.aborted) setResponse({ query: term, attempt, error: "Không thể tải danh sách review. Hãy kiểm tra kết nối và thử lại." });
      }
    }, SEARCH_DEBOUNCE_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [term, attempt]);

  const data = loading ? undefined : response?.data;
  return (
    <>
      <div className="page-heading"><div><h1>Review video</h1><p>Khám phá video, điểm đánh giá và transcript theo thời gian.</p></div></div>
      <SearchBar value={query} onChange={setQuery} loading={loading} />
      <section id="review-results" aria-label="Kết quả review" aria-busy={loading}>
        {loading ? <div className="review-skeleton-grid" aria-hidden="true">{[1, 2, 3].map((id) => <div className="review-skeleton" key={id} />)}</div> : response?.error ? (
          <div className="empty-list" role="alert"><p>{response.error}</p><Button variant="outline" onClick={() => setAttempt(attempt + 1)}>Thử lại</Button></div>
        ) : data && (
          <>
            <p className="review-result-count" role="status">{data.total} review{data.source === "demo" ? " · Dữ liệu mẫu, điểm số và transcript chưa được AI tạo." : ""}</p>
            {data.reviews.length ? <div className="review-grid">{data.reviews.map((review) => <ReviewCard key={review.id} review={review} demo={data.source === "demo"} />)}</div> : (
              <div className="empty-list"><p>Không tìm thấy review phù hợp.</p><Button variant="outline" onClick={() => setQuery("")}>Xóa tìm kiếm</Button></div>
            )}
          </>
        )}
      </section>
    </>
  );
}
