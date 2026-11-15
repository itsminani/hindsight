/** Formatting helpers so every screen shows dates, money and counts the same way. */

const DATE = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "short", day: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-CA", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** "2017-06-01" -> "Jun 1, 2017". Parsed as a calendar date, so no time-zone shift. */
export function formatDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  return DATE.format(new Date(y!, m! - 1, d!));
}

/** An ISO timestamp -> its calendar day in the user's time zone, e.g. "Nov 14, 2026". */
export function formatDay(iso: string): string {
  return DATE.format(new Date(iso));
}

/** An ISO timestamp -> "Nov 14, 14:19". */
export function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

/** The contract's Money string ("-290.00") -> "-$290.00". */
export function formatMoney(amount: string): string {
  return USD.format(Number(amount));
}

/** 1 -> "1 credit", 3 -> "3 credits". */
export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** How long a position was held, e.g. "2 yr 3 mo". */
export function holdingPeriod(buyDate: string, sellDate: string | null | undefined): string {
  const start = new Date(buyDate);
  const end = sellDate ? new Date(sellDate) : new Date();
  const months = (end.getFullYear() - start.getFullYear()) * 12 + end.getMonth() - start.getMonth();
  const years = Math.floor(months / 12);
  const rest = months % 12;
  if (years === 0) return `${rest} mo`;
  return rest === 0 ? `${years} yr` : `${years} yr ${rest} mo`;
}
