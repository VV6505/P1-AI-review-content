export type TranscriptSegment = { start: number; end: number; text: string };
export type Review = {
  id: string;
  title: string;
  product: string;
  summary: string;
  thumbnailUrl: string;
  videoUrl: string | null;
  score: number | null;
  status: "queued" | "processing" | "completed" | "failed";
  transcript: TranscriptSegment[];
};
export type ReviewSource = "demo" | "backend";
export type SearchResult = { reviews: Review[]; total: number; source: ReviewSource };
export type ReviewResult = { review: Review; source: ReviewSource };

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid review response");
  return value as Record<string, unknown>;
}
function string(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) throw new Error("Missing review field");
  return value;
}
function mediaUrl(value: unknown): string {
  const result = string(value);
  if (/^\/(?!\/)/.test(result)) return result;
  const url = new URL(result);
  if (url.protocol !== "https:" && url.protocol !== "http:") throw new Error("Invalid media URL");
  return result;
}
export function parseReview(value: unknown): Review {
  const data = object(value);
  const status = data.status;
  if (status !== "queued" && status !== "processing" && status !== "completed" && status !== "failed") throw new Error("Invalid review status");
  if (data.score !== null && (typeof data.score !== "number" || !Number.isFinite(data.score) || data.score < 0 || data.score > 100)) throw new Error("Invalid review score");
  if (!Array.isArray(data.transcript)) throw new Error("Missing transcript");
  let previousEnd = 0;
  const transcript = data.transcript.map((value) => {
    const segment = object(value);
    const { start, end } = segment;
    if (typeof start !== "number" || typeof end !== "number" || !Number.isFinite(start) || !Number.isFinite(end) || start < previousEnd || end <= start) throw new Error("Invalid transcript timing");
    previousEnd = end;
    return { start, end, text: string(segment.text) };
  });
  return {
    id: string(data.id), title: string(data.title), product: string(data.product), summary: string(data.summary),
    thumbnailUrl: mediaUrl(data.thumbnailUrl), videoUrl: data.videoUrl === null ? null : mediaUrl(data.videoUrl),
    score: data.score as number | null, status, transcript,
  };
}
export function parseSearchResult(value: unknown): SearchResult {
  const data = object(value);
  if (!Array.isArray(data.reviews) || typeof data.total !== "number" || !Number.isInteger(data.total) || data.total < data.reviews.length || (data.source !== "demo" && data.source !== "backend")) throw new Error("Invalid search response");
  return { reviews: data.reviews.map(parseReview), total: data.total, source: data.source };
}
export function parseReviewResult(value: unknown): ReviewResult {
  const data = object(value);
  if (data.source !== "demo" && data.source !== "backend") throw new Error("Invalid review source");
  return { review: parseReview(data.review), source: data.source };
}
export function activeSegmentAt(segments: TranscriptSegment[], seconds: number): number {
  return segments.findIndex((segment) => seconds >= segment.start && seconds < segment.end);
}
export function formatTime(seconds: number): string {
  const rounded = Math.max(0, Math.floor(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}
