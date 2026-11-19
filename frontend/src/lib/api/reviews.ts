import { parseReviewResult, parseSearchResult } from "@/features/reviews/types";

export class ReviewApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = "ReviewApiError"; }
}

async function request(path: string, signal?: AbortSignal): Promise<unknown> {
  const timeout = AbortSignal.timeout(10000);
  const response = await fetch(path, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout, headers: { Accept: "application/json" }, cache: "no-store" });
  if (!response.ok) throw new ReviewApiError(response.status === 404 ? "Không tìm thấy review này." : "Không thể tải review. Vui lòng thử lại.", response.status);
  return response.json();
}

export async function searchReviews(query: string, signal?: AbortSignal) {
  return parseSearchResult(await request(`/search?${new URLSearchParams({ q: query })}`, signal));
}
export async function getReview(id: string, signal?: AbortSignal) {
  return parseReviewResult(await request(`/api/reviews/${encodeURIComponent(id)}`, signal));
}
