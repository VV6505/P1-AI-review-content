const allowed = [
  /^products(?:\/[0-9a-f-]+)?(?:\/(?:crawl|discovery\/preflight|login\/(?:browser|finish)|pkb\/\d+(?:\/(?:review|revise))?|scripts(?:\/generate|\/\d+(?:\/(?:review|design-suggest))?)?|videos))?$/i,
  /^jobs\/[0-9a-f-]+(?:\/(?:video|assets\/\d+))?$/i,
];

function configuration() {
  if (process.env.P1_LOCAL_MODE !== "1") throw new Error("P1 local proxy is disabled");
  const base = process.env.P1_API_BASE_URL?.replace(/\/$/, "");
  if (!base) throw new Error("P1_API_BASE_URL is missing");
  return { base, service: process.env.P1_SERVICE_TOKEN ?? "" };
}

function serviceOperation(method: string, path: string) {
  return method === "POST" && (
    /^products\/[0-9a-f-]+\/scripts\/generate$/i.test(path) ||
    /^products\/[0-9a-f-]+\/videos$/i.test(path)
  );
}

async function forward(request: Request, context: { params: Promise<{ path: string[] }> }) {
  try {
    const segments = (await context.params).path;
    const path = segments.join("/");
    if (!allowed.some(pattern => pattern.test(path))) return Response.json({ detail: "P1 path is not allowed" }, { status: 404 });
    const { base, service } = configuration();
    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    if (serviceOperation(request.method, path)) {
      if (!service) return Response.json({ detail: "P1_SERVICE_TOKEN is missing" }, { status: 503 });
      headers.set("x-service-token", service);
    } else headers.set("authorization", "Bearer local-demo");
    const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
    const upstream = await fetch(`${base}/${path}`, { method: request.method, headers, body, cache: "no-store" });
    const responseHeaders = new Headers();
    responseHeaders.set("cache-control", "no-store");
    const type = upstream.headers.get("content-type");
    if (type) responseHeaders.set("content-type", type);
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) responseHeaders.set("content-disposition", disposition);
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch (error) {
    return Response.json({ detail: error instanceof Error ? error.message : "P1 proxy failed" }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
