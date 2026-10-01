export function conversationPath(id: string): string {
  return `/app/c/${encodeURIComponent(id)}`;
}

export function titleFromQuery(text: string): string {
  const t = text.trim();
  return t.length > 60 ? t.slice(0, 57) + "..." : t;
}
