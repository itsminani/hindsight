/**
 * Data hooks (TanStack Query) on top of the typed client. Pages call these instead of fetching
 * by hand: caching, loading/error states, refetching and polling all come from the library.
 */
import { useQuery } from "@tanstack/react-query";
import { api, type Problem } from "./client";

/** An API error carrying the contract's Problem body, so screens can show its message. */
export class ApiProblem extends Error {
  constructor(readonly problem: Partial<Problem>) {
    super(problem.detail ?? problem.title ?? "Request failed");
  }
}

/** openapi-fetch returns { data } or { error }; queries want data or a thrown error. */
export function unwrap<T>(result: { data?: T; error?: unknown }): T {
  if (result.data !== undefined) return result.data;
  throw new ApiProblem((result.error ?? {}) as Partial<Problem>);
}

/** Query keys in one place, so mutations know what to refresh. */
export const keys = {
  plan: ["plan"] as const,
  portfolios: ["portfolios"] as const,
  portfolio: (id: string) => ["portfolios", id] as const,
  report: (id: string) => ["reports", id] as const,
};

/** The caller's plan and credits. */
export function usePlan() {
  return useQuery({ queryKey: keys.plan, queryFn: async () => unwrap(await api.GET("/plans/me")) });
}

/** The caller's portfolios with their positions. */
export function usePortfolios() {
  return useQuery({
    queryKey: keys.portfolios,
    queryFn: async () => unwrap(await api.GET("/portfolios")).items,
  });
}

/** One portfolio (404 if it is not the caller's). */
export function usePortfolio(portfolioId: string) {
  return useQuery({
    queryKey: keys.portfolio(portfolioId),
    queryFn: async () =>
      unwrap(await api.GET("/portfolios/{portfolioId}", { params: { path: { portfolioId } } })),
  });
}

/**
 * One report. While it is pending, poll with backoff: 2 s, 4 s, 8 s, then every 15 s.
 * Done or failed reports never change again, so polling stops.
 */
export function useReport(reportId: string) {
  return useQuery({
    queryKey: keys.report(reportId),
    queryFn: async () =>
      unwrap(await api.GET("/hindsight-reports/{reportId}", { params: { path: { reportId } } })),
    refetchInterval: (query) =>
      query.state.data?.status === "pending"
        ? Math.min(2000 * 2 ** Math.max(query.state.dataUpdateCount - 1, 0), 15000)
        : false,
  });
}

/** Weekly closes for a ticker since a date (for the report charts). Prices don't change often. */
export function usePriceHistory(ticker: string, from: string) {
  return useQuery({
    queryKey: ["prices", ticker, from],
    queryFn: async () =>
      unwrap(await api.GET("/tickers/{ticker}/prices", { params: { path: { ticker }, query: { from } } })),
    staleTime: 60 * 60 * 1000,
  });
}
