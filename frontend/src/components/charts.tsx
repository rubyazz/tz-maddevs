// History charts. Two separate plots (never a dual axis): response time as a
// single-series line; availability as per-bucket status strips. Specs follow
// the dataviz rules: 2px line with round caps, hairline solid grid, muted
// axis ink, tooltips, gaps break the line (connectNulls=false).

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { HistoryBucket } from '../api/types';
import { fmtDateTime, fmtMs } from '../lib/format';

const SERIES = '#3987e5';
const GRID = '#1e293b';
const AXIS = '#334155';
const LABEL = '#94a3b8';

export function ResponseChart({ buckets }: { buckets: HistoryBucket[] }) {
  const data = buckets.map((bucket) => ({
    ts: bucket.ts,
    ms: bucket.avg_response_ms,
  }));
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="ts"
            stroke={AXIS}
            tick={{ fill: LABEL, fontSize: 11 }}
            tickLine={false}
            tickFormatter={(value: string) =>
              new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
            }
            minTickGap={48}
          />
          <YAxis
            stroke={AXIS}
            tick={{ fill: LABEL, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={52}
            tickFormatter={(value: number) => (value >= 1000 ? `${Math.round(value / 1000)}s` : `${value}`)}
          />
          <Tooltip
            cursor={{ stroke: LABEL, strokeWidth: 1 }}
            contentStyle={{
              background: '#0f172a',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(value) => fmtDateTime(String(value))}
            formatter={(value) => [fmtMs(Number(value)), 'Response time']}
          />
          <Line
            type="monotone"
            dataKey="ms"
            stroke={SERIES}
            strokeWidth={2}
            strokeLinecap="round"
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: '#0f172a', fill: SERIES }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function bucketColor(ratio: number | null): string {
  if (ratio === null) return 'transparent'; // gap: no data (server downtime etc.)
  if (ratio >= 1) return '#0ca30c';
  if (ratio > 0) return '#ec835a';
  return '#d03b3b';
}

export function UptimeBars({ buckets }: { buckets: HistoryBucket[] }) {
  return (
    <div>
      <div className="flex h-7 w-full items-stretch gap-[2px]">
        {buckets.map((bucket) => (
          <div
            key={bucket.ts}
            title={`${fmtDateTime(bucket.ts)} — ${
              bucket.uptime_ratio === null
                ? 'no data'
                : `${(bucket.uptime_ratio * 100).toFixed(1)}% (${bucket.ok_count}/${bucket.count})`
            }`}
            className="min-w-[3px] flex-1 rounded-sm"
            style={{ backgroundColor: bucketColor(bucket.uptime_ratio) }}
          />
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-ink-muted">
        <span>{fmtDateTime(buckets[0]?.ts)}</span>
        <span>{fmtDateTime(buckets[buckets.length - 1]?.ts)}</span>
      </div>
    </div>
  );
}
