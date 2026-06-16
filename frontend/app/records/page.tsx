"use client";

import { useEffect, useState } from "react";
import { getJobs, approveJob, skipJob, Job } from "@/lib/api";

const card: React.CSSProperties = {
  background: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  overflow: "hidden",
};

type FilterTab = "" | "pending_send" | "sent" | "matched" | "approved";

const TABS: { value: FilterTab; label: string }[] = [
  { value: "",             label: "全部"   },
  { value: "pending_send", label: "待发送" },
  { value: "sent",         label: "已发送" },
  { value: "matched",      label: "待审批" },
  { value: "approved",     label: "已批准" },
];

function Badge({ status }: { status: string }) {
  const map: Record<string, { label: string; bg: string; color: string }> = {
    pending_send: { label: "⏱ 待发送", bg: "var(--amber-dim)", color: "var(--amber)" },
    sent:         { label: "● 已发送", bg: "var(--green-dim)", color: "var(--green)" },
    matched:      { label: "◎ 待审批", bg: "var(--blue-dim)",  color: "var(--blue)"  },
    approved:     { label: "✓ 已批准", bg: "var(--green-dim)", color: "var(--green)" },
    skipped:      { label: "— 已跳过", bg: "rgba(148,163,184,.08)", color: "var(--muted2)" },
    failed:       { label: "✗ 失败",   bg: "var(--red-dim)",   color: "var(--red)"   },
  };
  const s = map[status] || { label: status, bg: "rgba(148,163,184,.08)", color: "var(--muted)" };
  return (
    <span
      style={{
        background: s.bg,
        color: s.color,
        borderRadius: 6,
        fontSize: 11,
        fontWeight: 600,
        padding: "3px 8px",
        whiteSpace: "nowrap",
      }}
    >
      {s.label}
    </span>
  );
}

function cleanSalary(s: string): string {
  // Strip Private Use Area characters (icon-font glyphs that render as boxes)
  // eslint-disable-next-line no-control-regex
  return s.replace(/[-]/g, "").replace(/\s+/g, " ").trim();
}

function formatDate(s: string) {
  try {
    const d = new Date(s);
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return s; }
}

export default function RecordsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<FilterTab>("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const res = await getJobs({ limit: 50, status: tab || undefined });
      setJobs(res.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchJobs(); }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const counts: Record<string, number> = {};
  jobs.forEach((j) => { counts[j.status] = (counts[j.status] || 0) + 1; });
  const totalCount = jobs.length;

  const handleApprove = async (id: number) => { await approveJob(id); fetchJobs(); };
  const handleSkip    = async (id: number) => { await skipJob(id);    fetchJobs(); };

  const exportCSV = () => {
    const rows = [
      ["ID", "公司", "岗位", "薪资", "状态", "投递时间"],
      ...jobs.map((j) => [j.id, j.company, j.title, cleanSalary(j.salary || ""), j.status, j.scraped_at]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "投递记录.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

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
        <span style={{ fontWeight: 700, fontSize: 15 }}>投递记录</span>
        <button
          onClick={exportCSV}
          style={{
            background: "transparent",
            border: "1px solid var(--border2)",
            color: "var(--muted)",
            fontSize: 12,
            fontWeight: 500,
            cursor: "pointer",
            padding: "5px 14px",
            borderRadius: "var(--radius-sm)",
          }}
        >
          ↓ 导出 CSV
        </button>
      </header>

      {/* Content */}
      <div style={{ padding: "20px", overflowY: "auto", height: "calc(100vh - var(--topbar-h))" }}>
        {/* Filter tabs */}
        <div
          style={{
            display: "flex",
            gap: 4,
            marginBottom: 16,
            background: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: 4,
            width: "fit-content",
          }}
        >
          {TABS.map(({ value, label }) => {
            const active = tab === value;
            const cnt = value === "" ? totalCount : (counts[value] || 0);
            return (
              <button
                key={value}
                onClick={() => setTab(value)}
                style={{
                  background: active ? "var(--green-dim)" : "transparent",
                  color: active ? "var(--green)" : "var(--muted)",
                  border: active ? "1px solid var(--green-border)" : "1px solid transparent",
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: active ? 600 : 500,
                  padding: "5px 14px",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                {label}
                {cnt > 0 && (
                  <span
                    style={{
                      background: active ? "var(--green)" : "var(--border2)",
                      color: active ? "#000" : "var(--muted)",
                      borderRadius: 10,
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "1px 6px",
                    }}
                  >
                    {cnt}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Table */}
        <div style={card}>
          {loading ? (
            <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--muted2)", fontSize: 13 }}>
              加载中…
            </div>
          ) : jobs.length === 0 ? (
            <div style={{ padding: "60px 20px", textAlign: "center", color: "var(--muted2)", fontSize: 13 }}>
              暂无记录
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--card2)" }}>
                  {["公司", "岗位", "薪资", "投递时间", "状态", "操作"].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "10px 16px",
                        textAlign: "left",
                        fontWeight: 600,
                        fontSize: 12,
                        color: "var(--muted)",
                        borderBottom: "1px solid var(--border)",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const expanded = expandedId === job.id;
                  return (
                    <>
                      <tr
                        key={job.id}
                        onClick={() => setExpandedId(expanded ? null : job.id)}
                        style={{
                          borderBottom: "1px solid var(--border)",
                          cursor: "pointer",
                          transition: "background 0.1s",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,.02)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        <td style={{ padding: "12px 16px", fontWeight: 600 }}>{job.company}</td>
                        <td style={{ padding: "12px 16px", color: "var(--muted)" }}>
                          {job.title}
                        </td>
                        <td style={{ padding: "12px 16px", fontWeight: 600, fontSize: 13, color: "var(--fg)", whiteSpace: "nowrap" }}>
                          {cleanSalary(job.salary || "") || <span style={{ color: "var(--muted2)", fontWeight: 400, fontSize: 12 }}>—</span>}
                        </td>
                        <td style={{ padding: "12px 16px", color: "var(--muted2)", fontSize: 12 }}>
                          {formatDate(job.scraped_at)}
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <Badge status={job.status} />
                        </td>
                        <td
                          style={{ padding: "12px 16px" }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                            <span style={{ fontSize: 12, color: "var(--muted2)" }}>
                              {expanded ? "▲" : "▼"}
                            </span>
                            {(job.status === "matched" || job.status === "approved") && (
                              <button
                                onClick={() => handleApprove(job.id)}
                                style={{
                                  background: "var(--green-dim)",
                                  border: "1px solid var(--green-border)",
                                  color: "var(--green)",
                                  borderRadius: 6,
                                  fontSize: 11,
                                  fontWeight: 600,
                                  padding: "3px 10px",
                                  cursor: "pointer",
                                }}
                              >
                                批准
                              </button>
                            )}
                            {job.status === "pending_send" && (
                              <button
                                onClick={() => handleSkip(job.id)}
                                style={{
                                  background: "transparent",
                                  border: "1px solid var(--border2)",
                                  color: "var(--muted2)",
                                  borderRadius: 6,
                                  fontSize: 11,
                                  padding: "3px 10px",
                                  cursor: "pointer",
                                }}
                              >
                                取消
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>

                      {/* Expanded row */}
                      {expanded && (
                        <tr key={`${job.id}-expand`} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td colSpan={6} style={{ padding: "16px 20px", background: "var(--card2)" }}>
                            {job.greeting_message ? (
                              <div>
                                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 8 }}>
                                  打招呼草稿
                                </div>
                                <p
                                  style={{
                                    fontSize: 13,
                                    color: "var(--fg)",
                                    lineHeight: 1.6,
                                    background: "var(--card)",
                                    border: "1px solid var(--border)",
                                    borderRadius: "var(--radius-sm)",
                                    padding: "10px 14px",
                                    marginBottom: 12,
                                  }}
                                >
                                  {job.greeting_message}
                                </p>
                              </div>
                            ) : (
                              <p style={{ fontSize: 12, color: "var(--muted2)", marginBottom: 12 }}>暂无打招呼草稿</p>
                            )}
                            <button
                              style={{
                                background: "var(--blue-dim)",
                                border: "1px solid rgba(59,130,246,.25)",
                                color: "var(--blue)",
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: 600,
                                padding: "6px 14px",
                                cursor: "pointer",
                              }}
                            >
                              ✦ 生成适配建议
                            </button>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
