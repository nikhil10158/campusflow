export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function minToHHMM(minute: number): string {
  const hours = Math.floor(minute / 60);
  return `${String(hours).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

export function slotToHHMM(slot: number): string {
  return minToHHMM(slot * 15);
}

export function fmtDateTime(value: string): string {
  return new Date(value).toLocaleString("en-IN", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}

export function fmtDate(value: string): string {
  return new Date(value).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" });
}

export function fmtTime(value: string): string {
  return new Date(value).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function isoLocal(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
}

export function dateOnly(value: string): string {
  return value.slice(0, 10);
}

export function addDays(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00`);
  date.setDate(date.getDate() + days);
  return isoLocal(date).slice(0, 10);
}

export function weekdayOf(day: string): number {
  return (new Date(`${day}T00:00:00`).getDay() + 6) % 7;
}

export function titleCase(text: string): string {
  return text.replace(/[_-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function extractToken(text: string): string {
  const trimmed = text.trim();
  const marker = trimmed.lastIndexOf("/pass/");
  return marker >= 0 ? trimmed.slice(marker + 6) : trimmed;
}
