// Providers supported by services/agent/llm_bridge.py.
export const PROVIDERS = [
  { id: 'local', label: 'Local GGUF (llama.cpp)', short: 'Local GGUF', local: true, needsKey: false, baseUrl: '' },
  { id: 'ollama', label: 'Ollama', short: 'Ollama', local: true, needsKey: false, baseUrl: 'http://localhost:11434' },
  { id: 'gemini', label: 'Google Gemini', short: 'Gemini', local: false, needsKey: true, baseUrl: 'https://generativelanguage.googleapis.com' },
  { id: 'claude', label: 'Anthropic Claude', short: 'Claude', local: false, needsKey: true, baseUrl: 'https://api.anthropic.com' },
  { id: 'openai', label: 'OpenAI', short: 'OpenAI', local: false, needsKey: true, baseUrl: 'https://api.openai.com/v1' },
  { id: 'deepseek', label: 'DeepSeek', short: 'DeepSeek', local: false, needsKey: true, baseUrl: 'https://api.deepseek.com' },
  { id: 'groq', label: 'Groq', short: 'Groq', local: false, needsKey: true, baseUrl: 'https://api.groq.com/openai/v1' },
  { id: 'custom', label: 'Custom OpenAI-compatible endpoint', short: 'Custom', local: false, needsKey: false, baseUrl: '' },
] as const;

export type ProviderId = (typeof PROVIDERS)[number]['id'];

export const DEFAULT_PROVIDER_MODELS: Record<string, string> = {
  local: 'qwen2.5-3b-instruct',
  ollama: 'llama3.2',
  gemini: 'gemini-2.0-flash',
  claude: 'claude-3-5-sonnet-20241022',
  openai: 'gpt-4o-mini',
  deepseek: 'deepseek-chat',
  groq: 'llama-3.3-70b-versatile',
  custom: 'custom-model',
};

export const PROVIDER_CATALOGS: Record<string, { id: string; name: string }[]> = {
  gemini: [
    { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash (Recommended · Fastest)' },
    { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro (Complex Reasoning)' },
    { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash (Lightweight)' },
  ],
  claude: [
    { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet (Recommended · Most Accurate)' },
    { id: 'claude-3-5-haiku-20241022', name: 'Claude 3.5 Haiku (Fast)' },
    { id: 'claude-3-opus-20240229', name: 'Claude 3 Opus' },
  ],
  openai: [
    { id: 'gpt-4o-mini', name: 'GPT-4o Mini (Recommended · Balanced)' },
    { id: 'gpt-4o', name: 'GPT-4o (High Precision)' },
    { id: 'o3-mini', name: 'o3-mini (Reasoning)' },
  ],
  deepseek: [
    { id: 'deepseek-chat', name: 'DeepSeek-V3 (deepseek-chat · Recommended)' },
    { id: 'deepseek-reasoner', name: 'DeepSeek-R1 (deepseek-reasoner · Chain of Thought)' },
  ],
  groq: [
    { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B Versatile (Recommended · Ultra Fast)' },
    { id: 'mixtral-8x7b-32768', name: 'Mixtral 8x7B (32k Context)' },
    { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B Instant (Sub-second)' },
  ],
};

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
