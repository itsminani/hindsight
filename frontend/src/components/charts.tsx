/** Charts, built with Recharts. Only data we really have is drawn; demo prices are labelled. */
import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Schemas } from "../api/client";
import { formatDate, formatMoney } from "../lib/format";

/**
 * Colours come from the CSS tokens in styles.css, so charts follow the theme. SVG attributes
 * can't read var(--x) themselves, so we look the values up once.
 */
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();
}
/** The chart colours, read when a chart renders (after the stylesheet is loaded). */
function palette() {
  return {
    INK: token("ink"),
    BRAND: token("brand"),
    MUTED: token("chart-muted"),
    AMBER: token("pending"),
    GRID: token("rule"),
    AXIS: { fontSize: 12, fill: token("ink-3") },
  };
}
const CHIPS = ["#2f3b2a", "#3d3026", "#28323f", "#3a2a37", "#3b3520", "#233832", "#332b45"];

/** A soft colour per ticker, always the same for the same ticker. */
export function tickerColor(ticker: string): string {
  let hash = 0;
  for (const ch of ticker) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return CHIPS[hash % CHIPS.length]!;
}

/** A round chip with the ticker in it, like an app icon for the stock. */
export function TickerChip({ ticker }: { ticker: string }) {
  return (
    <span className="ticker-chip" style={{ background: tickerColor(ticker) }} aria-hidden="true">
      {ticker.replace(/[^A-Z]/g, "").slice(0, 4)}
    </span>
  );
}

const RANGES = { All: null, "10Y": 10, "5Y": 5 } as const;
type Range = keyof typeof RANGES;
const YEAR_MS = 365.25 * 24 * 3600 * 1000;

/**
 * When each lot was owned: a bar from buy date to sell date (or today, if still held).
 * Recharts trick: a stacked bar whose first, invisible part is the time before the purchase.
 */
export function HoldingTimeline({ positions }: { positions: Schemas["Position"][] }) {
  const { INK, BRAND, GRID, AXIS } = palette();
  const [range, setRange] = useState<Range>("All");
  const now = Date.now();
  const years = RANGES[range];
  const earliest = Math.min(...positions.map((p) => new Date(p.buyDate).getTime()));
  const start = years ? Math.max(earliest, now - years * YEAR_MS) : earliest;

  const rows = positions.map((p) => {
    const bought = Math.max(new Date(p.buyDate).getTime(), start);
    const ended = p.sellDate ? new Date(p.sellDate).getTime() : now;
    return {
      name: p.ticker,
      before: bought - start,
      owned: Math.max(ended - bought, 0),
      held: !p.sellDate,
      label: `Bought ${formatDate(p.buyDate)}${p.sellDate ? ` · sold ${formatDate(p.sellDate)}` : " · still held"}`,
    };
  });

  return (
    <div>
      <div className="row" style={{ justifyContent: "flex-end", marginBottom: 8 }}>
        <div className="chart-tabs" role="tablist" aria-label="Time range">
          {(Object.keys(RANGES) as Range[]).map((r) => (
            <button
              key={r}
              role="tab"
              aria-selected={range === r}
              className={range === r ? "active" : ""}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={44 + rows.length * 36}>
        <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 16 }} barSize={10}>
          <CartesianGrid horizontal={false} stroke={GRID} />
          <XAxis
            type="number"
            domain={[0, now - start]}
            tick={AXIS}
            axisLine={false}
            tickLine={false}
            tickFormatter={(ms: number) => String(new Date(start + ms).getFullYear())}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ ...AXIS, fontWeight: 600 }}
            axisLine={false}
            tickLine={false}
            width={56}
          />
          <Tooltip
            cursor={{ fill: "rgba(255,255,255,0.04)" }}
            content={({ active, payload }) =>
              active && payload?.[0] ? (
                <div className="panel panel-pad small">{(payload[0].payload as { label: string }).label}</div>
              ) : null
            }
          />
          <Bar dataKey="before" stackId="t" fill="transparent" isAnimationActive={false} />
          <Bar dataKey="owned" stackId="t" radius={5}>
            {rows.map((r) => (
              <Cell key={r.name + r.label} fill={r.held ? BRAND : INK} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="row small muted" style={{ gap: 16 }}>
        <Dot color={INK} label="Sold" />
        <Dot color={BRAND} label="Still held" />
      </div>
    </div>
  );
}

/** Small coloured dot + label, for legends. */
function Dot({ color, label }: { color: string; label: string }) {
  return (
    <span className="row" style={{ gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: 4, background: color }} />
      {label}
    </span>
  );
}

/** Credits as a donut: available (ink) and held by reports in progress (amber). */
export function CreditsDonut({ available, held }: { available: number; held: number }) {
  const { INK, AMBER, GRID } = palette();
  const data = [
    { name: "Available", value: available, color: INK },
    { name: "Held by reports in progress", value: held, color: AMBER },
  ];
  const empty = available + held === 0;
  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={empty ? [{ name: "None", value: 1, color: GRID }] : data}
          dataKey="value"
          innerRadius={62}
          outerRadius={80}
          paddingAngle={empty ? 0 : 2}
          stroke="none"
          isAnimationActive={false}
        >
          {(empty ? [{ color: GRID }] : data).map((d, i) => (
            <Cell key={i} fill={d.color} />
          ))}
        </Pie>
        {!empty && (
          <Tooltip
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: 12 }}
          />
        )}
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 13 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

/** For a finished report: what each sale brought in vs what the same shares are worth today. */
export function SoldVsTodayChart({ results }: { results: Schemas["ReportResult"][] }) {
  const { BRAND, MUTED, GRID, AXIS } = palette();
  const data = results.map((r) => ({
    name: r.ticker,
    sold: Number(r.soldFor),
    today: Number(r.worthToday),
  }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 56)}>
      <BarChart data={data} layout="vertical" margin={{ left: 0, right: 24 }} barGap={4}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis
          type="number"
          tick={AXIS}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => formatMoney(String(v)).replace(".00", "")}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ ...AXIS, fontWeight: 600 }}
          axisLine={false}
          tickLine={false}
          width={56}
        />
        <Tooltip
          formatter={(v) => formatMoney(String(v))}
          contentStyle={{ background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: 12 }}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 13 }} />
        <Bar dataKey="sold" name="Sold for" fill={MUTED} radius={4} barSize={10} />
        <Bar dataKey="today" name="Worth today" fill={BRAND} radius={4} barSize={10} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/**
 * A stock's price around and since the sale: one year before it (for context), then up to today.
 * The dot marks the day it was sold; the headline is how much the price moved since.
 */
export function PriceSinceSaleChart({
  prices,
  soldOn,
}: {
  prices: { date: string; close: string }[];
  soldOn: string;
}) {
  const { BRAND, GRID, AXIS, INK } = palette();
  const data = prices.map((p) => ({ date: p.date, close: Number(p.close) }));
  const atSale = [...data].reverse().find((p) => p.date <= soldOn) ?? data[0];
  const last = data[data.length - 1];
  if (!atSale || !last) return null;
  const change = (last.close / atSale.close - 1) * 100;

  return (
    <div>
      <div className="row" style={{ alignItems: "baseline", gap: 12 }}>
        <span className="hero-figure" style={{ fontSize: 40 }}>
          {formatMoney(String(last.close))}
        </span>
        <span className={`delta ${change >= 0 ? "up" : "down"}`}>
          {change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(1)}% since you sold
        </span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={data} margin={{ top: 24, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={BRAND} stopOpacity={0.35} />
              <stop offset="100%" stopColor={BRAND} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis
            dataKey="date"
            tick={AXIS}
            axisLine={false}
            tickLine={false}
            minTickGap={48}
            tickFormatter={(d: string) => d.slice(0, 4)}
          />
          <YAxis
            tick={AXIS}
            axisLine={false}
            tickLine={false}
            width={60}
            tickFormatter={(v: number) => `$${Math.round(v)}`}
          />
          <Tooltip
            formatter={(v) => [formatMoney(String(v)), "Close"]}
            labelFormatter={(d) => formatDate(String(d))}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: 12 }}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={BRAND}
            strokeWidth={2}
            fill="url(#priceFill)"
            dot={false}
          />
          <ReferenceLine x={atSale.date} stroke={INK} strokeDasharray="3 3" />
          <ReferenceDot
            x={atSale.date}
            y={atSale.close}
            r={5}
            fill={INK}
            stroke="none"
            label={{ value: "You sold", position: "top", fill: INK, fontSize: 12 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
