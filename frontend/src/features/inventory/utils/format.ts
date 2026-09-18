import Decimal from "decimal.js";

Decimal.set({ precision: 40, rounding: Decimal.ROUND_HALF_UP });
export function normalizeDecimal(value: string): string {
  const normalized = value.trim().replace(",", ".");
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) throw new Error("Nhập số hợp lệ; dùng dấu phẩy hoặc dấu chấm cho phần thập phân.");
  return new Decimal(normalized).toFixed();
}
export const compareDecimal = (a: string | number, b: string | number) => new Decimal(a).cmp(b);
export const addDecimal = (a: string | number, b: string | number) => new Decimal(a).plus(b).toFixed();
export const subtractDecimal = (a: string | number, b: string | number) => new Decimal(a).minus(b).toFixed();
export const multiplyDecimal = (a: string | number, b: string | number) => new Decimal(a).times(b).toFixed();
export const roundDecimal = (value: string | number, places = 2) => new Decimal(value).toFixed(places);
function localized(value: string | number, places: number, fixed = false) {
  const [integer, fraction] = new Decimal(value).toFixed(places).split(".");
  const tail = fixed ? fraction : fraction?.replace(/0+$/, "");
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (tail ? `,${tail}` : "");
}
export const quantity = (value: string | number | null | undefined) => value == null ? "—" : localized(value, 3);
export const money = (value: string | number | null | undefined) => value == null ? "—" : `${localized(value, 2)} ₫`;
export function date(value: string | null | undefined) {
  if (!value) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : "—";
}
export function dateTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(/[Zz]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(parsed.getTime()) ? "—" : new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Ho_Chi_Minh" }).format(parsed);
}
export function todayISO(now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Ho_Chi_Minh", year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  return ["year", "month", "day"].map(type => parts.find(p => p.type === type)?.value).join("-");
}
export const EXPIRY_THRESHOLDS = [3, 7, 14] as const;
export function expiryDays(expiry: string | null, today = todayISO()): number | null {
  return expiry ? Math.round((Date.parse(`${expiry}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86400000) : null;
}
export function expiryStatus(expiry: string | null, today = todayISO()) {
  const days = expiryDays(expiry, today);
  return days === null ? "NO_EXPIRY" : days < 0 ? "EXPIRED" : days <= EXPIRY_THRESHOLDS[0] ? "EXPIRING_3" : days <= EXPIRY_THRESHOLDS[1] ? "EXPIRING_7" : days <= EXPIRY_THRESHOLDS[2] ? "EXPIRING_14" : "FRESH";
}
