import { findReview, reviewErrorResponse } from "@/lib/api/reviews-server";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    return Response.json(await findReview(id, request.headers.get("authorization")), { headers: { "Cache-Control": "no-store" } });
  } catch (error) { return reviewErrorResponse(error); }
}
