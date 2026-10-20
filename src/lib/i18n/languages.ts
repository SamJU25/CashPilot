// No imports: lib/format.ts reads this, and the dictionaries import from elsewhere.
// `-u-nu-latn` keeps Western digits in dates so they match the money figures beside them.
export const LANGUAGES = [
  { id: 'en', label: 'English', englishName: 'English', htmlLang: 'en', dateLocale: 'en-US' },
  { id: 'zh', label: '简体中文', englishName: 'Simplified Chinese', htmlLang: 'zh-CN', dateLocale: 'zh-CN' },
  { id: 'zh-TW', label: '繁體中文', englishName: 'Traditional Chinese', htmlLang: 'zh-TW', dateLocale: 'zh-TW' },
  { id: 'es', label: 'Español', englishName: 'Spanish', htmlLang: 'es', dateLocale: 'es-ES' },
  { id: 'fr', label: 'Français', englishName: 'French', htmlLang: 'fr', dateLocale: 'fr-FR' },
  { id: 'de', label: 'Deutsch', englishName: 'German', htmlLang: 'de', dateLocale: 'de-DE' },
  { id: 'ja', label: '日本語', englishName: 'Japanese', htmlLang: 'ja', dateLocale: 'ja-JP' },
  { id: 'ar', label: 'العربية', englishName: 'Arabic', htmlLang: 'ar', dateLocale: 'ar-SA-u-nu-latn' },
  { id: 'pt', label: 'Português', englishName: 'Portuguese', htmlLang: 'pt', dateLocale: 'pt-BR' },
  { id: 'it', label: 'Italiano', englishName: 'Italian', htmlLang: 'it', dateLocale: 'it-IT' },
  { id: 'hi', label: 'हिन्दी', englishName: 'Hindi', htmlLang: 'hi', dateLocale: 'hi-IN-u-nu-latn' },
  { id: 'bn', label: 'বাংলা', englishName: 'Bengali', htmlLang: 'bn', dateLocale: 'bn-BD-u-nu-latn' },
  { id: 'id', label: 'Bahasa Indonesia', englishName: 'Indonesian', htmlLang: 'id', dateLocale: 'id-ID' },
] as const;

export type Lang = (typeof LANGUAGES)[number]['id'];

/** Best match for the browser's language on a first visit. */
export function detectLanguage(browser: string): Lang {
  const b = browser.toLowerCase();
  if (/^zh-(tw|hk|mo)|^zh-hant/.test(b)) return 'zh-TW';
  const base = b.split('-')[0];
  return (LANGUAGES.find((l) => l.id === base)?.id as Lang | undefined) ?? 'en';
}
