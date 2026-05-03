import {
  churnSubscriber,
  runPollNow,
  saveBotSettings,
  sendPpvFromDashboard,
  setSubscriberAutomation,
} from "@/app/actions";
import { listChatTemplates } from "@/lib/fanvue";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export default async function Home() {
  const bot =
    (await prisma.botSettings.findUnique({ where: { id: 1 } })) ??
    (await prisma.botSettings.create({ data: { id: 1 } }));

  const subscribers = await prisma.subscriber.findMany({
    orderBy: { updatedAt: "desc" },
  });

  let templates: { uuid?: string; name?: string }[] = [];
  let templateError: string | null = null;
  try {
    const res = await listChatTemplates({ page: 1, size: 50 });
    templates = res.data ?? [];
  } catch (e) {
    templateError = e instanceof Error ? e.message : "Could not load templates";
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <main className="mx-auto max-w-4xl px-4 py-10 space-y-10">
        <header className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">Gurbotron — Fanvue automation</h1>
          <p className="text-sm text-zinc-400">
            Automation runs on a schedule via{" "}
            <code className="rounded bg-zinc-800 px-1">GET /api/cron/poll</code> (Vercel Cron +{" "}
            <code className="rounded bg-zinc-800 px-1">CRON_SECRET</code>). Use “Poll now” for a manual
            run.
          </p>
        </header>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="text-lg font-medium">Bot settings</h2>
            <form action={runPollNow}>
              <button
                type="submit"
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
              >
                Poll now
              </button>
            </form>
          </div>
          <form action={saveBotSettings} className="space-y-3">
            <label className="block space-y-1">
              <span className="text-xs uppercase text-zinc-500">Master prompt</span>
              <textarea
                name="masterPrompt"
                defaultValue={bot.masterPrompt}
                rows={3}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-zinc-500">Guidelines</span>
              <textarea
                name="guidelines"
                defaultValue={bot.guidelines}
                rows={3}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase text-zinc-500">Exit message</span>
              <textarea
                name="exitMessage"
                defaultValue={bot.exitMessage}
                rows={2}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="automationPausedGlobal"
                value="on"
                defaultChecked={bot.automationPausedGlobal}
                className="rounded border-zinc-600"
              />
              <input type="hidden" name="automationPausedGlobal" value="off" />
              Automation paused (global)
            </label>
            <button
              type="submit"
              className="rounded-lg bg-zinc-100 px-3 py-1.5 text-sm font-medium text-zinc-900 hover:bg-white"
            >
              Save settings
            </button>
          </form>
        </section>

        <section className="space-y-4">
          <h2 className="text-lg font-medium">Subscribers ({subscribers.length})</h2>
          {subscribers.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No subscribers yet — run a poll after fans message you to populate this list.
            </p>
          ) : (
            <ul className="space-y-6">
              {subscribers.map((s) => (
                <li
                  key={s.id}
                  className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-5 space-y-4"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{s.displayName ?? s.handle ?? "Subscriber"}</p>
                      <p className="font-mono text-xs text-zinc-500">{s.fanvueUserUuid}</p>
                      <p className="mt-1 text-xs text-zinc-400">
                        Pending PPV: {s.pendingPpvMessageUuid ?? "—"} · msgs since offer:{" "}
                        {s.messagesSincePpvOffer}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <form action={setSubscriberAutomation} className="space-y-1">
                        <input type="hidden" name="fanvueUuid" value={s.fanvueUserUuid} />
                        <label className="flex items-center gap-2 text-xs">
                          <input
                            type="checkbox"
                            name="automationEnabled"
                            value="on"
                            defaultChecked={s.automationEnabled}
                          />
                          <input type="hidden" name="automationEnabled" value="off" />
                          Automation
                        </label>
                        <button
                          type="submit"
                          className="rounded bg-zinc-700 px-2 py-1 text-xs hover:bg-zinc-600"
                        >
                          Save
                        </button>
                      </form>
                      <form action={churnSubscriber}>
                        <input type="hidden" name="fanvueUuid" value={s.fanvueUserUuid} />
                        <button
                          type="submit"
                          className="rounded bg-red-900/80 px-2 py-1 text-xs hover:bg-red-800"
                        >
                          Churn (delete)
                        </button>
                      </form>
                    </div>
                  </div>

                  <div className="border-t border-zinc-800 pt-4">
                    <p className="mb-2 text-xs uppercase text-zinc-500">Send PPV / template</p>
                    {templateError && (
                      <p className="mb-2 text-xs text-amber-400">{templateError}</p>
                    )}
                    <form action={sendPpvFromDashboard} className="grid gap-2 sm:grid-cols-2">
                      <input type="hidden" name="fanvueUuid" value={s.fanvueUserUuid} />
                      <label className="sm:col-span-2 space-y-1">
                        <span className="text-xs text-zinc-500">Template (optional)</span>
                        <select
                          name="templateUuid"
                          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
                          defaultValue=""
                        >
                          <option value="">— Custom message below —</option>
                          {templates.map((t) => (
                            <option key={t.uuid ?? ""} value={t.uuid ?? ""}>
                              {(t.name ?? t.uuid ?? "").slice(0, 80)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="sm:col-span-2 space-y-1">
                        <span className="text-xs text-zinc-500">Custom text</span>
                        <textarea
                          name="text"
                          rows={2}
                          placeholder="Ignored if a template is selected"
                          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
                        />
                      </label>
                      <label className="space-y-1">
                        <span className="text-xs text-zinc-500">Price (cents, ≥300)</span>
                        <input
                          name="priceCents"
                          type="number"
                          min={300}
                          placeholder="optional"
                          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
                        />
                      </label>
                      <label className="space-y-1">
                        <span className="text-xs text-zinc-500">Media UUIDs</span>
                        <input
                          name="mediaUuids"
                          placeholder="comma or space separated"
                          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm"
                        />
                      </label>
                      <button
                        type="submit"
                        className="sm:col-span-2 rounded-lg bg-violet-600 px-3 py-2 text-sm font-medium hover:bg-violet-500"
                      >
                        Send
                      </button>
                    </form>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <footer className="border-t border-zinc-800 pt-6 text-xs text-zinc-500 space-y-1">
          <p>
            LLM pack:{" "}
            <code className="text-zinc-400">
              GET /api/subscribers/&lt;fanvueUuid&gt;/llm-pack
            </code>
          </p>
          <p>
            Swap stub replies in <code className="text-zinc-400">lib/llm.ts</code>.
          </p>
        </footer>
      </main>
    </div>
  );
}
