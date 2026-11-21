export const UNTITLED_SESSION_TITLE = "Untitled session";

export function sessionTitle(title: string | null | undefined): string {
  const trimmed = title?.trim();
  return trimmed ? trimmed : UNTITLED_SESSION_TITLE;
}
