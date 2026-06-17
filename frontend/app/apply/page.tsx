"use client";

import { useEffect, useState } from "react";
import { getApplications, getTodayStats, Application } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { RefreshCwIcon } from "lucide-react";

const APP_STATUS_STYLE: Record<string, { bg: string; color: string }> = {
  approved: { bg: "rgba(59,130,246,0.10)",  color: "#3B82F6" },
  sent:     { bg: "rgba(16,185,129,0.10)",  color: "#10B981" },
  failed:   { bg: "rgba(244,63,94,0.10)",   color: "#F43F5E" },
};

const APP_STATUS_LABEL: Record<string, string> = {
  approved: "待发送",
  sent: "已发送",
  failed: "发送失败",
};

export default function ApplyPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [todayStats, setTodayStats] = useState({ today_sent: 0, daily_limit: 30, remaining: 30 });

  const fetchData = async () => {
    setLoading(true);
    try {
      const [appRes, stats] = await Promise.all([
        getApplications(statusFilter || undefined),
        getTodayStats(),
      ]);
      setApps(appRes.items);
      setTodayStats(stats);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const statusFilters = [
    { value: "", label: "全部" },
    { value: "sent", label: "已发送" },
    { value: "failed", label: "失败" },
  ];

  const statCards = [
    { value: todayStats.today_sent, unit: "份", label: "今日已投递",  bg: "rgba(59,130,246,0.08)",  numColor: "#3B82F6", subColor: "#60A5FA" },
    { value: apps.length,           unit: "条", label: "总投递记录",  bg: "rgba(152,152,184,0.08)", numColor: "#5B5B7A", subColor: "#9898B8" },
  ];

  return (
    <div className="space-y-4">
      {/* ── 顶部统计 ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statCards.map((c) => (
          <div key={c.label} className="rounded-xl p-4" style={{ background: c.bg, border: `2px solid ${c.bg}` }}>
            <div className="text-2xl font-bold" style={{ color: c.numColor }}>
              {c.value}
              <span className="text-sm font-normal ml-1">{c.unit}</span>
            </div>
            <div className="text-sm mt-0.5" style={{ color: c.subColor }}>{c.label}</div>
          </div>
        ))}
      </div>

      {/* 单日配额进度条 */}
      <div className="bg-white rounded-xl p-4" style={{ border: "3px solid rgba(255,255,255,0.92)", boxShadow: "8px 8px 22px rgba(139,92,246,0.09), -2px -2px 7px rgba(255,255,255,0.88)" }}>
        <div className="flex justify-between text-sm mb-2" style={{ color: "var(--muted)" }}>
          <span>今日投递进度</span>
          <span>
            {todayStats.today_sent} / {todayStats.daily_limit}
          </span>
        </div>
        <div className="w-full rounded-full h-2" style={{ background: "rgba(139,92,246,0.08)" }}>
          <div
            className="h-2 rounded-full transition-all"
            style={{
              width: `${Math.min(100, (todayStats.today_sent / todayStats.daily_limit) * 100)}%`,
              background: "linear-gradient(90deg, #A78BFA, #8B5CF6)",
              boxShadow: "0 0 6px rgba(139,92,246,0.35)",
            }}
          />
        </div>
      </div>

      {/* ── 筛选 + 刷新 ─────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {statusFilters.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className="px-3 py-1.5 text-sm rounded-xl border-2 font-bold transition-none"
              style={statusFilter === f.value
                ? { background: "#8B5CF6", color: "#fff", borderColor: "rgba(255,255,255,0.40)", boxShadow: "0 4px 0 #6D28D9, 0 6px 12px rgba(139,92,246,0.28)", transform: "translateY(-1px)" }
                : { background: "transparent", color: "var(--muted)", borderColor: "rgba(139,92,246,0.18)" }
              }
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg"
          style={{ color: "var(--muted)", border: "1px solid rgba(139,92,246,0.20)", background: "rgba(255,255,255,0.85)" }}
        >
          <RefreshCwIcon className="w-4 h-4" /> 刷新状态
        </button>
      </div>

      {/* ── 投递记录表格 ────────────────────────────────────── */}
      {loading ? (
        <div className="text-center py-12" style={{ color: "var(--muted2)" }}>加载中…</div>
      ) : (
        <div className="bg-white rounded-xl overflow-hidden" style={{ border: "3px solid rgba(255,255,255,0.92)", boxShadow: "8px 8px 22px rgba(139,92,246,0.09), -2px -2px 7px rgba(255,255,255,0.88)" }}>
          <table className="w-full text-sm">
            <thead style={{ background: "rgba(139,92,246,0.04)", borderBottom: "2px solid rgba(139,92,246,0.08)" }}>
              <tr>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>岗位</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>公司</th>
                <th className="text-center px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>状态</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>投递时间</th>
                <th className="text-left px-4 py-3 font-medium" style={{ color: "var(--muted)" }}>打招呼语</th>
              </tr>
            </thead>
            <tbody className="divide-y" style={{ borderColor: "rgba(139,92,246,0.06)" }}>
              {apps.map((app) => (
                <tr key={app.id} style={{ transition: "background 0.15s" }}
                  onMouseEnter={(e) => ((e.currentTarget as HTMLTableRowElement).style.background = "rgba(139,92,246,0.03)")}
                  onMouseLeave={(e) => ((e.currentTarget as HTMLTableRowElement).style.background = "")}
                >
                  <td className="px-4 py-3 font-medium" style={{ color: "var(--fg)" }}>{app.job_title}</td>
                  <td className="px-4 py-3" style={{ color: "var(--muted)" }}>{app.company}</td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className="text-xs px-2 py-0.5 rounded-full font-medium"
                      style={{ background: (APP_STATUS_STYLE[app.status] ?? APP_STATUS_STYLE.approved).bg, color: (APP_STATUS_STYLE[app.status] ?? APP_STATUS_STYLE.approved).color }}
                    >
                      {APP_STATUS_LABEL[app.status] || app.status}
                    </span>
                    {app.error_message && (
                      <div className="text-xs mt-0.5" style={{ color: "#F43F5E" }}>{app.error_message}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--muted2)" }}>
                    {formatDate(app.sent_at)}
                  </td>
                  <td className="px-4 py-3 max-w-xs" style={{ color: "var(--muted)" }}>
                    <p className="line-clamp-2 text-xs">{app.greeting_message}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {apps.length === 0 && (
            <div className="text-center py-12" style={{ color: "var(--muted2)" }}>暂无投递记录</div>
          )}
        </div>
      )}
    </div>
  );
}
