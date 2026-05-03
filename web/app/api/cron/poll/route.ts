import { NextRequest, NextResponse } from "next/server";

import { getEnv } from "@/lib/env";
import { pollOnce } from "@/lib/worker";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

function authorizeCron(req: NextRequest): boolean {
  const env = getEnv();
  if (process.env.NODE_ENV === "development" && !env.cronSecret) return true;

  const secret = env.cronSecret;
  if (!secret) return false;

  const auth = req.headers.get("authorization");
  if (auth === `Bearer ${secret}`) return true;

  const q = req.nextUrl.searchParams.get("secret");
  return q === secret;
}

export async function GET(req: NextRequest) {
  if (!authorizeCron(req)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  try {
    await pollOnce();
    return NextResponse.json({ ok: true });
  } catch (e) {
    console.error("[cron/poll]", e);
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : "poll failed" },
      { status: 500 },
    );
  }
}

export async function POST(req: NextRequest) {
  return GET(req);
}
