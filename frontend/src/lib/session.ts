/** Who is signed in (email) and the reports they requested from this browser. */
import { setToken } from "../api/client";

const EMAIL_KEY = "hindsight.email";

/** The signed-in user's email, or "" if unknown. */
export function currentEmail(): string {
  return sessionStorage.getItem(EMAIL_KEY) ?? "";
}

/** Remember who signed in (the token itself is kept by the API client). */
export function rememberSignIn(email: string, accessToken: string): void {
  sessionStorage.setItem(EMAIL_KEY, email);
  setToken(accessToken);
}

/** Forget the token and the email. */
export function signOut(): void {
  sessionStorage.removeItem(EMAIL_KEY);
  setToken(null);
}

/** What we keep locally about a report the user asked for, to list it without a list endpoint. */
export interface ReportRef {
  id: string;
  portfolioId: string;
  portfolioName: string;
  tickers: string[];
  credits: number;
  requestedAt: string;
}

/** Reports are listed per user; the API is still the source of truth for their status. */
function reportsKey(): string {
  return `hindsight.reports.${currentEmail()}`;
}

/** Reports this user requested from this browser, newest first. */
export function myReports(): ReportRef[] {
  try {
    return JSON.parse(localStorage.getItem(reportsKey()) ?? "[]") as ReportRef[];
  } catch {
    return [];
  }
}

/** Add a report to the local list (ignores duplicates, e.g. an idempotent replay). */
export function rememberReport(report: ReportRef): void {
  const all = myReports().filter((r) => r.id !== report.id);
  localStorage.setItem(reportsKey(), JSON.stringify([report, ...all].slice(0, 100)));
}
