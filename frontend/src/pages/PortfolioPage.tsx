import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { api, type Schemas } from "../api/client";
import { keys, unwrap, usePlan, usePortfolio } from "../api/queries";
import { HoldingTimeline, TickerChip } from "../components/charts";
import { Dialog, PageHead } from "../components/ui";
import { formatDate, formatDay, holdingPeriod, plural } from "../lib/format";
import { rememberReport } from "../lib/session";

/** One portfolio: when each lot was held, the lots themselves, and "run a hindsight report". */
export function PortfolioPage() {
  const { portfolioId = "" } = useParams();
  const portfolio = usePortfolio(portfolioId);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [confirming, setConfirming] = useState(false);

  if (portfolio.isLoading) return <p className="muted">Loading…</p>;
  if (portfolio.isError || !portfolio.data) {
    return (
      <div className="panel empty">
        <h3>Portfolio not found</h3>
        <p>
          It doesn't exist, or it isn't yours. <Link to="/portfolios">Back to portfolios</Link>
        </p>
      </div>
    );
  }

  const p = portfolio.data;
  const sold = p.positions.filter((x) => x.sellDate);
  const chosen = p.positions.filter((x) => picked.has(x.id));

  /** Tick or untick a sold lot for the next report. */
  function toggle(id: string) {
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <>
      <PageHead
        crumb={
          <Link to="/portfolios" className="crumb">
            ← Portfolios
          </Link>
        }
        title={p.name}
        subtitle={`${plural(p.positions.length, "lot")} · ${sold.length} sold · created ${formatDay(p.createdAt)}`}
        actions={
          <>
            <button className="btn" onClick={() => setAdding(true)}>
              Add a lot
            </button>
            <button
              className="btn primary"
              disabled={chosen.length === 0}
              onClick={() => setConfirming(true)}
            >
              {chosen.length === 0 ? "Run hindsight report" : `Run report on ${plural(chosen.length, "lot")}`}
            </button>
          </>
        }
      />

      <div className="stack">
        {p.positions.length > 0 && (
          <section className="panel panel-pad">
            <h2 style={{ marginBottom: 4 }}>When you owned each lot</h2>
            <p className="small muted">Bars run from the purchase to the sale.</p>
            <HoldingTimeline positions={p.positions} />
          </section>
        )}

        <section className="panel">
          <div className="panel-head">
            <h2>Lots</h2>
            <span className="small muted">Tick sold lots to include them in a report.</span>
          </div>
          {p.positions.length === 0 ? (
            <div className="empty">
              <h3>No lots yet</h3>
              <p>Add a stock you bought, with the date you sold it if you did.</p>
            </div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 40 }} />
                  <th>Stock</th>
                  <th className="right">Shares</th>
                  <th>Bought</th>
                  <th>Sold</th>
                  <th className="right">Held for</th>
                </tr>
              </thead>
              <tbody>
                {p.positions.map((x) => (
                  <tr
                    key={x.id}
                    className={x.sellDate ? "clickable" : ""}
                    onClick={() => x.sellDate && toggle(x.id)}
                  >
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Include ${x.ticker} in a report`}
                        disabled={!x.sellDate}
                        checked={picked.has(x.id)}
                        onChange={() => toggle(x.id)}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </td>
                    <td>
                      <span className="row" style={{ gap: 10 }}>
                        <TickerChip ticker={x.ticker} />
                        <span className="ticker">{x.ticker}</span>
                      </span>
                    </td>
                    <td className="right num">{x.shares}</td>
                    <td className="num">{formatDate(x.buyDate)}</td>
                    <td className="num">
                      {x.sellDate ? formatDate(x.sellDate) : <span className="pill">Still held</span>}
                    </td>
                    <td className="right num muted">{holdingPeriod(x.buyDate, x.sellDate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>

      {adding && <AddLotDialog portfolioId={p.id} onClose={() => setAdding(false)} />}
      {confirming && <RunReportDialog portfolio={p} lots={chosen} onClose={() => setConfirming(false)} />}
    </>
  );
}

/** Form for a new lot. The API validates it (ticker format, sell date after buy date). */
function AddLotDialog({ portfolioId, onClose }: { portfolioId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ ticker: "", shares: "", buyDate: "", sellDate: "" });
  const add = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/portfolios/{portfolioId}/positions", {
          params: { path: { portfolioId } },
          body: {
            ticker: form.ticker.trim().toUpperCase(),
            shares: Number(form.shares),
            buyDate: form.buyDate,
            sellDate: form.sellDate || null,
          },
        }),
      ),
    onSuccess: (lot) => {
      toast.success(`${lot.ticker} added`);
      void queryClient.invalidateQueries({ queryKey: keys.portfolios });
      onClose();
    },
    onError: (error) => toast.error(error.message),
  });
  const ready = form.ticker && Number(form.shares) > 0 && form.buyDate;

  return (
    <Dialog
      title="Add a lot"
      onClose={onClose}
      footer={
        <>
          <button className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" disabled={!ready || add.isPending} onClick={() => add.mutate()}>
            Add
          </button>
        </>
      }
    >
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <div className="field" style={{ flex: 1 }}>
          <label htmlFor="lot-ticker">Ticker</label>
          <input
            id="lot-ticker"
            className="input"
            autoFocus
            placeholder="AAPL"
            value={form.ticker}
            onChange={(e) => setForm({ ...form, ticker: e.target.value })}
          />
        </div>
        <div className="field" style={{ width: 120 }}>
          <label htmlFor="lot-shares">Shares</label>
          <input
            id="lot-shares"
            className="input"
            type="number"
            min={1}
            value={form.shares}
            onChange={(e) => setForm({ ...form, shares: e.target.value })}
          />
        </div>
      </div>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <div className="field" style={{ flex: 1 }}>
          <label htmlFor="lot-bought">Bought on</label>
          <input
            id="lot-bought"
            className="input"
            type="date"
            value={form.buyDate}
            onChange={(e) => setForm({ ...form, buyDate: e.target.value })}
          />
        </div>
        <div className="field" style={{ flex: 1 }}>
          <label htmlFor="lot-sold">Sold on</label>
          <input
            id="lot-sold"
            className="input"
            type="date"
            value={form.sellDate}
            onChange={(e) => setForm({ ...form, sellDate: e.target.value })}
          />
        </div>
      </div>
      <p className="hint">Leave "Sold on" empty if you still own the shares.</p>
    </Dialog>
  );
}

/** Shows what the report will cost, then requests it (with an Idempotency-Key) and opens it. */
function RunReportDialog({
  portfolio,
  lots,
  onClose,
}: {
  portfolio: Schemas["Portfolio"];
  lots: Schemas["Position"][];
  onClose: () => void;
}) {
  const plan = usePlan();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  // One key per confirmation: a double click or a network retry never charges twice.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const tickers = [...new Set(lots.map((l) => l.ticker))];
  const cost = tickers.length;
  const available = plan.data?.creditsAvailable ?? 0;

  const run = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/portfolios/{portfolioId}/hindsight-reports", {
          params: { path: { portfolioId: portfolio.id }, header: { "Idempotency-Key": idempotencyKey } },
          body: { positionIds: lots.map((l) => l.id) },
        }),
      ),
    onSuccess: (accepted) => {
      rememberReport({
        id: accepted.id,
        portfolioId: portfolio.id,
        portfolioName: portfolio.name,
        tickers,
        credits: accepted.creditsHeld,
        requestedAt: new Date().toISOString(),
      });
      void queryClient.invalidateQueries({ queryKey: keys.plan });
      navigate(`/reports/${accepted.id}`);
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Dialog
      title="Run a hindsight report"
      onClose={onClose}
      footer={
        <>
          <button className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn primary"
            disabled={run.isPending || cost > available}
            onClick={() => run.mutate()}
          >
            {run.isPending ? "Starting…" : `Use ${plural(cost, "credit")}`}
          </button>
        </>
      }
    >
      <p className="muted">
        We'll compare what you sold {tickers.join(", ")} for with what the same shares are worth today,
        adjusted for splits.
      </p>
      <div>
        <div className="summary-line">
          <span>Lots</span>
          <span className="num">{lots.length}</span>
        </div>
        <div className="summary-line">
          <span>Cost (1 credit per stock)</span>
          <span className="num">{plural(cost, "credit")}</span>
        </div>
        <div className="summary-line">
          <span>Credits left after</span>
          <span className="num">{plan.isSuccess ? Math.max(available - cost, 0) : "…"}</span>
        </div>
      </div>
      {plan.isSuccess && cost > available && (
        <p className="notice error">
          Your plan has {plural(available, "credit")}. Pick fewer stocks, or ask your plan owner for more
          credits.
        </p>
      )}
    </Dialog>
  );
}
