"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import {
  getJobs, getScrapeStatus, getApplyTaskStatus,
  getTodayStats, triggerScrape, batchApply, checkLogin, Job,
  getSettings, updateSearchSettings, retryGreetings,
} from "@/lib/api";
import {
  Send, BarChart2, MessageSquare, Search,
  Settings, AlertOctagon, Clock, X, ClipboardList,
  TrendingUp, Activity, Zap, BellOff,
} from "lucide-react";

/* ── Clay card base ─────────────────────────────────────────── */
const clay: React.CSSProperties = {
  background: "#FFFFFF",
  borderRadius: 20,
  border: "3px solid rgba(255,255,255,0.92)",
  boxShadow: "8px 8px 22px rgba(139,92,246,0.09), -2px -2px 7px rgba(255,255,255,0.88), inset 0 1px 0 rgba(255,255,255,0.97)",
  padding: 20,
};

/* ── Bounce press helpers ────────────────────────────────────── */
const ALL_TRANS = "transform 0.45s cubic-bezier(0.34,1.56,0.64,1), background 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease, color 0.15s ease";
const pressBounce = (el: HTMLElement) => {
  el.style.transform = "scale(0.93)";
  el.style.transition = `transform 0.08s ease, background 0.15s ease, box-shadow 0.15s ease`;
};
const releaseBounce = (el: HTMLElement) => {
  el.style.transform = "scale(1)";
  el.style.transition = ALL_TRANS;
};

/* ── Metric card ─────────────────────────────────────────────── */
function MetricCard({
  icon: Icon, value, label, color, glow,
}: {
  icon: React.ElementType; value: string | number;
  label: string; color: string; glow: string;
}) {
  return (
    <div
      style={{ ...clay, padding: "18px 18px 14px", position: "relative", overflow: "hidden", cursor: "default" }}
      onMouseEnter={(e) => {
        const el = e.currentTarget as HTMLDivElement;
        el.style.transform = "translateY(-3px)";
        el.style.boxShadow = `12px 12px 30px ${glow}, -3px -3px 9px rgba(255,255,255,0.92), inset 0 1px 0 rgba(255,255,255,0.97)`;
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget as HTMLDivElement;
        el.style.transform = "translateY(0)";
        el.style.boxShadow = "8px 8px 22px rgba(139,92,246,0.09), -2px -2px 7px rgba(255,255,255,0.88), inset 0 1px 0 rgba(255,255,255,0.97)";
      }}
    >
      <div style={{ position: "absolute", top: -18, right: -18, width: 64, height: 64, borderRadius: "50%", background: color, opacity: 0.10 }} />
      <div
        style={{
          width: 36, height: 36, borderRadius: 11,
          background: color,
          border: "2px solid rgba(255,255,255,0.45)",
          boxShadow: `3px 3px 10px ${glow}`,
          display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 12,
        }}
      >
        <Icon size={16} color="white" strokeWidth={2.5} />
      </div>
      <div
        style={{
          fontSize: 32, fontWeight: 900, lineHeight: 1, marginBottom: 5,
          fontVariantNumeric: "tabular-nums",
          background: color,
          WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 12, color: "#6B6A8A", fontWeight: 600 }}>{label}</div>
    </div>
  );
}

/* ── Status badge ────────────────────────────────────────────── */
function Badge({ status }: { status: string }) {
  const map: Record<string, { label: string; bg: string; color: string }> = {
    pending_send: { label: "待发送", bg: "rgba(59,130,246,0.10)",  color: "#3B82F6" },
    sent:         { label: "已发送", bg: "rgba(16,185,129,0.12)",  color: "#059669" },
    matched:      { label: "待审批", bg: "rgba(139,92,246,0.10)",  color: "#8B5CF6" },
    approved:     { label: "已批准", bg: "rgba(16,185,129,0.12)",  color: "#059669" },
    skipped:      { label: "已跳过", bg: "rgba(165,163,192,0.12)", color: "#A5A3C0" },
    failed:       { label: "失败",   bg: "rgba(244,63,94,0.10)",   color: "#F43F5E" },
  };
  const s = map[status] || { label: status, bg: "rgba(165,163,192,0.12)", color: "#A5A3C0" };
  return (
    <span style={{ background: s.bg, color: s.color, borderRadius: 20, fontSize: 11, fontWeight: 700, padding: "3px 10px", whiteSpace: "nowrap" }}>
      {s.label}
    </span>
  );
}

/* ── Countdown ───────────────────────────────────────────────── */
function Countdown({ seconds }: { seconds: number }) {
  const [s, setS] = useState(seconds);
  useEffect(() => {
    if (s <= 0) return;
    const id = setInterval(() => setS((v) => v - 1), 1000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <span style={{ fontSize: 11, color: "#3B82F6", fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>
      {Math.floor(s / 60)}:{String(s % 60).padStart(2, "0")}
    </span>
  );
}

/* ── Input style ─────────────────────────────────────────────── */
const inputStyle: React.CSSProperties = {
  background: "#F3F0FF",
  border: "2px solid rgba(139,92,246,0.14)",
  borderRadius: 12,
  color: "#1A1A2E",
  fontSize: 13,
  padding: "8px 11px",
  outline: "none",
  fontFamily: "var(--font-nunito), 'Nunito', sans-serif",
  fontWeight: 600,
  width: "100%",
};

/* ── Flat fill button styles ─────────────────────────────────── */
const btnBlue: React.CSSProperties = {
  background: "#3B82F6",
  color: "#fff",
  border: "none",
  borderRadius: 14,
  fontSize: 13, fontWeight: 700, padding: "11px 18px",
  cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
  fontFamily: "var(--font-nunito), 'Nunito', sans-serif",
  width: "100%",
};

/* ── Quick action link style (shared) ───────────────────────── */
const quickActionStyle = (color: string, bg: string, bd: string): React.CSSProperties => ({
  display: "flex", alignItems: "center", gap: 8,
  background: bg, border: `1px solid ${bd}`, color,
  borderRadius: 13, fontSize: 13, fontWeight: 700,
  padding: "9px 14px", textDecoration: "none",
  fontFamily: "var(--font-nunito),'Nunito',sans-serif",
  width: "100%", cursor: "pointer",
});

/* ── Dashboard ───────────────────────────────────────────────── */
export default function DashboardPage() {
  const [pendingJobs, setPendingJobs] = useState<Job[]>([]);
  const [todayCount, setTodayCount]   = useState(0);
  const [totalCount, setTotalCount]   = useState(0);
  const [dailyLimit, setDailyLimit]   = useState(30);
  const [agentRunning, setAgentRunning] = useState(false);
  const [applyRunning, setApplyRunning] = useState(false);
  const [applyDone,    setApplyDone]    = useState(0);
  const [applyTotal,   setApplyTotal]   = useState(0);
  const [scrapeProgress, setScrapeProgress] = useState("");
  const [applyProgress, setApplyProgress]   = useState("");
  const [loadingData, setLoadingData] = useState(true);

  const [keywords, setKeywords]       = useState<string[]>(["Agent工程师", "Python后端"]);
  const [keywordInput, setKeywordInput] = useState("");
  const [city, setCity]               = useState("上海");
  const [salary, setSalary]           = useState("");
  const [activityLog, setActivityLog] = useState<string[]>(["系统就绪，等待任务..."]);
  const didInit = useRef(false);

  const lastScrapeStoppedRef = useRef<string | null>(null);
  const lastApplyStoppedRef  = useRef<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [jobsRes, statsRes, scrapeRes, applyRes] = await Promise.all([
        getJobs({ status: "pending_send", limit: 10 }).catch(() => ({ items: [], count: 0 })),
        getTodayStats().catch(() => ({ today_sent: 0, total_sent: 0, daily_limit: 30, remaining: 30 })),
        getScrapeStatus().catch(() => ({ running: false, progress: "", total: 0, errors: [], stopped_reason: null })),
        getApplyTaskStatus().catch(() => ({ running: false, progress: "", success_count: 0, fail_count: 0, total_jobs: 0, stopped_reason: null, alert: null })),
      ]);
      setPendingJobs(jobsRes.items);
      setTodayCount(statsRes.today_sent);
      setTotalCount(statsRes.total_sent ?? 0);
      setDailyLimit(statsRes.daily_limit ?? 30);
      setAgentRunning(scrapeRes.running || applyRes.running);
      setApplyRunning(applyRes.running);
      setApplyDone((applyRes.success_count ?? 0) + (applyRes.fail_count ?? 0));
      setApplyTotal(applyRes.total_jobs ?? 0);
      if (scrapeRes.progress) setScrapeProgress(scrapeRes.progress);
      if (applyRes.progress)  setApplyProgress(applyRes.progress);

      // Show stopped_reason in activity log (deduplicated)
      if (scrapeRes.stopped_reason && scrapeRes.stopped_reason !== lastScrapeStoppedRef.current) {
        lastScrapeStoppedRef.current = scrapeRes.stopped_reason;
        const msg = scrapeRes.stopped_reason;
        setActivityLog((prev) => [`${new Date().toLocaleTimeString("zh-CN")} — 爬取停止：${msg}`, ...prev.slice(0, 19)]);
      }
      if (!scrapeRes.running && !scrapeRes.stopped_reason) lastScrapeStoppedRef.current = null;

      if (applyRes.stopped_reason && applyRes.stopped_reason !== lastApplyStoppedRef.current) {
        lastApplyStoppedRef.current = applyRes.stopped_reason;
        const msg = applyRes.stopped_reason;
        setActivityLog((prev) => [`${new Date().toLocaleTimeString("zh-CN")} — 投递停止：${msg}`, ...prev.slice(0, 19)]);
      }
      if (!applyRes.running && !applyRes.stopped_reason) lastApplyStoppedRef.current = null;

      // Show scrape completion count
      if (!scrapeRes.running && scrapeRes.total > 0) {
        setScrapeProgress(`已抓取 ${scrapeRes.total} 条新岗位`);
      }

    } catch { /* silent */ }
    finally { setLoadingData(false); }
  }, []);

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    fetchData();
    checkLogin().catch(() => {});
    // Load persisted search settings
    getSettings()
      .then((s) => {
        if (s.search?.keywords?.length) setKeywords(s.search.keywords);
        if (s.search?.city)             setCity(s.search.city);
        if (s.search?.salary_code != null) setSalary(s.search.salary_code);
      })
      .catch(() => {});
  }, [fetchData]);

  useEffect(() => {
    if (!agentRunning) return;
    const id = setInterval(fetchData, 3000);
    return () => clearInterval(id);
  }, [agentRunning, fetchData]);

  const addLog = (msg: string) =>
    setActivityLog((prev) => [`${new Date().toLocaleTimeString("zh-CN")} — ${msg}`, ...prev.slice(0, 19)]);

  const handleScrape = async () => {
    try {
      // Persist search settings before triggering
      updateSearchSettings({ keywords, city, salary_code: salary || "" }).catch(() => {});
      await triggerScrape({ keywords, city, salary_code: salary || undefined, max_pages: 3 });
      addLog("开始爬取任务...");
      lastScrapeStoppedRef.current = null;  // reset so new stopped_reason shows up
      setAgentRunning(true);  // optimistically start polling
      fetchData();
    } catch (e: unknown) { addLog(`爬取失败: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const handleRetryGreetings = async () => {
    try {
      await retryGreetings();
      addLog("重新生成打招呼语任务已启动...");
      lastScrapeStoppedRef.current = null;
      setAgentRunning(true);
      fetchData();
    } catch (e: unknown) { addLog(`重试失败: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const handleBatchApply = async () => {
    try {
      await batchApply();
      addLog("开始批量投递...");
      fetchData();
    } catch (e: unknown) { addLog(`投递失败: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const handleKwKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === "Enter" || e.key === ",") && keywordInput.trim()) {
      e.preventDefault();
      const kw = keywordInput.trim().replace(/,$/, "");
      if (kw && !keywords.includes(kw)) setKeywords([...keywords, kw]);
      setKeywordInput("");
    }
  };

  const todayPct = Math.min(100, (todayCount / dailyLimit) * 100);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>

      {/* ── Topbar ──────────────────────────────────────────── */}
      <header
        style={{
          height: "var(--topbar-h)",
          background: "rgba(248,244,255,0.80)",
          borderBottom: "1px solid rgba(255,255,255,0.65)",
          boxShadow: "0 4px 20px rgba(139,92,246,0.06)",
          backdropFilter: "blur(18px)",
          WebkitBackdropFilter: "blur(18px)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 22px", position: "sticky", top: 0, zIndex: 40, flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-fredoka), 'Fredoka', sans-serif",
            fontWeight: 600, fontSize: 17, color: "#1E1B3A",
          }}
        >
          控制台
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <button
            className="btn-ghost"
            style={{ background: "rgba(255,255,255,0.70)", border: "1px solid rgba(255,255,255,0.75)", backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)", borderRadius: 11, padding: "5px 9px", cursor: "pointer", display: "flex", alignItems: "center", color: "#A5A3C0" }}
            onMouseDown={(e) => pressBounce(e.currentTarget)}
            onMouseUp={(e)   => releaseBounce(e.currentTarget)}
            onMouseLeave={(e) => releaseBounce(e.currentTarget)}
            title="通知"
          >
            <BellOff size={15} />
          </button>
          <Link
            href="/settings"
            className="btn-ghost"
            style={{ background: "rgba(255,255,255,0.70)", border: "1px solid rgba(255,255,255,0.75)", backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)", color: "#6B6A8A", fontSize: 12, fontWeight: 700, padding: "5px 13px", borderRadius: 11, textDecoration: "none", display: "flex", alignItems: "center", gap: 5, fontFamily: "var(--font-nunito), 'Nunito', sans-serif" }}
            onMouseDown={(e) => pressBounce(e.currentTarget)}
            onMouseUp={(e)   => releaseBounce(e.currentTarget)}
            onMouseLeave={(e) => releaseBounce(e.currentTarget)}
          >
            <Settings size={12} /> 设置
          </Link>
          <button
            className="btn-ghost-danger"
            onClick={() => addLog("紧急暂停已触发")}
            style={{ background: "rgba(244,63,94,0.08)", border: "1px solid rgba(244,63,94,0.22)", color: "#F43F5E", fontSize: 12, fontWeight: 700, cursor: "pointer", padding: "5px 13px", borderRadius: 11, display: "flex", alignItems: "center", gap: 5, fontFamily: "var(--font-nunito), 'Nunito', sans-serif" }}
            onMouseDown={(e) => pressBounce(e.currentTarget)}
            onMouseUp={(e)   => releaseBounce(e.currentTarget)}
            onMouseLeave={(e) => releaseBounce(e.currentTarget)}
          >
            <AlertOctagon size={12} /> 紧急暂停
          </button>
        </div>
      </header>

      {/* ── Content ─────────────────────────────────────────── */}
      <div style={{ padding: "18px 22px 28px", display: "flex", flexDirection: "column", gap: 16, flex: 1 }}>

        {/* Status bar */}
        <div
          style={{
            ...clay,
            padding: "13px 18px",
            borderColor: agentRunning ? "rgba(59,130,246,0.30)" : "rgba(255,255,255,0.92)",
            background: agentRunning ? "linear-gradient(135deg, rgba(59,130,246,0.06), rgba(96,165,250,0.04))" : "#fff",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
            <span
              style={{
                width: 9, height: 9, borderRadius: "50%", flexShrink: 0,
                background: agentRunning ? "#3B82F6" : "#10B981",
                boxShadow: agentRunning ? "0 0 8px rgba(59,130,246,0.65)" : "0 0 8px rgba(16,185,129,0.55)",
              }}
            />
            <span
              style={{
                fontSize: 13, fontWeight: 700,
                color: agentRunning ? "#3B82F6" : "#10B981",
                fontFamily: "var(--font-fredoka), 'Fredoka', sans-serif",
              }}
            >
              {agentRunning ? "运行中 · Agent 活跃" : "Agent 已就绪"}
            </span>
            {(scrapeProgress || applyProgress) && (
              <span style={{ fontSize: 11, color: "#A5A3C0", marginLeft: 4 }}>
                {scrapeProgress || applyProgress}
              </span>
            )}
          </div>
          {(() => {
            const determinate   = applyRunning && applyTotal > 0;
            const indeterminate = agentRunning && !determinate;
            const pct = determinate
              ? Math.min(99, Math.round((applyDone / applyTotal) * 100))
              : Math.round((todayCount / Math.max(dailyLimit, 1)) * 100);
            return (
              <div style={{ height: 6, background: "rgba(139,92,246,0.08)", borderRadius: 3, overflow: "hidden" }}>
                <div
                  className={indeterminate ? "bar-indeterminate" : undefined}
                  style={{
                    width: indeterminate ? "35%" : `${pct}%`,
                    height: "100%",
                    background: agentRunning
                      ? "linear-gradient(90deg, #60A5FA, #3B82F6)"
                      : "linear-gradient(90deg, #34D399, #10B981)",
                    borderRadius: 3,
                    transition: indeterminate ? "none" : "width 0.5s ease",
                  }}
                />
              </div>
            );
          })()}
        </div>

        {/* Metric cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14 }}>
          <MetricCard icon={Send}      value={loadingData ? "—" : todayCount} label="今日已投" color="linear-gradient(135deg,#60A5FA,#3B82F6)" glow="rgba(59,130,246,0.22)" />
          <MetricCard icon={BarChart2} value={loadingData ? "—" : totalCount} label="总投递量" color="linear-gradient(135deg,#A78BFA,#8B5CF6)" glow="rgba(139,92,246,0.24)" />
        </div>

        {/* Queue + Search */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>

          {/* Pending queue */}
          <div style={clay}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <span style={{ fontFamily: "var(--font-fredoka),'Fredoka',sans-serif", fontWeight: 600, fontSize: 14, color: "#1E1B3A", display: "flex", alignItems: "center", gap: 7 }}>
                <Clock size={14} color="#3B82F6" strokeWidth={2.5} />
                待发送队列
                <span style={{ background: "rgba(59,130,246,0.10)", color: "#3B82F6", borderRadius: 20, fontSize: 11, fontWeight: 700, padding: "1px 9px" }}>
                  {pendingJobs.length}
                </span>
              </span>
              <Link href="/records" style={{ fontSize: 11, color: "#9898B8", textDecoration: "none", fontWeight: 600 }}>
                全部 →
              </Link>
            </div>
            {loadingData ? (
              <div style={{ color: "#A5A3C0", fontSize: 12, padding: "12px 0" }}>加载中…</div>
            ) : pendingJobs.length === 0 ? (
              <div style={{ color: "#A5A3C0", fontSize: 13, padding: "22px 0", textAlign: "center", fontWeight: 600 }}>
                暂无待发送岗位
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {pendingJobs.slice(0, 5).map((job) => (
                  <div
                    key={job.id}
                    className="job-item"
                    style={{ background: "rgba(139,92,246,0.05)", border: "2px solid rgba(139,92,246,0.10)", borderRadius: 13, padding: "9px 12px", display: "flex", alignItems: "center", gap: 11 }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#1E1B3A", marginBottom: 2 }}>{job.company}</div>
                      <div style={{ fontSize: 11, color: "#A5A3C0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{job.title}</div>
                    </div>
                    <Countdown seconds={300} />
                    <button
                      className="btn-cancel"
                      style={{ background: "rgba(255,255,255,0.85)", border: "1px solid rgba(165,163,192,0.22)", color: "#A5A3C0", fontSize: 11, fontWeight: 700, cursor: "pointer", padding: "4px 10px", borderRadius: 8, display: "flex", alignItems: "center", gap: 3, fontFamily: "var(--font-nunito),'Nunito',sans-serif" }}
                      onMouseDown={(e) => pressBounce(e.currentTarget)}
                      onMouseUp={(e)   => releaseBounce(e.currentTarget)}
                      onMouseLeave={(e) => releaseBounce(e.currentTarget)}
                    >
                      <X size={9} /> 取消
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Search settings */}
          <div style={clay}>
            <div style={{ fontFamily: "var(--font-fredoka),'Fredoka',sans-serif", fontWeight: 600, fontSize: 14, color: "#1E1B3A", display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
              <Search size={14} color="#8B5CF6" strokeWidth={2.5} />
              搜索设置
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "#A5A3C0", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  关键词
                </label>
                <div className="input-clay" style={{ display: "flex", flexWrap: "wrap", gap: 6, background: "#F3F0FF", border: "2px solid rgba(139,92,246,0.12)", borderRadius: 12, padding: "7px 9px", minHeight: 42 }}>
                  {keywords.map((kw) => (
                    <span key={kw} style={{ background: "rgba(139,92,246,0.10)", color: "#8B5CF6", borderRadius: 20, fontSize: 12, fontWeight: 700, padding: "2px 9px", display: "flex", alignItems: "center", gap: 4 }}>
                      {kw}
                      <button onClick={() => setKeywords(keywords.filter((k) => k !== kw))} style={{ background: "none", border: "none", color: "#A78BFA", cursor: "pointer", fontSize: 13, padding: 0, lineHeight: 1, display: "flex" }}>×</button>
                    </span>
                  ))}
                  <input
                    value={keywordInput}
                    onChange={(e) => setKeywordInput(e.target.value)}
                    onKeyDown={handleKwKeyDown}
                    placeholder="输入后 Enter…"
                    style={{ background: "transparent", border: "none", outline: "none", color: "#1E1B3A", fontSize: 12, fontWeight: 600, flex: 1, minWidth: 80, fontFamily: "var(--font-nunito),'Nunito',sans-serif" }}
                  />
                </div>
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "#A5A3C0", marginBottom: 5 }}>城市</label>
                  <input
                    type="text"
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="如：广州、深圳、远程"
                    className="input-clay"
                    style={inputStyle}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ display: "block", fontSize: 11, fontWeight: 700, color: "#A5A3C0", marginBottom: 5 }}>薪资</label>
                  <select value={salary} onChange={(e) => setSalary(e.target.value)} className="input-clay" style={{ ...inputStyle, cursor: "pointer" }}>
                    <option value="">不限</option>
                    {["10","15","20","25","30"].map((v) => <option key={v} value={v}>{v}k+</option>)}
                  </select>
                </div>
              </div>
              <button
                className="btn-flat-blue"
                style={btnBlue}
                onClick={handleScrape}
                onMouseDown={(e) => pressBounce(e.currentTarget)}
                onMouseUp={(e)   => releaseBounce(e.currentTarget)}
                onMouseLeave={(e) => releaseBounce(e.currentTarget)}
              >
                <Search size={13} /> 开始爬取
              </button>
              <button
                className="btn-flat-blue"
                style={{ ...btnBlue, background: "linear-gradient(135deg,#10B981,#059669)", marginTop: 8 }}
                onClick={handleRetryGreetings}
                onMouseDown={(e) => pressBounce(e.currentTarget)}
                onMouseUp={(e)   => releaseBounce(e.currentTarget)}
                onMouseLeave={(e) => releaseBounce(e.currentTarget)}
                title="为已抓取但打招呼生成失败的岗位重新触发生成，无需重新爬取"
              >
                <MessageSquare size={13} /> 重新生成打招呼
              </button>
            </div>
          </div>
        </div>

        {/* Activity + Right column */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>

          {/* Activity log */}
          <div style={clay}>
            <div style={{ fontFamily: "var(--font-fredoka),'Fredoka',sans-serif", fontWeight: 600, fontSize: 14, color: "#1E1B3A", display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
              <Activity size={14} color="#8B5CF6" strokeWidth={2.5} />
              活动记录
              <span style={{ marginLeft: "auto", fontSize: 11, color: "#A5A3C0", fontWeight: 600 }}>最近 20 条</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {activityLog.map((log, i) => (
                <div
                  key={i}
                  className="log-item"
                  style={{
                    fontSize: 12, padding: "6px 10px",
                    color: i === 0 ? "#1A1A2E" : "#9898B8",
                    fontWeight: i === 0 ? 700 : 500,
                    background: i === 0 ? "rgba(139,92,246,0.07)" : "transparent",
                    borderRadius: 9,
                    borderLeft: i === 0 ? "3px solid #8B5CF6" : "3px solid transparent",
                  }}
                >
                  {log}
                </div>
              ))}
            </div>
          </div>

          {/* Right column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

            {/* Quick controls */}
            <div style={clay}>
              <div style={{ fontFamily: "var(--font-fredoka),'Fredoka',sans-serif", fontWeight: 600, fontSize: 14, color: "#1A1A2E", display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
                <Zap size={14} color="#3B82F6" strokeWidth={2.5} />
                快速操作
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {[
                  { type: "button" as const, Icon: Zap,          label: "一键批量投递", color: "#3B82F6", bg: "rgba(59,130,246,0.08)",  bd: "rgba(59,130,246,0.18)",  cls: "quick-link-blue",   onClick: handleBatchApply },
                  { type: "link"   as const, href: "/records",   Icon: ClipboardList,  label: "查看投递记录", color: "#8B5CF6", bg: "rgba(139,92,246,0.08)", bd: "rgba(139,92,246,0.18)", cls: "quick-link-purple" },
                  { type: "link"   as const, href: "/analytics", Icon: TrendingUp,     label: "效果分析",     color: "#059669", bg: "rgba(16,185,129,0.08)", bd: "rgba(16,185,129,0.18)", cls: "quick-link-green"  },
                ].map((item) =>
                  item.type === "button" ? (
                    <button
                      key={item.label}
                      className={item.cls}
                      style={quickActionStyle(item.color, item.bg, item.bd)}
                      onClick={item.onClick}
                      onMouseDown={(e) => pressBounce(e.currentTarget)}
                      onMouseUp={(e)   => releaseBounce(e.currentTarget)}
                      onMouseLeave={(e) => releaseBounce(e.currentTarget)}
                    >
                      <item.Icon size={13} strokeWidth={2.5} /> {item.label}
                    </button>
                  ) : (
                    <Link
                      key={item.label} href={(item as { href: string }).href}
                      className={item.cls}
                      style={quickActionStyle(item.color, item.bg, item.bd)}
                      onMouseDown={(e) => pressBounce(e.currentTarget)}
                      onMouseUp={(e)   => releaseBounce(e.currentTarget)}
                      onMouseLeave={(e) => releaseBounce(e.currentTarget)}
                    >
                      <item.Icon size={13} strokeWidth={2.5} /> {item.label}
                    </Link>
                  )
                )}
              </div>
            </div>

            {/* Daily quota */}
            <div style={clay}>
              <div style={{ fontFamily: "var(--font-fredoka),'Fredoka',sans-serif", fontWeight: 600, fontSize: 14, color: "#1E1B3A", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                今日投递配额
                <span style={{ fontSize: 11, fontWeight: 700, color: "#6B6A8A" }}>{todayCount} / {dailyLimit}</span>
              </div>
              <div style={{ marginBottom: 6 }}>
                <div style={{ height: 8, background: "rgba(139,92,246,0.07)", borderRadius: 4, overflow: "hidden" }}>
                  <div style={{ width: `${todayPct}%`, height: "100%", background: "linear-gradient(90deg,#A78BFA,#8B5CF6)", borderRadius: 4, boxShadow: "0 0 6px rgba(139,92,246,0.30)", transition: "width 0.5s ease" }} />
                </div>
              </div>
              <div style={{ fontSize: 11, color: "#9898B8", fontWeight: 600 }}>
                今日剩余 {dailyLimit - todayCount} 个投递名额
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
