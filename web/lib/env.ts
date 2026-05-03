function req(name: string): string {
  const v = process.env[name];
  if (v === undefined || v === "") {
    throw new Error(`Missing required env: ${name}`);
  }
  return v;
}

function opt(name: string): string | undefined {
  const v = process.env[name];
  return v === undefined || v === "" ? undefined : v;
}

function optInt(name: string): number | undefined {
  const v = opt(name);
  if (v === undefined) return undefined;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : undefined;
}

/** Resolved after lazy load — call getEnv() inside handlers/worker */
export function getEnv() {
  return {
    fanvueAccessToken: opt("FANVUE_ACCESS_TOKEN") ?? "",
    fanvueCreatorUuid: opt("FANVUE_CREATOR_UUID") ?? "",
    fanvueApiUrl: opt("FANVUE_API_URL") ?? "https://api.fanvue.com",
    fanvueApiVersion: opt("FANVUE_API_VERSION") ?? "2025-06-26",
    databaseUrl: opt("DATABASE_URL") ?? "file:./data/next.db",
    cronSecret: opt("CRON_SECRET"),
    defaultPpvPriceCents: optInt("DEFAULT_PPV_PRICE_CENTS"),
    exitMessagesMin: optInt("EXIT_MESSAGES_MIN") ?? 20,
    exitMessagesMax: optInt("EXIT_MESSAGES_MAX") ?? 30,
    /** After a non-priced auto-reply, send this Fanvue chat template UUID (optional). */
    autoAttachPpvTemplateUuid: opt("AUTO_ATTACH_PPV_TEMPLATE_UUID"),
  };
}

/** Fail fast when wiring cron or scripts that must authenticate */
export function requireCronSecret(): string {
  return req("CRON_SECRET");
}
