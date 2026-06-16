"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useCallback } from "react";
import {
  LayoutDashboard,
  Briefcase,
  FileText,
  BarChart2,
  Settings,
  User,
  Bot,
  Zap,
} from "lucide-react";

const NAV = [
  { href: "/",          Icon: LayoutDashboard, label: "控制台"      },
  { href: "/jobs",      Icon: Briefcase,        label: "岗位列表"    },
  { href: "/records",   Icon: FileText,         label: "投递记录"    },
  { href: "/analytics", Icon: BarChart2,         label: "效果分析"    },
  { href: "/settings",  Icon: Settings,          label: "策略配置"    },
  { href: "/profile",   Icon: User,              label: "个人档案"    },
  { href: "/chat",      Icon: Bot,               label: "Agent 控制台" },
];

export default function Sidebar() {
  const path = usePathname();
  const [hovered, setHovered] = useState<string | null>(null);

  const [todayCount,  setTodayCount]  = useState(0);
  const [dailyLimit,  setDailyLimit]  = useState(30);
  const [agentRunning, setAgentRunning] = useState(false);
  const [applyRunning, setApplyRunning] = useState(false);
  const [applyDone,    setApplyDone]    = useState(0);
  const [applyTotal,   setApplyTotal]   = useState(0);

  const poll = useCallback(async () => {
    try {
      const [statsRes, applyRes, scrapeRes] = await Promise.all([
        fetch("/api/apply/today").then(r => r.ok ? r.json() : null),
        fetch("/api/apply/task-status").then(r => r.ok ? r.json() : null),
        fetch("/api/jobs/scrape/status").then(r => r.ok ? r.json() : null),
      ]);
      if (statsRes) {
        setTodayCount(statsRes.today_sent ?? 0);
        setDailyLimit(statsRes.daily_limit ?? 30);
      }
      if (applyRes) {
        setApplyRunning(applyRes.running ?? false);
        setApplyDone((applyRes.success_count ?? 0) + (applyRes.fail_count ?? 0));
        setApplyTotal(applyRes.total_jobs ?? 0);
      }
      if (scrapeRes) {
        setAgentRunning((applyRes?.running ?? false) || (scrapeRes.running ?? false));
      }
    } catch {
      // network error — keep last known state
    }
  }, []);

  // initial fetch
  useEffect(() => { poll(); }, [poll]);

  // fast poll when running, slow when idle
  useEffect(() => {
    const interval = agentRunning ? 3000 : 15000;
    const id = setInterval(poll, interval);
    return () => clearInterval(id);
  }, [agentRunning, poll]);

  // progress bar math (same logic as console page)
  const determinate   = applyRunning && applyTotal > 0;
  const indeterminate = agentRunning && !determinate;
  const barPct = determinate
    ? Math.min(99, Math.round((applyDone / applyTotal) * 100))
    : Math.round((todayCount / Math.max(dailyLimit, 1)) * 100);

  return (
    <aside
      style={{
        position: "fixed",
        inset: "0 auto 0 0",
        width: "var(--sidebar-w)",
        background: "rgba(255, 255, 255, 0.55)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        borderRight: "1px solid rgba(255, 255, 255, 0.65)",
        boxShadow: "4px 0 32px rgba(139,92,246,0.08)",
        display: "flex",
        flexDirection: "column",
        zIndex: 50,
      }}
    >
      {/* ── Logo ── */}
      <div style={{ padding: "16px 12px 12px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: "rgba(255,255,255,0.80)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
            borderRadius: 18,
            border: "1px solid rgba(255,255,255,0.85)",
            boxShadow: "0 4px 16px rgba(139,92,246,0.10), inset 0 1px 0 rgba(255,255,255,0.95)",
            padding: "10px 12px",
          }}
        >
          <div
            style={{
              width: 36,
              height: 36,
              background: "linear-gradient(135deg, #A78BFA, #8B5CF6)",
              borderRadius: 12,
              border: "1px solid rgba(255,255,255,0.55)",
              boxShadow: "0 4px 12px rgba(139,92,246,0.35)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Zap size={16} color="white" strokeWidth={2.5} />
          </div>
          <div>
            <div
              style={{
                fontFamily: "var(--font-fredoka), 'Fredoka', sans-serif",
                fontWeight: 600,
                fontSize: 16,
                color: "#1A1A2E",
                lineHeight: 1.2,
              }}
            >
              求职助手
            </div>
            <div style={{ fontSize: 10, color: "#9898B8", marginTop: 1 }}>
              Job Hunt Agent
            </div>
          </div>
        </div>
      </div>

      {/* ── Nav ── */}
      <nav style={{ flex: 1, padding: "4px 10px", overflowY: "auto" }}>
        {NAV.map(({ href, Icon, label }) => {
          const active = path === href;
          const isHovered = hovered === href && !active;
          return (
            <Link
              key={href}
              href={href}
              onMouseEnter={() => setHovered(href)}
              onMouseLeave={() => setHovered(null)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "9px 12px",
                borderRadius: 13,
                marginBottom: 2,
                fontSize: 13,
                fontWeight: active ? 700 : 500,
                color: active ? "#7C3AED" : isHovered ? "#8B5CF6" : "#5B5B7A",
                background: active
                  ? "rgba(139,92,246,0.12)"
                  : isHovered
                  ? "rgba(255,255,255,0.55)"
                  : "transparent",
                backdropFilter: active || isHovered ? "blur(10px)" : "none",
                WebkitBackdropFilter: active || isHovered ? "blur(10px)" : "none",
                boxShadow: active
                  ? "inset 0 1px 0 rgba(255,255,255,0.60), 0 2px 10px rgba(139,92,246,0.12)"
                  : isHovered
                  ? "inset 0 1px 0 rgba(255,255,255,0.70)"
                  : "none",
                border: active
                  ? "1px solid rgba(139,92,246,0.28)"
                  : isHovered
                  ? "1px solid rgba(255,255,255,0.60)"
                  : "1px solid transparent",
                textDecoration: "none",
                transition: "all 0.15s ease",
              }}
            >
              <Icon
                size={14}
                strokeWidth={active ? 2.5 : 2}
                color={active ? "#8B5CF6" : isHovered ? "#A78BFA" : "#9898B8"}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* ── Status footer ── */}
      <div style={{ padding: "8px 10px 14px" }}>
        <div
          style={{
            background: "rgba(255,255,255,0.72)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
            border: "1px solid rgba(255,255,255,0.80)",
            borderRadius: 16,
            boxShadow: "0 4px 16px rgba(139,92,246,0.07), inset 0 1px 0 rgba(255,255,255,0.90)",
            padding: "10px 12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: agentRunning ? "#3B82F6" : "#10B981",
                boxShadow: agentRunning
                  ? "0 0 6px rgba(59,130,246,0.65)"
                  : "0 0 6px rgba(16,185,129,0.65)",
                flexShrink: 0,
              }}
            />
            <span style={{ fontSize: 12, fontWeight: 700, color: "#1A1A2E" }}>
              {agentRunning ? (determinate ? `投递中 ${barPct}%` : "运行中…") : "Agent 就绪"}
            </span>
          </div>
          <div
            style={{
              height: 5,
              background: "rgba(139,92,246,0.08)",
              borderRadius: 3,
              overflow: "hidden",
            }}
          >
            <div
              className={indeterminate ? "bar-indeterminate" : undefined}
              style={{
                width: indeterminate ? "35%" : `${barPct}%`,
                height: "100%",
                background: agentRunning
                  ? "linear-gradient(90deg, #60A5FA, #3B82F6)"
                  : "linear-gradient(90deg, #A78BFA, #8B5CF6)",
                borderRadius: 3,
                transition: indeterminate ? "none" : "width 0.5s ease",
              }}
            />
          </div>
          <div style={{ fontSize: 10, color: "#9898B8", marginTop: 5, textAlign: "center" }}>
            今日已投 {todayCount} / {dailyLimit} 份
          </div>
        </div>
      </div>
    </aside>
  );
}
