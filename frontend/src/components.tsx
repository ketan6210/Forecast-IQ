import type { ReactNode } from "react";
import { ArrowUpRight, LoaderCircle } from "lucide-react";
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
import type { Group } from "./types";

export function Loading({ text = "Loading your data…" }: { text?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={24} />
      <span>{text}</span>
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
        <ArrowUpRight size={15} />
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
              <stop offset="0%" stopColor="#248577" stopOpacity={0.18} />
              <stop offset="100%" stopColor="#248577" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 5"
            vertical={false}
            stroke="#e8edeb"
          />
          <XAxis
            dataKey="date"
            tickFormatter={shortDate}
            minTickGap={60}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#768583", fontSize: 11 }}
          />
          <YAxis
            tickFormatter={(v) => number(Number(v))}
            tickLine={false}
            axisLine={false}
            width={52}
            tick={{ fill: "#768583", fontSize: 11 }}
          />
          <Tooltip
            labelFormatter={(v) => shortDate(String(v))}
            formatter={(v) => [number(Number(v), 1), "Units sold"]}
            contentStyle={{ borderRadius: 10, border: "1px solid #e2e8e5" }}
          />
          <Area
            isAnimationActive={false}
            dataKey="units"
            type="monotone"
            stroke="#218473"
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
  color = "#378f81",
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
            stroke="#e8edeb"
          />
          <XAxis
            dataKey="name"
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#768583", fontSize: 10 }}
            interval={0}
          />
          <YAxis
            tickFormatter={(v) => number(Number(v))}
            width={50}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#768583", fontSize: 10 }}
          />
          <Tooltip
            cursor={{ fill: "#f0f5f2" }}
            formatter={(v) => [number(Number(v), 1), "Units"]}
            contentStyle={{ borderRadius: 10, border: "1px solid #e2e8e5" }}
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
