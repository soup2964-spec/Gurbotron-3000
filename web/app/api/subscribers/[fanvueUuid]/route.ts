import { NextResponse } from "next/server";

import { purgeSubscriberByFanvueUuid } from "@/lib/automation";

export const dynamic = "force-dynamic";

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ fanvueUuid: string }> },
) {
  const { fanvueUuid } = await ctx.params;
  const ok = await purgeSubscriberByFanvueUuid(fanvueUuid);
  if (!ok) return NextResponse.json({ deleted: false }, { status: 404 });
  return NextResponse.json({ deleted: true });
}
