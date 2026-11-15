import { Link, useNavigate } from "react-router";
import { useReport } from "../api/queries";
import { TickerChip } from "../components/charts";
import { PageHead, StatusPill } from "../components/ui";
import { formatDateTime, plural } from "../lib/format";
import { myReports, type ReportRef } from "../lib/session";

/** Reports the user ran from this browser, newest first, each with its live status. */
export function ReportsPage() {
  const reports = myReports();

  return (
    <>
      <PageHead title="Reports" subtitle="What your past sales cost you, one report at a time." />
      <section className="panel">
        {reports.length === 0 ? (
          <div className="empty">
            <h3>No reports yet</h3>
            <p>
              Open a <Link to="/portfolios">portfolio</Link>, tick the lots you sold, and run a report.
            </p>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Stocks</th>
                <th>Portfolio</th>
                <th>Requested</th>
                <th className="right">Credits</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <ReportRow key={r.id} report={r} />
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

/** One row; its status comes from the API (and keeps updating while pending). */
function ReportRow({ report }: { report: ReportRef }) {
  const navigate = useNavigate();
  const live = useReport(report.id);
  return (
    <tr className="clickable" onClick={() => navigate(`/reports/${report.id}`)}>
      <td>
        <span className="row" style={{ gap: 6 }}>
          {report.tickers.slice(0, 4).map((t) => (
            <TickerChip key={t} ticker={t} />
          ))}
        </span>
      </td>
      <td>{report.portfolioName}</td>
      <td className="num muted">{formatDateTime(report.requestedAt)}</td>
      <td className="right num">{plural(report.credits, "credit")}</td>
      <td>{live.data ? <StatusPill status={live.data.status} /> : <span className="muted">…</span>}</td>
    </tr>
  );
}
