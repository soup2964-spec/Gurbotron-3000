import { NextResponse } from "next/server";

import { sendPpvOffer } from "@/lib/automation";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

type Body = {
  templateUuid?: string;
  text?: string;
  priceCents?: number;
  mediaUuids?: string[];
};

export async function POST(
  req: Request,
  ctx: { params: Promise<{ fanvueUuid: string }> },
) {
  const { fanvueUuid } = await ctx.params;
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const subscriber = await prisma.subscriber.findUnique({
    where: { fanvueUserUuid: fanvueUuid },
  });
  if (!subscriber) {
    return NextResponse.json({ error: "Subscriber not found" }, { status: 404 });
  }

  try {
    const result = await sendPpvOffer(subscriber.id, {
      templateUuid: body.templateUuid,
      text: body.text,
      priceCents: body.priceCents,
      mediaUuids: body.mediaUuids,
    });
    return NextResponse.json(result);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "send failed";
    return NextResponse.json({ error: msg }, { status: 400 });
  }
}
