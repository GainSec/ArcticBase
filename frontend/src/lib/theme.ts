import type { Theme } from "./api";

export function themeToCssVars(theme: Theme): string {
  const lines: string[] = [];
  for (const [k, v] of Object.entries(theme.tokens.core)) lines.push(`--wb-${k}: ${v};`);
  for (const [k, v] of Object.entries(theme.tokens.rounded)) lines.push(`--wb-rounded-${k}: ${v};`);
  for (const [k, v] of Object.entries(theme.tokens.spacing)) lines.push(`--wb-space-${k}: ${v};`);
  for (const [k, v] of Object.entries(theme.tokens.custom)) lines.push(`--wb-${k}: ${v};`);
  for (const [name, style] of Object.entries(theme.tokens.typography)) {
    if (style.fontFamily) lines.push(`--wb-font-${name}: ${style.fontFamily};`);
    if (style.fontSize) lines.push(`--wb-font-size-${name}: ${style.fontSize};`);
    if (style.fontWeight) lines.push(`--wb-font-weight-${name}: ${style.fontWeight};`);
    if (style.lineHeight) lines.push(`--wb-line-height-${name}: ${style.lineHeight};`);
    if (style.letterSpacing) lines.push(`--wb-letter-spacing-${name}: ${style.letterSpacing};`);
  }
  return lines.join(" ");
}
