import type { ReactNode } from "react";
import {
  AlertCircle,
  CheckCircle2,
  CircleDot,
  LoaderCircle,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { number, shortDate } from "./format";
import { chartTheme } from "./theme";
import type { Group } from "./types";

export function Loading({ text = "Loading your data…" }: { text?: string }) {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <span className="loading-icon" aria-hidden="true">
        <LoaderCircle className="spin" size={22} />
      </span>
      <span className="loading-copy">
        <strong>Working on it</strong>
        <span>{text}</span>
      </span>
      <span className="loading-progress" aria-hidden="true">
        <i />
      </span>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action && <div className="page-heading-action">{action}</div>}
    </header>
  );
}

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "success" | "warning" | "danger" | "info" | "neutral";
}) {
  return (
    <span className={`status-badge ${tone}`}>
      <CircleDot size={12} aria-hidden="true" />
      {children}
    </span>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="empty-state">
      <span className="empty-state-icon" aria-hidden="true">
        {icon}
      </span>
      <h2>{title}</h2>
      <p>{description}</p>
      {action && <div className="empty-state-action">{action}</div>}
    </section>
  );
}

export function ErrorState({
  message,
  onRetry,
  onDismiss,
}: {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}) {
  return (
    <div className="error-state" role="alert">
      <AlertCircle size={20} aria-hidden="true" />
      <div>
        <strong>We couldn’t complete that request</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button className="button secondary" onClick={onRetry}>
          Try again
        </button>
      )}
      {onDismiss && (
        <button className="error-state-dismiss" onClick={onDismiss}>
          Dismiss
        </button>
      )}
    </div>
  );
}

export function Stat({
  label,
  value,
  note,
  accent = false,
}: {
  label: string;
  value: string;
  note?: string;
  accent?: boolean;
}) {
  return (
    <div className={`stat ${accent ? "accent" : ""}`}>
      <div className="stat-label">
        {label}
        {accent ? <CheckCircle2 size={15} /> : <span aria-hidden="true" />}
      </div>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  children,
  action,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h3>{title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function SalesChart({
  data,
}: {
  data: { date: string; units: number | null }[];
}) {
  return (
    <div className="chart" role="img" aria-label="Daily total sales chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 16, right: 20, left: 0, bottom: 8 }}
        >
          <defs>
            <linearGradient id="salesFill" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor={chartTheme.primary}
                stopOpacity={0.18}
              />
              <stop
                offset="100%"
                stopColor={chartTheme.primary}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 5"
            vertical={false}
            stroke={chartTheme.grid}
          />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            minTickGap={60}
            tickLine={false}
            axisLine={false}
            tick={{ fill: chartTheme.tick, fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v) => number(Number(v))}
            tickLine={false}
            axisLine={false}
            width={52}
            tick={{ fill: chartTheme.tick, fontSize: 11 }}
          />
          <Tooltip
            labelFormatter={(v) => shortDate(String(v))}
            formatter={(v) => [number(Number(v), 1), "Units sold"]}
            contentStyle={{
              borderRadius: 10,
              border: `1px solid ${chartTheme.tooltipBorder}`,
              background: chartTheme.tooltipBackground,
            }}
          />
          <Area
            isAnimationActive={false}
            dataKey="units"
            type="monotone"
            stroke={chartTheme.primary}
            strokeWidth={2}
            fill="url(#salesFill)"
            connectNulls={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
export function Bars({
  data,
  color = chartTheme.primary,
}: {
  data: Group[];
  color?: string;
}) {
  if (!data.length)
    return (
      <div className="empty-small">
        No category values are available in this dataset.
      </div>
    );
  return (
    <div
      className="chart compact"
      role="img"
      aria-label="Sales distribution chart"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 10, right: 12, left: 0, bottom: 6 }}
        >
          <CartesianGrid
            strokeDasharray="3 5"
            vertical={false}
            stroke={chartTheme.grid}
          />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tick={{ fill: chartTheme.tick, fontSize: 10 }}
            interval={0}
          />
          <YAxis
            tickFormatter={(v) => number(Number(v))}
            width={50}
            tickLine={false}
            axisLine={false}
            tick={{ fill: chartTheme.tick, fontSize: 10 }}
          />
          <Tooltip
            cursor={{ fill: chartTheme.cursor }}
            formatter={(v) => [number(Number(v), 1), "Units"]}
            contentStyle={{
              borderRadius: 10,
              border: `1px solid ${chartTheme.tooltipBorder}`,
              background: chartTheme.tooltipBackground,
            }}
          />
          <Bar
            isAnimationActive={false}
            dataKey="units"
            fill={color}
            radius={[5, 5, 0, 0]}
            maxBarSize={40}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
