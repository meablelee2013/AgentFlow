import { marked } from "marked";

// Configure marked for GitHub Flavored Markdown
marked.setOptions({
  gfm: true,
  breaks: true,
  async: false,
});

/**
 * Convert markdown string to sanitized HTML string.
 * Returns empty string for empty/falsy input.
 */
export function renderMarkdown(md: string): string {
  if (!md) return "";
  try {
    return marked.parse(md, { async: false }) as string;
  } catch {
    return md; // fallback: show raw text if parsing fails
  }
}
