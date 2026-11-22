export const MODELS = {
  draft: "claude-sonnet-4-5",
  embed: "text-embedding-3-small",
  vision: "gemini-3.5-flash",
} as const;

const notAModel = "claude-code";
const alsoNot = "gemini-cli";
