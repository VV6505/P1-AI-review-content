import { findReviews, reviewErrorResponse } from "@/lib/api/reviews-server";

export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.get("q")?.trim() ?? "";
  if (query.length > 200) return Response.json({ detail: "Query too long" }, { status: 400 });
  try {
    return Response.json(await findReviews(query, request.headers.get("authorization")), { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return reviewErrorResponse(error); }
}
