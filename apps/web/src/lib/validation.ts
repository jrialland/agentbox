export function requiredText(value: string, label: string): string | null {
  return value.trim() ? null : `${label} is required.`;
}

export function isHttpUrl(value: string, label = "URL"): string | null {
  const text = value.trim();
  if (!text) return null;
  try {
    const url = new URL(text);
    return url.protocol === "http:" || url.protocol === "https:"
      ? null
      : `${label} must use http or https.`;
  } catch {
    return `${label} must be a valid URL.`;
  }
}

export function isAbsolutePath(value: string): boolean {
  const text = value.trim();
  return text.startsWith("/") || /^[A-Za-z]:[\\/]/.test(text) || text.startsWith("\\\\");
}
