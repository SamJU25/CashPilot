// Single source for motion presets; see .agent/skills/motion-craft/SKILL.md.
export const spring = {
  snappy: { type: 'spring', stiffness: 500, damping: 40, mass: 0.8 },
  smooth: { type: 'spring', stiffness: 300, damping: 34 },
  gentle: { type: 'spring', stiffness: 180, damping: 28 },
} as const;

export const fade = { duration: 0.16, ease: [0.16, 1, 0.3, 1] } as const;

export const STAGGER_S = 0.03;
