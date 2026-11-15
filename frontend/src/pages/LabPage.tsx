import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type CallRecord, onCalls, type Schemas } from "../api/client";
import { keys, usePlan, usePortfolios } from "../api/queries";
import { PageHead } from "../components/ui";

/**
 * Developer lab: shows, live, the guarantees the service makes. Not part of the product's
 * navigation; linked from the sidebar footer for demos and debugging.
 */
export function LabPage() {
  const portfolios = usePortfolios();
  const plan = usePlan();
  // Any portfolio with a sold lot works as the target: every request costs 1 credit.
  const target = (portfolios.data ?? [])
    .map((p) => ({ portfolio: p, lot: p.positions.find((x) => x.sellDate) }))
    .find((x) => x.lot);

  return (
    <>
      <PageHead
        title="Developer lab"
        subtitle="Live demonstrations of how the API behaves under pressure. Each one spends real credits."
      />
      <div className="stack">
        <RaceDemo target={target} plan={plan.data} />
        <ReplayDemo target={target} />
        <CallLog />
      </div>
    </>
  );
}

type Target = { portfolio: Schemas["Portfolio"]; lot?: Schemas["Position"] } | undefined;

/** POST one report request for the target lot with the given Idempotency-Key. */
function requestReport(target: NonNullable<Target>, key: string) {
  return api.POST("/portfolios/{portfolioId}/hindsight-reports", {
    params: { path: { portfolioId: target.portfolio.id }, header: { "Idempotency-Key": key } },
    body: { positionIds: [target.lot!.id] },
  });
}

/** Fire N requests at the same instant; only as many as there are credits may succeed (Ch7). */
function RaceDemo({ target, plan }: { target: Target; plan?: Schemas["Plan"] }) {
  const queryClient = useQueryClient();
  const [count, setCount] = useState(20);
  const [statuses, setStatuses] = useState<(number | null)[]>([]);
  const [before, setBefore] = useState<number | null>(null);
  const running = statuses.some((s) => s === null);

  /** Send `count` one-credit requests in parallel, each with its own key. */
  async function fire() {
    if (!target?.lot || !plan) return;
    setBefore(plan.creditsAvailable);
    setStatuses(Array(count).fill(null));
    await Promise.all(
      Array.from({ length: count }, async (_, i) => {
        const { response } = await requestReport(target, crypto.randomUUID());
        setStatuses((all) => all.map((s, j) => (j === i ? response.status : s)));
      }),
    );
    void queryClient.invalidateQueries({ queryKey: keys.plan });
  }

  const accepted = statuses.filter((s) => s === 202).length;
  const refused = statuses.filter((s) => s === 402).length;
  const finished = statuses.length > 0 && !running;

  return (
    <section className="panel panel-pad stack" style={{ gap: 14 }}>
      <div>
        <h2>Concurrent spending</h2>
        <p className="small muted" style={{ marginTop: 4 }}>
          Many report requests on one plan at the same instant. The plan row is locked (SELECT … FOR UPDATE),
          so exactly as many succeed as there are credits; the rest get 402 insufficient_credits.
        </p>
      </div>
      <div className="row">
        <input
          className="input"
          style={{ width: 90 }}
          type="number"
          min={2}
          max={50}
          aria-label="Number of requests"
          value={count}
          onChange={(e) => setCount(Math.max(2, Math.min(50, Number(e.target.value))))}
        />
        <button className="btn primary" disabled={running || !target?.lot || !plan} onClick={fire}>
          Send {count} at once
        </button>
        <span className="small muted">
          {target?.lot
            ? `${target.lot.ticker} in ${target.portfolio.name}`
            : "Needs a portfolio with a sold lot"}{" "}
          · plan has {plan?.creditsAvailable ?? "…"} credits
        </span>
      </div>
      {statuses.length > 0 && (
        <>
          <div
            style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(52px, 1fr))", gap: 6 }}
          >
            {statuses.map((s, i) => (
              <span
                key={i}
                className={`pill ${s === 202 ? "done" : s === null ? "pending" : "failed"}`}
                style={{ justifyContent: "center" }}
              >
                {s ?? "…"}
              </span>
            ))}
          </div>
          {finished && (
            <p className={`notice ${accepted === Math.min(before ?? 0, statuses.length) ? "ok" : "error"}`}>
              {accepted} accepted, {refused} refused with 402. The plan had {before} credits:{" "}
              {accepted === Math.min(before ?? 0, statuses.length)
                ? "no credit was spent twice."
                : "unexpected!"}
            </p>
          )}
        </>
      )}
    </section>
  );
}

/** Send the same request twice with the same Idempotency-Key: one report, charged once (Ch3). */
function ReplayDemo({ target }: { target: Target }) {
  const queryClient = useQueryClient();
  const [lines, setLines] = useState<string[]>([]);

  /** Two identical requests, one after the other, sharing a key. */
  async function run() {
    if (!target?.lot) return;
    const key = crypto.randomUUID();
    const out: string[] = [];
    for (const attempt of [1, 2]) {
      const { data, response } = await requestReport(target, key);
      const replayed = response.headers.get("Idempotent-Replayed") === "true";
      out.push(
        `Attempt ${attempt}: HTTP ${response.status}${data ? ` · report ${data.id}` : ""}${replayed ? " · replayed, not charged again" : ""}`,
      );
    }
    setLines(out);
    void queryClient.invalidateQueries({ queryKey: keys.plan });
  }

  return (
    <section className="panel panel-pad stack" style={{ gap: 14 }}>
      <div>
        <h2>Safe retries</h2>
        <p className="small muted" style={{ marginTop: 4 }}>
          A client that loses the response retries with the same Idempotency-Key. The API answers with the
          saved response: same report, credits held only once.
        </p>
      </div>
      <div>
        <button className="btn" disabled={!target?.lot} onClick={run}>
          Send twice with one key
        </button>
      </div>
      {lines.length > 0 && (
        <div className="mono stack" style={{ gap: 4 }}>
          {lines.map((l) => (
            <span key={l}>{l}</span>
          ))}
        </div>
      )}
    </section>
  );
}

/** Every API call this tab made, with the X-Request-ID that also appears in the server logs. */
function CallLog() {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  useEffect(() => onCalls(setCalls), []);
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>API calls</h2>
        <span className="small muted">Search a request ID in: docker compose logs api</span>
      </div>
      <div style={{ maxHeight: 360, overflow: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Call</th>
              <th>Status</th>
              <th className="right">ms</th>
              <th>X-Request-ID</th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.id}>
                <td className="mono" style={{ whiteSpace: "nowrap" }}>
                  {c.method} {c.path}
                </td>
                <td>
                  <span className={`pill ${c.status < 400 ? "done" : c.status < 500 ? "pending" : "failed"}`}>
                    {c.status}
                    {c.code ? ` ${c.code}` : ""}
                  </span>
                </td>
                <td className="right num">{c.ms}</td>
                <td className="mono muted" style={{ whiteSpace: "nowrap" }}>
                  {c.requestId}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
