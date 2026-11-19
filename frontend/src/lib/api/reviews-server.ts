import "server-only";
import { demoReviews, searchDemoReviews } from "@/features/reviews/demo";
import { parseReview, type ReviewResult, type SearchResult } from "@/features/reviews/types";

export class ReviewServiceError extends Error {
  constructor(public status: number) { super("Review service unavailable"); }
}

async function upstream(path: string, authorization: string | null): Promise<unknown> {
  const base = process.env.REVIEW_API_BASE_URL;
  if (!base) throw new ReviewServiceError(503);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (authorization) headers.Authorization = authorization;
  try {
    const response = await fetch(`${base.replace(/\/$/, "")}${path}`, { headers, cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new ReviewServiceError([401, 403, 404, 429].includes(response.status) ? response.status : 502);
    return await response.json();
  } catch (error) {
    if (error instanceof ReviewServiceError) throw error;
    throw new ReviewServiceError(502);
  }
}

export async function findReviews(query: string, authorization: string | null): Promise<SearchResult> {
  if (!process.env.REVIEW_API_BASE_URL) {
    const reviews = searchDemoReviews(query);
    return { reviews, total: reviews.length, source: "demo" };
  }
  const data = await upstream(`/search?${new URLSearchParams({ q: query })}`, authorization);
  try {
    const payload = data as { reviews: unknown[]; total: number };
    if (!Array.isArray(payload.reviews) || !Number.isInteger(payload.total) || payload.total < payload.reviews.length) throw new Error("Invalid payload");
    return { reviews: payload.reviews.map(parseReview), total: payload.total, source: "backend" };
  } catch { throw new ReviewServiceError(502); }
}

export async function findReview(id: string, authorization: string | null): Promise<ReviewResult> {
  if (!process.env.REVIEW_API_BASE_URL) {
    const review = demoReviews.find((item) => item.id === id);
    if (!review) throw new ReviewServiceError(404);
    return { review, source: "demo" };
  }
  const data = await upstream(`/reviews/${encodeURIComponent(id)}`, authorization);
  try { return { review: parseReview(data), source: "backend" }; }
  catch { throw new ReviewServiceError(502); }
}

export function reviewErrorResponse(error: unknown): Response {
  const status = error instanceof ReviewServiceError ? error.status : 502;
  return Response.json({ detail: status === 404 ? "Review not found" : "Review service unavailable" }, { status, headers: { "Cache-Control": "no-store" } });
}
