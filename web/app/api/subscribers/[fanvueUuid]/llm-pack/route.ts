import { NextResponse } from "next/server";

import { factsDict, safeParseJson } from "@/lib/automation";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ fanvueUuid: string }> },
) {
  const { fanvueUuid } = await ctx.params;

  const bot = await prisma.botSettings.findUnique({ where: { id: 1 } });
  const subscriber = await prisma.subscriber.findUnique({
    where: { fanvueUserUuid: fanvueUuid },
    include: { facts: true },
  });

  if (!subscriber) {
    return NextResponse.json({ error: "Subscriber not found" }, { status: 404 });
  }

  const llmContext = safeParseJson(subscriber.llmContext);

  return NextResponse.json({
    masterPrompt: bot?.masterPrompt ?? "",
    guidelines: bot?.guidelines ?? "",
    exitMessage: bot?.exitMessage ?? "",
    subscriber: {
      fanvueUserUuid: subscriber.fanvueUserUuid,
      handle: subscriber.handle,
      displayName: subscriber.displayName,
      llmContext,
      facts: factsDict(subscriber.facts),
      automationEnabled: subscriber.automationEnabled,
      pendingPpvMessageUuid: subscriber.pendingPpvMessageUuid,
      messagesSincePpvOffer: subscriber.messagesSincePpvOffer,
    },
  });
}
