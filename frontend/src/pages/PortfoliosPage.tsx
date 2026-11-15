import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { api } from "../api/client";
import { keys, unwrap, usePortfolios } from "../api/queries";
import { TickerChip } from "../components/charts";
import { Dialog, PageHead } from "../components/ui";
import { plural } from "../lib/format";

/** All of the user's portfolios as cards, and a way to create one. */
export function PortfoliosPage() {
  const portfolios = usePortfolios();
  const [creating, setCreating] = useState(false);
  const list = portfolios.data ?? [];
  const soldLots = list.flatMap((p) => p.positions).filter((p) => p.sellDate).length;

  return (
    <>
      <PageHead
        title="Portfolios"
        subtitle={`${plural(list.length, "portfolio")} · ${plural(soldLots, "sold lot")} you can look back on`}
        actions={
          <button className="btn primary" onClick={() => setCreating(true)}>
            New portfolio
          </button>
        }
      />

      {portfolios.isLoading && <p className="muted">Loading…</p>}
      {portfolios.isError && <p className="error-text">{portfolios.error.message}</p>}
      {portfolios.isSuccess && list.length === 0 && (
        <div className="panel empty">
          <h3>No portfolios yet</h3>
          <p>Create one, then add the stocks you bought and sold.</p>
        </div>
      )}

      <div className="grid grid-3">
        {list.map((p) => {
          const tickers = [...new Set(p.positions.map((x) => x.ticker))];
          const sold = p.positions.filter((x) => x.sellDate).length;
          return (
            <Link
              key={p.id}
              to={`/portfolios/${p.id}`}
              className="panel panel-pad"
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <h3>{p.name}</h3>
              <p className="small muted" style={{ marginTop: 2 }}>
                {plural(p.positions.length, "lot")} · {sold} sold
              </p>
              <div className="row" style={{ marginTop: 18, gap: 6 }}>
                {tickers.slice(0, 5).map((t) => (
                  <TickerChip key={t} ticker={t} />
                ))}
                {tickers.length > 5 && <span className="small muted">+{tickers.length - 5}</span>}
              </div>
            </Link>
          );
        })}
      </div>

      {creating && <NewPortfolioDialog onClose={() => setCreating(false)} />}
    </>
  );
}

/** Asks for a name, creates the portfolio, then opens it. */
function NewPortfolioDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: async () => unwrap(await api.POST("/portfolios", { body: { name: name.trim() } })),
    onSuccess: (portfolio) => {
      void queryClient.invalidateQueries({ queryKey: keys.portfolios });
      navigate(`/portfolios/${portfolio.id}`);
    },
    onError: (error) => toast.error(error.message),
  });

  /** Submit on Enter as well as on the button. */
  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <Dialog
      title="New portfolio"
      onClose={onClose}
      footer={
        <>
          <button className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn primary"
            disabled={!name.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Create
          </button>
        </>
      }
    >
      <form className="field" onSubmit={submit}>
        <label htmlFor="portfolio-name">Name</label>
        <input
          id="portfolio-name"
          className="input"
          autoFocus
          maxLength={100}
          placeholder="e.g. Retirement, Tech picks"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </form>
    </Dialog>
  );
}
