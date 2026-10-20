// Providers supported by services/agent/llm_bridge.py.
export const PROVIDERS = [
  { id: 'local', label: 'MiniCPM5-2B (local model)', short: 'MiniCPM5-2B', local: true, needsKey: false, baseUrl: '' },
  { id: 'ollama', label: 'Ollama', short: 'Ollama', local: true, needsKey: false, baseUrl: 'http://localhost:11434' },
  { id: 'gemini', label: 'Google Gemini', short: 'Gemini', local: false, needsKey: true, baseUrl: 'https://generativelanguage.googleapis.com' },
  { id: 'claude', label: 'Anthropic Claude', short: 'Claude', local: false, needsKey: true, baseUrl: 'https://api.anthropic.com' },
  { id: 'openai', label: 'OpenAI', short: 'OpenAI', local: false, needsKey: true, baseUrl: 'https://api.openai.com/v1' },
  { id: 'deepseek', label: 'DeepSeek', short: 'DeepSeek', local: false, needsKey: true, baseUrl: 'https://api.deepseek.com' },
  { id: 'groq', label: 'Groq', short: 'Groq', local: false, needsKey: true, baseUrl: 'https://api.groq.com/openai/v1' },
  { id: 'custom', label: 'Custom OpenAI-compatible endpoint', short: 'Custom', local: false, needsKey: true, baseUrl: '' },
] as const;

export type ProviderId = (typeof PROVIDERS)[number]['id'];

/** Display name in the current language; only the two generic entries need translating. */
export function providerName(id: string, t: (key: 'provider.local' | 'provider.localShort' | 'provider.custom' | 'provider.customShort') => string, short = false): string | null {
  if (id === 'local') return t(short ? 'provider.localShort' : 'provider.local');
  if (id === 'custom') return t(short ? 'provider.customShort' : 'provider.custom');
  const p = PROVIDERS.find((x) => x.id === id);
  return p ? (short ? p.short : p.label) : null;
}

/** A model can answer once it has what it needs: a key for cloud providers, an address for custom ones. */
export function isProviderReady(id: string, keys: Record<string, string>, urls: Record<string, string>): boolean {
  const p = PROVIDERS.find((x) => x.id === id);
  if (!p) return false;
  if (p.needsKey && !keys[id]?.trim()) return false;
  if (id === 'custom' && !urls[id]?.trim()) return false;
  return true;
}
