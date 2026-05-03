import { getEnv } from "@/lib/env";

export type FanvueChatTemplateSummary = { uuid?: string; name?: string };

async function fanvueFetch(path: string, init?: RequestInit): Promise<unknown> {
  const env = getEnv();
  const token = env.fanvueAccessToken;
  const base = env.fanvueApiUrl.replace(/\/$/, "");
  const url = `${base}${path}`;
  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
    "X-Fanvue-API-Version": env.fanvueApiVersion,
    Accept: "application/json",
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const res = await fetch(url, {
    ...init,
    headers,
    signal: AbortSignal.timeout(60_000),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Fanvue ${res.status}: ${body.slice(0, 500)}`);
  }
  return res.json();
}

export async function listChats(params: {
  page?: number;
  size?: number;
  filters?: string[];
}): Promise<{ data?: unknown[] }> {
  const page = params.page ?? 1;
  const size = params.size ?? 30;
  const q = new URLSearchParams();
  q.set("page", String(page));
  q.set("size", String(size));
  for (const f of params.filters ?? ["subscribers"]) {
    q.append("filter", f);
  }
  return fanvueFetch(`/chats?${q.toString()}`) as Promise<{ data?: unknown[] }>;
}

export async function listChatTemplates(params?: {
  page?: number;
  size?: number;
  folderName?: string;
}): Promise<{ data?: FanvueChatTemplateSummary[] }> {
  const page = params?.page ?? 1;
  const size = Math.min(Math.max(params?.size ?? 50, 1), 50);
  const q = new URLSearchParams({
    page: String(page),
    size: String(size),
  });
  if (params?.folderName) q.set("folderName", params.folderName);
  return fanvueFetch(`/chats/templates?${q.toString()}`) as Promise<{
    data?: FanvueChatTemplateSummary[];
  }>;
}

export async function getChatTemplate(templateUuid: string): Promise<Record<string, unknown>> {
  return fanvueFetch(`/chats/templates/${templateUuid}`) as Promise<Record<string, unknown>>;
}

export async function listMessages(
  userUuid: string,
  params?: { page?: number; size?: number; markAsRead?: boolean },
): Promise<{ data?: Record<string, unknown>[] }> {
  const page = params?.page ?? 1;
  const size = params?.size ?? 50;
  const markAsRead = params?.markAsRead ?? false;
  const q = new URLSearchParams({
    page: String(page),
    size: String(size),
    markAsRead: String(markAsRead).toLowerCase(),
  });
  return fanvueFetch(`/chats/${userUuid}/messages?${q.toString()}`) as Promise<{
    data?: Record<string, unknown>[];
  }>;
}

export async function sendChatMessage(
  userUuid: string,
  body: {
    text?: string;
    price?: number;
    mediaUuids?: string[];
    templateUuid?: string;
  },
): Promise<Record<string, unknown>> {
  const payload: Record<string, unknown> = {};
  if (body.text) payload.text = body.text;
  if (body.price !== undefined) payload.price = body.price;
  if (body.mediaUuids?.length) payload.mediaUuids = body.mediaUuids;
  if (body.templateUuid) payload.templateUuid = body.templateUuid;

  return fanvueFetch(`/chats/${userUuid}/message`, {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<Record<string, unknown>>;
}
