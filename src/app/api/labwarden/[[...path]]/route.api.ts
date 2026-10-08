import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.LABWARDEN_API_BASE || process.env.MEERKAT_API_BASE || "http://127.0.0.1:8711";
// x-meerkat-action-token is the pre-0.3 header name; the backend accepts both.
const FORWARDED_HEADERS = ["content-type", "x-labwarden-action-token", "x-meerkat-action-token"];

function backendPath(parts: string[] = []) {
  if (parts[0] === "actions") {
    return `/api/${parts.join("/")}`;
  }
  if (parts[0] === "metrics") {
    return "/metrics";
  }
  return `/api/${parts.join("/") || "status"}`;
}

async function proxy(request: NextRequest, parts: string[] = []) {
  const url = new URL(backendPath(parts), API_BASE);
  url.search = request.nextUrl.search;
  // Forward only what the Python API needs; never cookies or auth headers from the browser.
  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
    });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: `Labwarden API unavailable at ${API_BASE}`,
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 },
    );
  }

  const contentType = response.headers.get("content-type") || "application/json";
  const body = await response.text();

  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": contentType,
      "cache-control": "no-store",
    },
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const { path = [] } = await context.params;
  return proxy(request, path);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const { path = [] } = await context.params;
  return proxy(request, path);
}
