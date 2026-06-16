"use client";

import { useState, useEffect } from "react";

const card: React.CSSProperties = {
  background: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: 16,
};

const cardHeader: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: 14,
};

type TimeRange = "7d" | "30d" | "all";

interface DailyPoint  { date: string; scraped: number; sent: number }
interface Category    { label: string; count: number; sent: number; color: string }
interface Location    { city: string; count: number }
interface ScoreDist   { range: string; count: number; color: string }
interface Insight     { emoji: string; title: string; desc: string }

interface AnalyticsData {
  summary: {
    total_scraped: number; total_sent: number;
    total_skipped: number; pending: number; matched: number;
    avg_score: number;
  };
  daily:      DailyPoint[];
  categories: Category[];
  locations:  Location[];
  score_dist: ScoreDist[];
  insights:   Insight[];
}

const EMPTY: AnalyticsData = {
  summary: { total_scraped:0, total_sent:0, total_skipped:0, pending:0, matched:0, avg_score:0 },
  daily: [], categories: [], locations: [], score_dist: [], insights: [],
};

export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");
  const [data, setData]           = useState<AnalyticsData>(EMPTY);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/analytics?range=${timeRange}`)
      .then((r) => r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`))
      .then((d) => { if (d) setData(d); })
      .catch((e) => console.error("[analytics]", e))
      .finally(() => setLoading(false));
  }, [timeRange]);

  // ── Line chart helpers ─────────────────────────────────────────
  const daily     = data.daily;
  const svgW      = 560;
  const svgH      = 160;
  const padX      = 8;
  const padY      = 8;
  const plotW     = svgW - padX * 2;
  const plotH     = svgH - padY * 2;
  const n         = Math.max(daily.length, 1);
  const maxVal    = Math.max(...daily.map((d) => Math.max(d.scraped, d.sent)), 1);

  const xPos = (i: number) =>
    n === 1 ? svgW / 2 : padX + (i / (n - 1)) * plotW;
  const yPos = (v: number) =>
    padY + plotH - (v / maxVal) * plotH;

  const linePath = (key: "scraped" | "sent") =>
    daily.length === 0
      ? ""
      : daily
          .map((d, i) => `${i === 0 ? "M" : "L"}${xPos(i).toFixed(1)},${yPos(d[key]).toFixed(1)}`)
          .join(" ");

  const areaPath = (key: "scraped" | "sent") =>
    daily.length === 0
      ? ""
      : `${linePath(key)} L${xPos(n - 1).toFixed(1)},${(padY + plotH).toFixed(1)} L${padX},${(padY + plotH).toFixed(1)} Z`;

  // ── Category bar chart max ─────────────────────────────────────
  const catMax = Math.max(...data.categories.map((c) => c.count), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* Topbar */}
      <header
        style={{
          height: "var(--topbar-h)",
          borderBottom: "1px solid var(--border)",
          background: "var(--card)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          position: "sticky",
          top: 0,
          zIndex: 40,
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: 15 }}>
          效果分析
          {loading && (
            <span style={{ fontSize: 11, color: "var(--muted)", marginLeft: 8, fontWeight: 400 }}>
              加载中…
            </span>
          )}
        </span>
        {/* Time toggle */}
        <div
          style={{
            display: "flex",
            gap: 2,
            background: "var(--card2)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: 3,
          }}
        >
          {(["7d", "30d", "all"] as TimeRange[]).map((r) => (
            <button
              key={r}
              onClick={() => setTimeRange(r)}
              style={{
                background: timeRange === r ? "var(--green-dim)" : "transparent",
                color: timeRange === r ? "var(--green)" : "var(--muted)",
                border: timeRange === r ? "1px solid var(--green-border)" : "1px solid transparent",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: timeRange === r ? 600 : 500,
                padding: "4px 12px",
                cursor: "pointer",
              }}
            >
              {r === "7d" ? "7天" : r === "30d" ? "30天" : "全部"}
            </button>
          ))}
        </div>
      </header>

      {/* Content */}
      <div
        style={{
          padding: "20px",
          overflowY: "auto",
          height: "calc(100vh - var(--topbar-h))",
          display: "flex",
          flexDirection: "column",
          gap: 16,
        }}
      >
        {/* ── KPIs ────────────────────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12 }}>
          {[
            { icon: "📥", label: "抓取岗位",   value: data.summary.total_scraped,                                               color: "var(--fg)" },
            { icon: "📤", label: "已投递",     value: data.summary.total_sent,                                                  color: "var(--blue)" },
            { icon: "⏳", label: "待处理",     value: data.summary.pending,                                                     color: "var(--amber)" },
            { icon: "✅", label: "已匹配",     value: data.summary.matched,                                                     color: "var(--green)" },
            { icon: "⏭",  label: "已跳过",     value: data.summary.total_skipped,                                               color: "var(--muted)" },
            { icon: "🎯", label: "平均匹配分", value: data.summary.avg_score > 0 ? `${data.summary.avg_score}` : "—",           color: "var(--blue)" },
          ].map(({ icon, label, value, color }) => (
            <div key={label} style={{ ...card, padding: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 18 }}>{icon}</span>
                <span style={{ fontSize: 22, fontWeight: 800, color, lineHeight: 1 }}>{loading ? "—" : value}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500 }}>{label}</div>
            </div>
          ))}
        </div>

        {/* ── Line chart ──────────────────────────────────────── */}
        <div style={card}>
          <div style={cardHeader}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>每日抓取量 & 投递趋势</span>
            <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--muted)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ display: "inline-block", width: 20, height: 2, background: "var(--green)", borderRadius: 1 }} />
                抓取量
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ display: "inline-block", width: 20, height: 2, background: "var(--blue)", borderRadius: 1 }} />
                投递数
              </span>
            </div>
          </div>
          <div style={{ width: "100%", overflowX: "auto" }}>
            {daily.length === 0 ? (
              <div style={{ textAlign: "center", color: "var(--muted2)", fontSize: 13, padding: "40px 0" }}>
                暂无数据
              </div>
            ) : (
              <svg
                viewBox={`0 0 ${svgW} ${svgH}`}
                style={{ width: "100%", height: svgH, display: "block" }}
                preserveAspectRatio="none"
              >
                <defs>
                  <linearGradient id="gradGreen" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--green)" stopOpacity="0.3" />
                    <stop offset="100%" stopColor="var(--green)" stopOpacity="0" />
                  </linearGradient>
                  <linearGradient id="gradBlue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--blue)" stopOpacity="0.2" />
                    <stop offset="100%" stopColor="var(--blue)" stopOpacity="0" />
                  </linearGradient>
                </defs>
                {[0.25, 0.5, 0.75, 1].map((f) => (
                  <line
                    key={f}
                    x1={padX} y1={padY + plotH * (1 - f)}
                    x2={svgW - padX} y2={padY + plotH * (1 - f)}
                    stroke="var(--border)" strokeWidth="1"
                  />
                ))}
                <path d={areaPath("scraped")} fill="url(#gradGreen)" />
                <path d={areaPath("sent")}    fill="url(#gradBlue)" />
                <path d={linePath("scraped")} fill="none" stroke="var(--green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d={linePath("sent")}    fill="none" stroke="var(--blue)"  strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                {daily.map((d, i) => (
                  <circle key={`s${i}`} cx={xPos(i)} cy={yPos(d.scraped)} r="3" fill="var(--green)" />
                ))}
                {daily.map((d, i) => (
                  <circle key={`a${i}`} cx={xPos(i)} cy={yPos(d.sent)}    r="3" fill="var(--blue)" />
                ))}
              </svg>
            )}
          </div>
        </div>

        {/* ── 2-col: category + insights ──────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {/* Category bar chart */}
          <div style={card}>
            <div style={cardHeader}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>岗位类别分布</span>
            </div>
            {data.categories.length === 0 ? (
              <div style={{ textAlign: "center", color: "var(--muted2)", fontSize: 13, padding: "20px 0" }}>暂无数据</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {data.categories.map(({ label, count, color }) => (
                  <div key={label}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                      <span style={{ fontSize: 12, color: "var(--fg)" }}>{label}</span>
                      <span style={{ fontSize: 12, color, fontWeight: 700 }}>{count} 条</span>
                    </div>
                    <div style={{ height: 6, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
                      <div
                        style={{
                          width: `${Math.round((count / catMax) * 100)}%`,
                          height: "100%",
                          background: color,
                          borderRadius: 3,
                          transition: "width 0.8s ease",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Insights */}
          <div style={card}>
            <div style={cardHeader}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>智能洞察</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {data.insights.map(({ emoji, title, desc }) => (
                <div
                  key={title}
                  style={{
                    background: "var(--card2)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "10px 12px",
                    display: "flex",
                    gap: 10,
                  }}
                >
                  <span style={{ fontSize: 18, flexShrink: 0 }}>{emoji}</span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 3 }}>{title}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Score distribution ──────────────────────────────── */}
        <div style={card}>
          <div style={cardHeader}>
            <span style={{ fontWeight: 700, fontSize: 13 }}>AI 匹配分布</span>
          </div>
          {data.score_dist.every((s) => s.count === 0) ? (
            <div style={{ textAlign: "center", color: "var(--muted2)", fontSize: 13, padding: "20px 0" }}>暂无数据</div>
          ) : (
            <div style={{ display: "flex", gap: 12, alignItems: "flex-end", height: 80 }}>
              {data.score_dist.map(({ range, count, color }) => {
                const maxCount = Math.max(...data.score_dist.map((s) => s.count), 1);
                const pct = Math.round((count / maxCount) * 100);
                return (
                  <div key={range} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color }}>{count}</span>
                    <div
                      style={{
                        width: "100%",
                        height: `${Math.max(pct * 0.56, 4)}px`,
                        background: color,
                        borderRadius: "4px 4px 0 0",
                        opacity: 0.85,
                        transition: "height 0.6s ease",
                      }}
                    />
                    <span style={{ fontSize: 10, color: "var(--muted)", textAlign: "center", lineHeight: 1.3 }}>{range}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Location distribution ───────────────────────────── */}
        {data.locations.length > 0 && (
          <div style={card}>
            <div style={cardHeader}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>城市分布</span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {data.locations.map(({ city, count }) => (
                <div
                  key={city}
                  style={{
                    background: "var(--card2)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "6px 14px",
                    fontSize: 12,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span style={{ color: "var(--fg)", fontWeight: 600 }}>{city}</span>
                  <span style={{ color: "var(--muted)" }}>{count} 条</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
