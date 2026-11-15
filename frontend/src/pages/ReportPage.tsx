import { useState } from "react";
import { Link, useParams } from "react-router";
import type { Schemas } from "../api/client";
import { usePortfolio, usePriceHistory, useReport } from "../api/queries";
import { PriceSinceSaleChart, SoldVsTodayChart, TickerChip } from "../components/charts";
import { PageHead, StatusPill } from "../components/ui";
import { formatDate, formatDateTime, formatMoney, plural } from "../lib/format";
import { myReports } from "../lib/session";

/** One report: calculating, failed (credits returned), or done with the results and a chart. */
export function ReportPage() {
  const { reportId = "" } = useParams();
  const report = useReport(reportId);

  if (report.isLoading) return <p className="muted">Loading…</p>;
  if (report.isError || !report.data) {
    return (
      <div className="panel empty">
        <h3>Report not found</h3>
        <p>
          It doesn't exist, or it isn't yours. <Link to="/reports">Back to reports</Link>
        </p>
      </div>
    );
  }

  const r = report.data;
  const ref = myReports().find((x) => x.id === r.id);
  const results = r.results ?? [];
  const total = results.reduce((sum, x) => sum + Number(x.difference), 0);

  return (
    <>
      <PageHead
        crumb={
          <Link to="/reports" className="crumb">
            ← Reports
          </Link>
        }
        title="Hindsight report"
        subtitle={`Requested ${formatDateTime(r.createdAt)}`}
        actions={<StatusPill status={r.status} />}
      />

      {r.status === "pending" && (
        <section className="panel empty">
          {ref && (
            <div className="row" style={{ justifyContent: "center", marginBottom: 16, gap: 6 }}>
              {ref.tickers.map((t) => (
                <TickerChip key={t} ticker={t} />
              ))}
            </div>
          )}
          <h3>Calculating your report</h3>
          <p>
            We're fetching historical prices and adjusting for splits. This page updates by itself; you can
            also leave and come back.
          </p>
          {ref && (
            <p className="small" style={{ marginTop: 10 }}>
              {plural(ref.credits, "credit")} held from your plan while it runs · {ref.portfolioName}
            </p>
          )}
        </section>
      )}

      {r.status === "failed" && (
        <section className="panel panel-pad stack" style={{ gap: 8 }}>
          <h2>We couldn't finish this report</h2>
          <p className="muted">{r.failureReason ?? "Something went wrong on our side."}</p>
          <p className="notice">Your credits were returned to your plan.</p>
        </section>
      )}

      {r.status === "done" && (
        <div className="stack">
          <section className="panel panel-pad">
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <span className="small muted">{total > 0 ? "Selling cost you" : "Selling saved you"}</span>
                <div className="hero-figure">{formatMoney(String(Math.abs(total)))}</div>
                <p className="small muted" style={{ marginTop: 6 }}>
                  Across {plural(results.length, "lot")} · {plural(r.creditsCharged ?? 0, "credit")} used
                </p>
              </div>
              {r.priceSource === "demo" && (
                <span className="pill pending" title="Generated prices: add a Tiingo API key for real data">
                  Demo prices, not real market data
                </span>
              )}
            </div>
          </section>

          <SinceYouSold portfolioId={r.portfolioId} results={results} />

          <section className="panel panel-pad">
            <h2 style={{ marginBottom: 12 }}>Sold for vs worth today</h2>
            <SoldVsTodayChart results={results} />
          </section>
          <section className="panel">
            <table className="table">
              <thead>
                <tr>
                  <th>Stock</th>
                  <th className="right">Shares</th>
                  <th className="right">Sold for</th>
                  <th className="right">Worth today</th>
                  <th className="right">Difference</th>
                </tr>
              </thead>
              <tbody>
                {results.map((x) => (
                  <tr key={x.positionId}>
                    <td>
                      <span className="row" style={{ gap: 10 }}>
                        <TickerChip ticker={x.ticker} />
                        <span className="ticker">{x.ticker}</span>
                      </span>
                    </td>
                    <td className="right num">{x.shares}</td>
                    <td className="right num">{formatMoney(x.soldFor)}</td>
                    <td className="right num">{formatMoney(x.worthToday)}</td>
                    <td className={`right delta ${Number(x.difference) > 0 ? "down" : "up"}`}>
                      {formatMoney(x.difference)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </div>
      )}
    </>
  );
}

/** "Since you sold": pick a stock, see its price from a year before the sale until today. */
function SinceYouSold({ portfolioId, results }: { portfolioId: string; results: Schemas["ReportResult"][] }) {
  const portfolio = usePortfolio(portfolioId);
  const [selected, setSelected] = useState(results[0]?.positionId ?? "");
  const result = results.find((x) => x.positionId === selected) ?? results[0];
  const soldOn = portfolio.data?.positions.find((p) => p.id === result?.positionId)?.sellDate;
  if (!result || !soldOn) return null;

  return (
    <section className="panel panel-pad">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <h2>Since you sold</h2>
        <div className="chart-tabs" role="tablist" aria-label="Stock">
          {results.map((x) => (
            <button
              key={x.positionId}
              role="tab"
              aria-selected={x.positionId === result.positionId}
              className={x.positionId === result.positionId ? "active" : ""}
              onClick={() => setSelected(x.positionId)}
            >
              {x.ticker}
            </button>
          ))}
        </div>
      </div>
      <PriceChartFor ticker={result.ticker} soldOn={soldOn} />
      <p className="small muted" style={{ marginTop: 8 }}>
        You sold {result.shares} shares of {result.ticker} on {formatDate(soldOn)}. Prices are weekly closes,
        adjusted for splits and dividends.
      </p>
    </section>
  );
}

/** Loads one ticker's price history (from a year before the sale) and draws it. */
function PriceChartFor({ ticker, soldOn }: { ticker: string; soldOn: string }) {
  const yearBefore = `${Number(soldOn.slice(0, 4)) - 1}${soldOn.slice(4)}`;
  const history = usePriceHistory(ticker, yearBefore);
  if (history.isLoading) return <p className="muted">Loading prices…</p>;
  if (history.isError || !history.data) return <p className="error-text">{history.error?.message}</p>;
  return <PriceSinceSaleChart prices={history.data.prices} soldOn={soldOn} />;
}
