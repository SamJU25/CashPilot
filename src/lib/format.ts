import { LANGUAGES, type Lang } from '@/lib/i18n/languages';
import { getCurrencySymbol } from '@/lib/currencies';

// Money arrives as decimal strings; formatting stays string-based so no value round-trips through a float.

const symbolCache = new Map<string, string>();

function currencySymbol(currency: string): string {
  let symbol = symbolCache.get(currency);
  if (!symbol) {
    const known = getCurrencySymbol(currency);
    if (known && known !== currency) {
      symbol = known;
    } else {
      try {
        symbol =
          new Intl.NumberFormat('en-US', { style: 'currency', currency, currencyDisplay: 'narrowSymbol' })
            .formatToParts(0)
            .find((p) => p.type === 'currency')?.value ?? `${currency} `;
      } catch {
        symbol = `${currency} `;
      }
    }
    symbolCache.set(currency, symbol);
  }
  return symbol;
}

interface MoneyOptions {
  signed?: boolean;
  cents?: boolean;
}

// shortcut: module-level like the date language below; WorkspaceProvider sets it to the currency of the
// data on screen. One currency per workspace until mixed-currency conversion lands (handoff item 4).
let displayCurrency = 'USD';
export function setMoneyCurrency(currency: string) {
  displayCurrency = currency;
}

export function formatMoney(value: string | number | null | undefined, currency = displayCurrency, { signed = false, cents = true }: MoneyOptions = {}): string {
  if (value === null || value === undefined) return `${currencySymbol(currency)}0.00`;
  const str = typeof value === 'number' ? value.toFixed(2) : String(value);
  const negative = str.trim().startsWith('-');
  const [intPart, fracPart = ''] = str.trim().replace(/^[-+]/, '').split('.');
  const grouped = (intPart || '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const frac = cents ? `.${fracPart.padEnd(2, '0').slice(0, 2)}` : '';
  const sign = negative ? '−' : signed ? '+' : '';
  return `${sign}${currencySymbol(currency)}${grouped}${frac}`;
}

export function centsToString(cents: number): string {
  const negative = cents < 0;
  const abs = Math.abs(Math.round(cents));
  return `${negative ? '-' : ''}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`;
}

/** "7500.5" -> 750050, by string so no float touches the amount. */
export function stringToCents(value: string): number {
  const negative = value.trim().startsWith('-');
  const [intPart, fracPart = ''] = value.trim().replace(/^[-+]/, '').split('.');
  const cents = Number(intPart || '0') * 100 + Number(fracPart.padEnd(2, '0').slice(0, 2));
  return negative ? -cents : cents;
}

// shortcut: module-level date language set by WorkspaceProvider during render; fine for this
// client-rendered app, switch to passing the language explicitly if dates render on the server.
let dateLocale = 'en-US';
const formatters = new Map<string, Intl.DateTimeFormat>();

export function setDateLanguage(lang: Lang) {
  dateLocale = LANGUAGES.find((l) => l.id === lang)?.dateLocale ?? 'en-US';
}

function formatter(withYear: boolean) {
  const key = `${dateLocale}|${withYear}`;
  let f = formatters.get(key);
  if (!f) {
    // UTC so a calendar date never shifts a day in the viewer's timezone.
    f = new Intl.DateTimeFormat(dateLocale, { month: 'short', day: 'numeric', year: withYear ? 'numeric' : undefined, timeZone: 'UTC' });
    formatters.set(key, f);
  }
  return f;
}

/** "2026-10-28" -> "Oct 28" / "10月28日" / "28 oct" (year optional), in the selected language. */
export function formatDate(iso: string | null | undefined, withYear = false): string {
  if (!iso) return '';
  const clean = String(iso).slice(0, 10);
  const time = Date.parse(`${clean}T00:00:00Z`);
  if (isNaN(time)) return String(iso);
  return formatter(withYear).format(new Date(time));
}

export function formatDateTime(iso: string): string {
  return `${formatDate(iso)}, ${iso.slice(11, 16)}`;
}
