import { randomInt, randomUUID } from "crypto";

import type { Prisma, Subscriber, SubscriberFact } from "@prisma/client";

import { getChatTemplate, sendChatMessage } from "@/lib/fanvue";
import { getEnv } from "@/lib/env";
import type { ReplyGenerator } from "@/lib/llm";
import { defaultGenerator } from "@/lib/llm";
import { prisma } from "@/lib/prisma";

export function safeParseJson(raw: string | null | undefined): Record<string, unknown> {
  if (!raw || !String(raw).trim()) return {};
  try {
    const v = JSON.parse(String(raw)) as unknown;
    if (v && typeof v === "object" && !Array.isArray(v)) return v as Record<string, unknown>;
  } catch {
    /* ignore malformed JSON */
  }
  return {};
}

export function factsDict(facts: SubscriberFact[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of facts) out[f.factKey] = f.factValue;
  return out;
}

export async function recentThread(subscriberId: number, limit = 40): Promise<[string, string][]> {
  const rows = await prisma.chatMessage.findMany({
    where: { subscriberId },
    orderBy: { id: "desc" },
    take: limit,
    select: { direction: true, body: true },
  });
  rows.reverse();
  const out: [string, string][] = [];
  for (const m of rows) {
    const role = m.direction === "inbound" ? "fan" : "creator";
    const text = (m.body ?? "").trim();
    if (text) out.push([role, text]);
  }
  return out;
}

export async function composeAndMaybeSend(
  subscriberId: number,
  generator?: ReplyGenerator,
): Promise<void> {
  const env = getEnv();
  const gen = generator ?? defaultGenerator;

  await prisma.botSettings.upsert({
    where: { id: 1 },
    create: { id: 1 },
    update: {},
  });

  const bot = await prisma.botSettings.findUnique({ where: { id: 1 } });
  if (!bot) return;

  let subscriber = await prisma.subscriber.findUnique({
    where: { id: subscriberId },
    include: { facts: true },
  });
  if (!subscriber || bot.automationPausedGlobal || !subscriber.automationEnabled) return;

  const llmContext = safeParseJson(subscriber.llmContext);

  const ctx = {
    masterPrompt: bot.masterPrompt,
    guidelines: bot.guidelines,
    subscriberHandle: subscriber.handle,
    subscriberUuid: subscriber.fanvueUserUuid,
    llmContext,
    facts: factsDict(subscriber.facts),
    recentMessages: await recentThread(subscriber.id),
  };

  let [text, ppvPrice] = await gen.generate(ctx);

  if (subscriber.pendingPpvMessageUuid && subscriber.exitThreshold === null) {
    const exitThreshold = randomInt(env.exitMessagesMin, env.exitMessagesMax + 1);
    await prisma.subscriber.update({
      where: { id: subscriber.id },
      data: { exitThreshold },
    });
  }

  subscriber = await prisma.subscriber.findUnique({
    where: { id: subscriberId },
    include: { facts: true },
  });
  if (!subscriber) return;

  if (
    subscriber.pendingPpvMessageUuid &&
    subscriber.exitThreshold != null &&
    subscriber.messagesSincePpvOffer >= subscriber.exitThreshold
  ) {
    text = bot.exitMessage;
    ppvPrice = null;
  }

  let priceOut = ppvPrice ?? env.defaultPpvPriceCents ?? null;
  priceOut = priceOut != null && priceOut >= 300 ? priceOut : null;

  const payload = (await sendChatMessage(subscriber.fanvueUserUuid, {
    text,
    ...(priceOut != null ? { price: priceOut } : {}),
  })) as { data?: { uuid?: string } };

  const fanvueMsgUuid = payload?.data?.uuid ?? null;
  const localId = fanvueMsgUuid ?? randomUUID();

  await prisma.chatMessage.create({
    data: {
      fanvueMessageUuid: localId,
      subscriberId: subscriber.id,
      direction: "outbound",
      body: text,
      hadPricing: Boolean(priceOut),
    },
  });

  const subUpdate: Prisma.SubscriberUpdateInput = { updatedAt: new Date() };
  if (priceOut && fanvueMsgUuid) {
    subUpdate.pendingPpvMessageUuid = fanvueMsgUuid;
    subUpdate.messagesSincePpvOffer = 0;
    subUpdate.exitThreshold = null;
  }
  await prisma.subscriber.update({ where: { id: subscriber.id }, data: subUpdate });

  const tpl = env.autoAttachPpvTemplateUuid?.trim();
  if (tpl && !priceOut) {
    const sub2 = await prisma.subscriber.findUnique({ where: { id: subscriber.id } });
    if (sub2 && !sub2.pendingPpvMessageUuid) {
      await sendPpvOffer(sub2.id, { templateUuid: tpl });
    }
  }
}

export async function sendPpvOffer(
  subscriberId: number,
  opts: {
    templateUuid?: string | null;
    text?: string | null;
    priceCents?: number | null;
    mediaUuids?: string[] | null;
  },
): Promise<{ fanvue_message_uuid: string; had_pricing: boolean; template_uuid?: string }> {
  const subscriber = await prisma.subscriber.findUnique({ where: { id: subscriberId } });
  if (!subscriber) throw new Error("Subscriber not found");

  const templateUuid = opts.templateUuid?.trim() || undefined;
  const text = opts.text?.trim() || undefined;
  const mediaUuids = opts.mediaUuids?.filter(Boolean) ?? undefined;

  if (templateUuid) {
    if (text !== undefined || opts.priceCents != null || (mediaUuids?.length ?? 0) > 0) {
      throw new Error("Use either templateUuid or custom text/price/media — not both");
    }
  }

  let previewText = "";
  let priceForTracking: number | null = null;

  if (templateUuid) {
    const detail = (await getChatTemplate(templateUuid)) as {
      data?: { text?: string; price?: unknown };
    };
    const tplData = detail.data;
    if (tplData && typeof tplData === "object") {
      previewText = String(tplData.text ?? "").trim();
      const p = tplData.price;
      if (p != null) {
        const pi = typeof p === "number" ? p : Number.parseInt(String(p), 10);
        if (Number.isFinite(pi) && pi >= 300) priceForTracking = pi;
      }
    }
    const payload = (await sendChatMessage(subscriber.fanvueUserUuid, {
      templateUuid,
    })) as { data?: { uuid?: string } };
    const fanvueMsgUuid = payload?.data?.uuid ?? null;
    const localId = fanvueMsgUuid ?? randomUUID();
    const storedBody = previewText || null;

    await prisma.chatMessage.create({
      data: {
        fanvueMessageUuid: localId,
        subscriberId: subscriber.id,
        direction: "outbound",
        body: storedBody,
        hadPricing: Boolean(priceForTracking),
      },
    });

    const subUpdate: Prisma.SubscriberUpdateInput = { updatedAt: new Date() };
    if (priceForTracking && fanvueMsgUuid) {
      subUpdate.pendingPpvMessageUuid = fanvueMsgUuid;
      subUpdate.messagesSincePpvOffer = 0;
      subUpdate.exitThreshold = null;
    }
    await prisma.subscriber.update({ where: { id: subscriber.id }, data: subUpdate });

    return {
      fanvue_message_uuid: fanvueMsgUuid ?? localId,
      had_pricing: Boolean(priceForTracking),
      template_uuid: templateUuid,
    };
  }

  if (!text) throw new Error("Message text is required when not using a template");
  if (opts.priceCents != null && opts.priceCents < 300) {
    throw new Error("PPV price must be at least 300 cents ($3)");
  }
  const priceOut =
    opts.priceCents != null && opts.priceCents >= 300 ? opts.priceCents : undefined;

  const payload = (await sendChatMessage(subscriber.fanvueUserUuid, {
    text,
    price: priceOut,
    mediaUuids,
  })) as { data?: { uuid?: string } };

  const fanvueMsgUuid = payload?.data?.uuid ?? null;
  const localId = fanvueMsgUuid ?? randomUUID();

  await prisma.chatMessage.create({
    data: {
      fanvueMessageUuid: localId,
      subscriberId: subscriber.id,
      direction: "outbound",
      body: text,
      hadPricing: Boolean(priceOut),
    },
  });

  const subUpdateOut: Prisma.SubscriberUpdateInput = { updatedAt: new Date() };
  if (priceOut && fanvueMsgUuid) {
    subUpdateOut.pendingPpvMessageUuid = fanvueMsgUuid;
    subUpdateOut.messagesSincePpvOffer = 0;
    subUpdateOut.exitThreshold = null;
  }
  await prisma.subscriber.update({ where: { id: subscriber.id }, data: subUpdateOut });

  return {
    fanvue_message_uuid: fanvueMsgUuid ?? localId,
    had_pricing: Boolean(priceOut),
  };
}

export async function refreshPpvPurchaseState(
  subscriberId: number,
  messagesPayload: { data?: Record<string, unknown>[] },
): Promise<void> {
  const subscriber = await prisma.subscriber.findUnique({ where: { id: subscriberId } });
  const pending = subscriber?.pendingPpvMessageUuid;
  if (!pending) return;

  for (const item of messagesPayload.data ?? []) {
    if (String(item.uuid) !== pending) continue;
    if (item.purchasedAt) {
      await prisma.subscriber.update({
        where: { id: subscriberId },
        data: {
          pendingPpvMessageUuid: null,
          messagesSincePpvOffer: 0,
          exitThreshold: null,
          updatedAt: new Date(),
        },
      });
    }
    break;
  }
}

export async function ingestMessageRow(
  subscriber: Subscriber,
  row: {
    fanvueMessageUuid: string;
    body: string | null;
    senderUuid: string;
    creatorUuid: string;
    pricing: Record<string, unknown> | null | undefined;
    purchasedAt: string | null | undefined;
    sentAt: string | null | undefined;
  },
): Promise<boolean> {
  const exists = await prisma.chatMessage.findUnique({
    where: { fanvueMessageUuid: row.fanvueMessageUuid },
  });
  if (exists) return false;

  const direction =
    row.senderUuid !== row.creatorUuid ? ("inbound" as const) : ("outbound" as const);
  const hadPricing = Boolean(row.pricing);

  await prisma.chatMessage.create({
    data: {
      fanvueMessageUuid: row.fanvueMessageUuid,
      subscriberId: subscriber.id,
      direction,
      body: row.body,
      hadPricing,
      purchasedAtRaw: row.purchasedAt ?? null,
      sentAt: row.sentAt ?? null,
    },
  });

  if (direction === "inbound" && subscriber.pendingPpvMessageUuid) {
    await prisma.subscriber.update({
      where: { id: subscriber.id },
      data: {
        messagesSincePpvOffer: { increment: 1 },
        updatedAt: new Date(),
      },
    });
  } else {
    await prisma.subscriber.update({
      where: { id: subscriber.id },
      data: { updatedAt: new Date() },
    });
  }

  return direction === "inbound";
}

export async function upsertSubscriber(user: {
  uuid?: string;
  handle?: string | null;
  displayName?: string | null;
}): Promise<Subscriber> {
  const uid = user.uuid;
  if (!uid) throw new Error("user.uuid required");

  return prisma.subscriber.upsert({
    where: { fanvueUserUuid: uid },
    create: {
      fanvueUserUuid: uid,
      handle: user.handle ?? null,
      displayName: user.displayName ?? null,
      llmContext: "{}",
    },
    update: {
      handle: user.handle ?? null,
      displayName: user.displayName ?? null,
    },
  });
}

export async function purgeSubscriberByFanvueUuid(fanvueUserUuid: string): Promise<boolean> {
  try {
    await prisma.subscriber.delete({ where: { fanvueUserUuid } });
    return true;
  } catch {
    return false;
  }
}
