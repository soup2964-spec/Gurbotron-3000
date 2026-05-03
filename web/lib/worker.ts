import {
  composeAndMaybeSend,
  ingestMessageRow,
  refreshPpvPurchaseState,
  upsertSubscriber,
} from "@/lib/automation";
import { getEnv } from "@/lib/env";
import { listChats, listMessages } from "@/lib/fanvue";
import { prisma } from "@/lib/prisma";

/** Single Fanvue poll: list chats → ingest messages → reply when new inbound. */
export async function pollOnce(): Promise<void> {
  const env = getEnv();
  if (!env.fanvueAccessToken || !env.fanvueCreatorUuid) {
    console.warn("[poll] FANVUE_ACCESS_TOKEN or FANVUE_CREATOR_UUID missing — skipping");
    return;
  }

  await prisma.botSettings.upsert({
    where: { id: 1 },
    create: { id: 1 },
    update: {},
  });

  const chatsPayload = await listChats({ page: 1, size: 30, filters: ["subscribers"] });
  const chats = (chatsPayload.data ?? []) as { user?: Record<string, unknown> }[];

  for (const chat of chats) {
    const user = (chat.user ?? {}) as {
      uuid?: string;
      handle?: string | null;
      displayName?: string | null;
    };
    const uid = user.uuid;
    if (!uid) continue;

    let subscriber = await upsertSubscriber(user);

    const msgPayload = await listMessages(uid, { page: 1, size: 50, markAsRead: false });
    await refreshPpvPurchaseState(subscriber.id, msgPayload);

    const rows = [...(msgPayload.data ?? [])].sort((a, b) =>
      String(a.sentAt ?? "").localeCompare(String(b.sentAt ?? "")),
    );

    let hadNewInbound = false;
    for (const m of rows) {
      const mid = m.uuid != null ? String(m.uuid) : "";
      const sender = (m.sender ?? {}) as { uuid?: string };
      const sid = sender.uuid != null ? String(sender.uuid) : "";
      if (!mid || !sid) continue;

      const refreshed = await prisma.subscriber.findUnique({ where: { id: subscriber.id } });
      if (!refreshed) break;

      const pricing = m.pricing as Record<string, unknown> | null | undefined;
      const isNew = await ingestMessageRow(refreshed, {
        fanvueMessageUuid: mid,
        body: m.text != null ? String(m.text) : null,
        senderUuid: sid,
        creatorUuid: env.fanvueCreatorUuid,
        pricing: pricing ?? null,
        purchasedAt: m.purchasedAt != null ? String(m.purchasedAt) : undefined,
        sentAt: m.sentAt != null ? String(m.sentAt) : undefined,
      });
      if (isNew) hadNewInbound = true;
      subscriber = refreshed;
    }

    if (hadNewInbound) {
      const subForLlm = await prisma.subscriber.findUnique({
        where: { id: subscriber.id },
        include: { facts: true },
      });
      if (subForLlm) await composeAndMaybeSend(subForLlm.id);
    }
  }
}
