// Lateness escalates from caution to critical; "not yet due" stays neutral.
export const BUCKET_COLORS: Record<string, string> = {
  current: 'rgb(var(--muted-foreground) / 0.35)',
  d1_30: 'rgb(var(--warning) / 0.7)',
  d31_60: 'rgb(var(--serious))',
  d61_90: 'rgb(var(--critical))',
  d90_plus: 'rgb(var(--critical-text))',
};

// Spending categories: identity, in a fixed order so a category keeps its colour on every page.
export const CATEGORY_COLORS: Record<string, string> = {
  everyday: 'rgb(var(--s1))',
  payroll: 'rgb(var(--s2))',
  utilities: 'rgb(var(--s3))',
  rent: 'rgb(var(--s4))',
  debt: 'rgb(var(--ink-2) / 0.7)',
  tax: 'rgb(var(--muted-foreground) / 0.45)',
};
