export interface CurrencyMetadata {
  code: string;
  name: string;
  symbol: string;
  decimals: number;
  region: string;
}

export const WORLD_CURRENCIES: CurrencyMetadata[] = [
  // Major Global Reserve Currencies
  { code: 'USD', name: 'United States Dollar', symbol: '$', decimals: 2, region: 'Americas' },
  { code: 'EUR', name: 'Euro', symbol: '€', decimals: 2, region: 'Europe' },
  { code: 'GBP', name: 'British Pound Sterling', symbol: '£', decimals: 2, region: 'Europe' },
  { code: 'JPY', name: 'Japanese Yen', symbol: '¥', decimals: 0, region: 'Asia-Pacific' },
  { code: 'CHF', name: 'Swiss Franc', symbol: 'CHF', decimals: 2, region: 'Europe' },
  { code: 'CNY', name: 'Chinese Yuan Renminbi', symbol: '¥', decimals: 2, region: 'Asia-Pacific' },
  { code: 'CAD', name: 'Canadian Dollar', symbol: 'C$', decimals: 2, region: 'Americas' },
  { code: 'AUD', name: 'Australian Dollar', symbol: 'A$', decimals: 2, region: 'Asia-Pacific' },
  { code: 'NZD', name: 'New Zealand Dollar', symbol: 'NZ$', decimals: 2, region: 'Asia-Pacific' },
  { code: 'SGD', name: 'Singapore Dollar', symbol: 'S$', decimals: 2, region: 'Asia-Pacific' },
  { code: 'HKD', name: 'Hong Kong Dollar', symbol: 'HK$', decimals: 2, region: 'Asia-Pacific' },

  // South Asia & Southeast Asia
  { code: 'BDT', name: 'Bangladeshi Taka', symbol: '৳', decimals: 2, region: 'Asia-Pacific' },
  { code: 'INR', name: 'Indian Rupee', symbol: '₹', decimals: 2, region: 'Asia-Pacific' },
  { code: 'PKR', name: 'Pakistani Rupee', symbol: '₨', decimals: 2, region: 'Asia-Pacific' },
  { code: 'LKR', name: 'Sri Lankan Rupee', symbol: 'Rs', decimals: 2, region: 'Asia-Pacific' },
  { code: 'NPR', name: 'Nepalese Rupee', symbol: 'रू', decimals: 2, region: 'Asia-Pacific' },
  { code: 'MYR', name: 'Malaysian Ringgit', symbol: 'RM', decimals: 2, region: 'Asia-Pacific' },
  { code: 'IDR', name: 'Indonesian Rupiah', symbol: 'Rp', decimals: 0, region: 'Asia-Pacific' },
  { code: 'THB', name: 'Thai Baht', symbol: '฿', decimals: 2, region: 'Asia-Pacific' },
  { code: 'VND', name: 'Vietnamese Dong', symbol: '₫', decimals: 0, region: 'Asia-Pacific' },
  { code: 'PHP', name: 'Philippine Peso', symbol: '₱', decimals: 2, region: 'Asia-Pacific' },
  { code: 'KRW', name: 'South Korean Won', symbol: '₩', decimals: 0, region: 'Asia-Pacific' },
  { code: 'TWD', name: 'New Taiwan Dollar', symbol: 'NT$', decimals: 2, region: 'Asia-Pacific' },

  // Middle East & North Africa
  { code: 'AED', name: 'UAE Dirham', symbol: 'د.إ', decimals: 2, region: 'Middle East & Africa' },
  { code: 'SAR', name: 'Saudi Riyal', symbol: '﷼', decimals: 2, region: 'Middle East & Africa' },
  { code: 'QAR', name: 'Qatari Riyal', symbol: 'QR', decimals: 2, region: 'Middle East & Africa' },
  { code: 'KWD', name: 'Kuwaiti Dinar', symbol: 'KD', decimals: 3, region: 'Middle East & Africa' },
  { code: 'BHD', name: 'Bahraini Dinar', symbol: 'BD', decimals: 3, region: 'Middle East & Africa' },
  { code: 'OMR', name: 'Omani Rial', symbol: 'RO', decimals: 3, region: 'Middle East & Africa' },
  { code: 'ILS', name: 'Israeli New Shekel', symbol: '₪', decimals: 2, region: 'Middle East & Africa' },
  { code: 'TRY', name: 'Turkish Lira', symbol: '₺', decimals: 2, region: 'Middle East & Africa' },
  { code: 'EGP', name: 'Egyptian Pound', symbol: 'E£', decimals: 2, region: 'Middle East & Africa' },

  // Latin America
  { code: 'BRL', name: 'Brazilian Real', symbol: 'R$', decimals: 2, region: 'Americas' },
  { code: 'MXN', name: 'Mexican Peso', symbol: 'Mex$', decimals: 2, region: 'Americas' },
  { code: 'COP', name: 'Colombian Peso', symbol: 'COL$', decimals: 2, region: 'Americas' },
  { code: 'CLP', name: 'Chilean Peso', symbol: 'CLP$', decimals: 0, region: 'Americas' },
  { code: 'ARS', name: 'Argentine Peso', symbol: 'AR$', decimals: 2, region: 'Americas' },
  { code: 'PEN', name: 'Peruvian Sol', symbol: 'S/', decimals: 2, region: 'Americas' },

  // Europe (Non-Euro)
  { code: 'SEK', name: 'Swedish Krona', symbol: 'kr', decimals: 2, region: 'Europe' },
  { code: 'NOK', name: 'Norwegian Krone', symbol: 'kr', decimals: 2, region: 'Europe' },
  { code: 'DKK', name: 'Danish Krone', symbol: 'kr', decimals: 2, region: 'Europe' },
  { code: 'PLN', name: 'Polish Zloty', symbol: 'zł', decimals: 2, region: 'Europe' },
  { code: 'CZK', name: 'Czech Koruna', symbol: 'Kč', decimals: 2, region: 'Europe' },
  { code: 'HUF', name: 'Hungarian Forint', symbol: 'Ft', decimals: 2, region: 'Europe' },
  { code: 'RON', name: 'Romanian Leu', symbol: 'lei', decimals: 2, region: 'Europe' },

  // Africa
  { code: 'ZAR', name: 'South African Rand', symbol: 'R', decimals: 2, region: 'Middle East & Africa' },
  { code: 'NGN', name: 'Nigerian Naira', symbol: '₦', decimals: 2, region: 'Middle East & Africa' },
  { code: 'KES', name: 'Kenyan Shilling', symbol: 'KSh', decimals: 2, region: 'Middle East & Africa' },
  { code: 'GHS', name: 'Ghanaian Cedi', symbol: 'GH₵', decimals: 2, region: 'Middle East & Africa' },
  { code: 'MAD', name: 'Moroccan Dirham', symbol: 'DH', decimals: 2, region: 'Middle East & Africa' },
];

export const SYMBOL_MAP: Record<string, string> = Object.fromEntries(
  WORLD_CURRENCIES.map((c) => [c.code, c.symbol]),
);

export function getCurrencySymbol(code: string): string {
  return SYMBOL_MAP[code.toUpperCase()] ?? code;
}
