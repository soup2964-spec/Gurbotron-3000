export type ReplyContext = {
  masterPrompt: string;
  guidelines: string;
  subscriberHandle: string | null;
  subscriberUuid: string;
  llmContext: Record<string, unknown>;
  facts: Record<string, string>;
  recentMessages: [role: string, text: string][];
};

export type ReplyGenerator = {
  generate(ctx: ReplyContext): Promise<[text: string, ppvPriceCents: number | null]>;
};

/** Swap for OpenAI / Anthropic / etc. */
export class StubReplyGenerator implements ReplyGenerator {
  async generate(ctx: ReplyContext): Promise<[string, number | null]> {
    const factsPreview = Object.entries(ctx.facts)
      .slice(0, 5)
      .map(([k, v]) => `${k}=${v}`)
      .join(", ");
    const tail = factsPreview ? ` (I remember: ${factsPreview})` : "";
    return [
      `[auto/stub] hey love thanks for texting 💕 wire a real LLM in lib/llm.ts.${tail}`,
      null,
    ];
  }
}

export const defaultGenerator: ReplyGenerator = new StubReplyGenerator();
