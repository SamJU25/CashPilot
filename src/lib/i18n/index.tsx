'use client';

import { Fragment, useCallback } from 'react';
import { useWorkspace } from '@/lib/workspace';
import { ar } from './ar';
import { bn } from './bn';
import { de } from './de';
import { en, type Key } from './en';
import { es } from './es';
import { fr } from './fr';
import { hi } from './hi';
import { id } from './id';
import { it } from './it';
import { ja } from './ja';
import { LANGUAGES, type Lang } from './languages';
import { pt } from './pt';
import { zh } from './zh';
import { zhTW } from './zh-TW';

export type { Key, Lang };
export { LANGUAGES };

const DICTS: Record<Lang, Partial<Record<Key, string>>> = {
  en,
  zh,
  'zh-TW': zhTW,
  es,
  fr,
  de,
  ja,
  ar,
  pt,
  it,
  hi,
  bn,
  id,
};

type Vars = Record<string, string | number>;

export function translate(lang: Lang, key: Key, vars?: Vars): string {
  const dict = DICTS[lang] ?? en;
  const oneKey = `${key}_one` as Key;
  const k = vars?.n === 1 && oneKey in dict ? oneKey : key;
  const template = dict[k] ?? en[k] ?? key;
  return vars ? template.replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m)) : template;
}

/** Like translate, but placeholders can be React nodes (e.g. a styled amount). */
function richTranslate(lang: Lang, key: Key, vars: Record<string, React.ReactNode>): React.ReactNode {
  const template = DICTS[lang]?.[key] ?? en[key] ?? key;
  return template.split(/(\{\w+\})/g).map((part, i) => {
    const name = part.match(/^\{(\w+)\}$/)?.[1];
    return <Fragment key={i}>{name && name in vars ? vars[name] : part}</Fragment>;
  });
}

export function useT() {
  const { language } = useWorkspace();
  const t = useCallback((key: Key, vars?: Vars) => translate(language, key, vars), [language]);
  const rich = useCallback((key: Key, vars: Record<string, React.ReactNode>) => richTranslate(language, key, vars), [language]);
  return { t, rich, lang: language };
}

export type T = (key: Key, vars?: Vars) => string;
