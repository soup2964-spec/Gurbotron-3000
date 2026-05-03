"use server";

import { revalidatePath } from "next/cache";

import { pollOnce } from "@/lib/worker";
import { purgeSubscriberByFanvueUuid, sendPpvOffer } from "@/lib/automation";
import { prisma } from "@/lib/prisma";

export async function saveBotSettings(formData: FormData) {
  const masterPrompt = String(formData.get("masterPrompt") ?? "");
  const guidelines = String(formData.get("guidelines") ?? "");
  const exitMessage = String(formData.get("exitMessage") ?? "");
  const paused = formData.get("automationPausedGlobal") === "on";

  await prisma.botSettings.upsert({
    where: { id: 1 },
    create: {
      id: 1,
      masterPrompt,
      guidelines,
      exitMessage,
      automationPausedGlobal: paused,
    },
    update: {
      masterPrompt,
      guidelines,
      exitMessage,
      automationPausedGlobal: paused,
    },
  });
  revalidatePath("/");
}

export async function runPollNow() {
  await pollOnce();
  revalidatePath("/");
}

export async function setSubscriberAutomation(formData: FormData) {
  const fanvueUuid = String(formData.get("fanvueUuid") ?? "");
  const enabled = formData.get("automationEnabled") === "on";
  if (!fanvueUuid) return;
  await prisma.subscriber.update({
    where: { fanvueUserUuid: fanvueUuid },
    data: { automationEnabled: enabled },
  });
  revalidatePath("/");
}

export async function churnSubscriber(formData: FormData) {
  const fanvueUuid = String(formData.get("fanvueUuid") ?? "");
  if (!fanvueUuid) return;
  await purgeSubscriberByFanvueUuid(fanvueUuid);
  revalidatePath("/");
}

export async function sendPpvFromDashboard(formData: FormData) {
  const fanvueUuid = String(formData.get("fanvueUuid") ?? "");
  const templateUuid = String(formData.get("templateUuid") ?? "").trim();
  const text = String(formData.get("text") ?? "").trim();
  const priceRaw = formData.get("priceCents");
  const mediaRaw = String(formData.get("mediaUuids") ?? "").trim();

  const subscriber = await prisma.subscriber.findUnique({
    where: { fanvueUserUuid: fanvueUuid },
  });
  if (!subscriber) return;

  let priceCents: number | undefined;
  if (priceRaw !== null && String(priceRaw).trim() !== "") {
    const n = Number.parseInt(String(priceRaw), 10);
    if (Number.isFinite(n)) priceCents = n;
  }

  const mediaUuids = mediaRaw
    ? mediaRaw
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean)
    : undefined;

  if (templateUuid) {
    await sendPpvOffer(subscriber.id, { templateUuid });
  } else {
    await sendPpvOffer(subscriber.id, {
      text,
      priceCents: priceCents ?? null,
      mediaUuids: mediaUuids ?? null,
    });
  }
  revalidatePath("/");
}
