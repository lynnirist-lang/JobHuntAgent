"use client";

import { useChat, type Message } from "ai/react";
import { useCallback, useEffect, useRef, useState } from "react";

const HISTORY_KEY = "hermes_chat_history";

function loadHistory(): Message[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]");
  } catch {
    return [];
  }
}
import {
  Bot, CheckCircle2, Loader2, RefreshCw,
  Search, SendHorizonal, Settings2, Terminal,
  User, Wrench, Zap,
} from "lucide-react";

// ─────────────────────────── Types ──────────────────────────────────

interface TodayStats {
  today_sent: number;
  daily_limit: number;
  remaining: number;
}
interface ConsoleStatus {
  job_counts: Record<string, number>;
  today_stats: TodayStats;
  scrape_status: { running: boolean; last_result: Record<string, number> | null; error: string | null };
}

// ─────────────────────────── Static config ──────────────────────────

const PIPELINE_STAGES = [
  { key: "matched",      label: "待审批", accent: "#F59E0B" },
  { key: "approved",     label: "已批准", accent: "#10B981" },
  { key: "pending_send", label: "冷却中", accent: "#3B82F6" },
];

const ACTION_GROUPS = [
  {
    label: "爬取", Icon: Search, accent: "#8B5CF6",
    actions: [
      { label: "启动爬取", prompt: "帮我搜索上海的 Python 后端和 AI 工程师岗位" },
      { label: "爬取进度", prompt: "上次爬取任务进展如何" },
    ],
  },
  {
    label: "审批", Icon: CheckCircle2, accent: "#10B981",
    actions: [
      { label: "待审批列表", prompt: "显示所有待审批的岗位，列出 ID、职位名和薪资" },
      { label: "批量批准",   prompt: "把所有 matched 状态的岗位批准" },
    ],
  },
  {
    label: "系统", Icon: Settings2, accent: "#3B82F6",
    actions: [
      { label: "今日统计", prompt: "今天投递了几个，还剩多少名额" },
      { label: "查看策略", prompt: "当前策略配置是什么" },
    ],
  },
];

// ─────────────────────────── Message rendering ──────────────────────

function isToolLine(line: string) {
  return /^正在[\s\S]+?[…\.]{1,3}\s*$/.test(line.trim());
}

const EMOJI_COLORS: Record<string, string> = {
  "✅": "#10B981", "❌": "#EF4444", "⚠️": "#F59E0B", "⏳": "#3B82F6",
};

function parseInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|`([^`]+)`/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1]) {
      nodes.push(<strong key={m.index} style={{ fontWeight: 600 }}>{m[1]}</strong>);
    } else {
      nodes.push(
        <code key={m.index} style={{
          background: "rgba(255,255,255,.08)", padding: "1px 5px",
          borderRadius: 4, fontSize: "0.87em", fontFamily: "monospace",
        }}>{m[2]}</code>
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function MessageContent({ content }: { content: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {content.split("\n").map((line, i) => {
        if (!line.trim()) return <div key={i} style={{ height: 5 }} />;

        if (isToolLine(line)) {
          return (
            <div key={i} style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              background: "rgba(255,255,255,.055)", borderRadius: 20,
              padding: "2px 9px", width: "fit-content",
              color: "var(--muted2)", fontSize: 11,
            }}>
              <Wrench style={{ width: 9, height: 9, flexShrink: 0 }} />
              {line.trim()}
            </div>
          );
        }

        const emojiColor = Object.entries(EMOJI_COLORS).find(([k]) => line.startsWith(k))?.[1];

        if (/^[•·]\s/.test(line)) {
          return (
            <div key={i} style={{ display: "flex", gap: 7, lineHeight: 1.65, paddingLeft: 2 }}>
              <span style={{ color: "var(--muted2)", flexShrink: 0 }}>•</span>
              <span>{parseInline(line.replace(/^[•·]\s/, ""))}</span>
            </div>
          );
        }

        return (
          <div key={i} style={{ lineHeight: 1.65, color: emojiColor || "inherit" }}>
            {parseInline(line)}
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────── Status panel pieces ────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p style={{
      fontSize: 10, fontWeight: 700, color: "var(--muted2)",
      textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8,
    }}>
      {children}
    </p>
  );
}

// ─────────────────────────── Main page ──────────────────────────────

export default function ConsolePage() {
  const {
    messages, input, handleInputChange, handleSubmit, append,
    isLoading, error, reload, setMessages,
  } = useChat({ api: "/api/chat" });

  // 客户端挂载后恢复历史（SSR 阶段 window 不存在，不能放 initialMessages）
  useEffect(() => {
    const saved = loadHistory();
    if (saved.length > 0) setMessages(saved);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (messages.length > 0)
      localStorage.setItem(HISTORY_KEY, JSON.stringify(messages));
  }, [messages]);

  const [status, setStatus] = useState<ConsoleStatus | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/agent/console-status");
      if (res.ok) setStatus(await res.json());
    } catch { /* ignore */ }
  }, []);

  // Poll every 15s; also re-fetch when agent finishes a response
  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 15_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  useEffect(() => {
    if (!isLoading) fetchStatus();
  }, [isLoading, fetchStatus]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [input]);

  const sendPrompt = (prompt: string) => append({ role: "user", content: prompt });

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (input.trim()) handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const counts = status?.job_counts ?? {};
  const today = status?.today_stats;
  const scrapeRunning = status?.scrape_status?.running ?? false;
  const quotaPct = today
    ? Math.min(100, (today.today_sent / today.daily_limit) * 100)
    : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>

      {/* ── Topbar ── */}
      <header style={{
        height: "var(--topbar-h)", borderBottom: "1px solid var(--border)",
        background: "var(--card)", display: "flex", alignItems: "center",
        justifyContent: "space-between", padding: "0 20px", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Terminal style={{ width: 16, height: 16, color: "#8B5CF6" }} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>Agent 控制台</span>
          <span style={{ fontSize: 11, color: "var(--muted2)", marginLeft: 2 }}>
            Hermes · 工具调用 · 流水线控制
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 5,
            fontSize: 11,
            color: scrapeRunning ? "#F59E0B" : "var(--muted2)",
          }}>
            <div style={{
              width: 6, height: 6, borderRadius: "50%",
              background: scrapeRunning ? "#F59E0B" : "#6B7280",
              animation: scrapeRunning ? "pulse 1.5s ease-in-out infinite" : "none",
            }} />
            {scrapeRunning ? "爬取中" : "空闲"}
          </div>
          <button onClick={() => { setMessages([]); localStorage.removeItem(HISTORY_KEY); }} title="清空对话" style={{
            background: "transparent", border: "none",
            color: "var(--muted2)", cursor: "pointer", padding: 4,
          }}>
            <RefreshCw style={{ width: 14, height: 14 }} />
          </button>
        </div>
      </header>

      {/* ── Body ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* ── Left status panel ── */}
        <aside style={{
          width: 252, flexShrink: 0,
          borderRight: "1px solid var(--border)",
          overflowY: "auto",
          display: "flex", flexDirection: "column", gap: 22,
          padding: "18px 14px",
        }}>

          {/* Pipeline counts */}
          <section>
            <SectionLabel>流水线状态</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {PIPELINE_STAGES.map(({ key, label, accent }) => (
                <button key={key}
                  onClick={() => sendPrompt(`显示所有 ${key} 状态的岗位，列出 ID、职位名和薪资`)}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    background: "transparent", border: "1px solid var(--border)",
                    borderRadius: 8, padding: "8px 10px",
                    cursor: "pointer", color: "var(--fg)", width: "100%",
                    transition: "background 0.12s",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,.04)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: accent }} />
                    <span style={{ fontSize: 12 }}>{label}</span>
                  </div>
                  <span style={{ fontSize: 14, fontWeight: 700, color: accent }}>
                    {counts[key] ?? 0}
                  </span>
                </button>
              ))}
            </div>
          </section>

          {/* Today quota */}
          <section>
            <SectionLabel>今日配额</SectionLabel>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "var(--muted2)" }}>已投</span>
                <span style={{ fontWeight: 600 }}>
                  {today?.today_sent ?? "—"} / {today?.daily_limit ?? "—"}
                </span>
              </div>
              <div style={{
                height: 5, background: "rgba(255,255,255,.08)",
                borderRadius: 3, overflow: "hidden",
              }}>
                <div style={{
                  height: "100%", borderRadius: 3, width: `${quotaPct}%`,
                  background: today?.remaining === 0 ? "#EF4444" : "#10B981",
                  transition: "width 0.5s ease",
                }} />
              </div>
              <p style={{ fontSize: 11, color: "var(--muted2)" }}>
                {today ? `剩余 ${today.remaining} 个名额` : "加载中…"}
              </p>
            </div>
          </section>

          {/* Quick action groups */}
          {ACTION_GROUPS.map(({ label, Icon, accent, actions }) => (
            <section key={label}>
              <SectionLabel>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  <Icon style={{ width: 10, height: 10 }} />
                  {label}
                </span>
              </SectionLabel>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 5 }}>
                {actions.map((a) => (
                  <button key={a.label} onClick={() => sendPrompt(a.prompt)}
                    style={{
                      padding: "8px 5px", fontSize: 11, textAlign: "center",
                      color: "var(--muted)", background: "var(--card)",
                      border: "1px solid var(--border)", borderRadius: 8,
                      cursor: "pointer", lineHeight: 1.3,
                      transition: "border-color 0.12s, color 0.12s",
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.borderColor = accent;
                      e.currentTarget.style.color = accent;
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.borderColor = "var(--border)";
                      e.currentTarget.style.color = "var(--muted)";
                    }}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </section>
          ))}

        </aside>

        {/* ── Chat panel ── */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* Messages */}
          <div style={{
            flex: 1, overflowY: "auto",
            padding: "20px 24px",
            display: "flex", flexDirection: "column", gap: 14,
          }}>

            {/* Empty state */}
            {messages.length === 0 && (
              <div style={{
                display: "flex", flexDirection: "column", alignItems: "center",
                justifyContent: "center", height: "100%", gap: 14,
              }}>
                <div style={{
                  width: 52, height: 52, borderRadius: 14,
                  background: "rgba(139,92,246,.1)",
                  border: "1px solid rgba(139,92,246,.2)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Zap style={{ width: 22, height: 22, color: "#8B5CF6" }} />
                </div>
                <div style={{ textAlign: "center" }}>
                  <p style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>
                    Hermes 就绪
                  </p>
                  <p style={{ color: "var(--muted2)", fontSize: 12 }}>
                    用自然语言控制求职流水线 · 点击左侧快捷操作或直接输入
                  </p>
                </div>
              </div>
            )}

            {messages.map((m) => (
              <div key={m.id} style={{
                display: "flex", gap: 9,
                flexDirection: m.role === "user" ? "row-reverse" : "row",
              }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: m.role === "user"
                    ? "rgba(59,130,246,.12)"
                    : "rgba(139,92,246,.12)",
                }}>
                  {m.role === "user"
                    ? <User style={{ width: 13, height: 13, color: "#3B82F6" }} />
                    : <Bot style={{ width: 13, height: 13, color: "#8B5CF6" }} />
                  }
                </div>
                <div style={{
                  maxWidth: "78%", padding: "10px 14px",
                  borderRadius: 14, fontSize: 13,
                  background: m.role === "user"
                    ? "rgba(59,130,246,.08)"
                    : "var(--card)",
                  border: m.role === "user"
                    ? "1px solid rgba(59,130,246,.18)"
                    : "1px solid var(--border)",
                  color: "var(--fg)",
                  borderTopRightRadius: m.role === "user" ? 4 : 14,
                  borderTopLeftRadius:  m.role === "user" ? 14 : 4,
                }}>
                  {m.role === "assistant"
                    ? <MessageContent content={m.content} />
                    : <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
                  }
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div style={{ display: "flex", gap: 9 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 8,
                  background: "rgba(139,92,246,.12)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Bot style={{ width: 13, height: 13, color: "#8B5CF6" }} />
                </div>
                <div style={{
                  background: "var(--card)", border: "1px solid var(--border)",
                  borderRadius: 14, borderTopLeftRadius: 4,
                  padding: "10px 14px",
                  display: "flex", alignItems: "center", gap: 6,
                  color: "var(--muted2)", fontSize: 12,
                }}>
                  <Loader2 style={{ width: 12, height: 12, animation: "spin 1s linear infinite" }} />
                  <span>Hermes 正在处理…</span>
                </div>
              </div>
            )}

            {/* Error */}
            {!!error && (
              <div style={{
                display: "flex", alignItems: "center", gap: 8, fontSize: 12,
                color: "#EF4444", background: "rgba(239,68,68,.08)",
                border: "1px solid rgba(239,68,68,.2)",
                borderRadius: 8, padding: "10px 14px",
              }}>
                <span>连接失败：{error?.message}</span>
                <button onClick={() => reload()} style={{
                  background: "none", border: "none", color: "#EF4444",
                  cursor: "pointer", textDecoration: "underline", fontSize: 12,
                }}>重试</button>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input bar */}
          <div style={{
            padding: "12px 20px 16px", flexShrink: 0,
            borderTop: "1px solid var(--border)",
          }}>
            <form onSubmit={handleSubmit} style={{
              display: "flex", alignItems: "flex-end", gap: 8,
              background: "var(--card)", border: "1px solid var(--border)",
              borderRadius: 12, padding: "10px 14px",
              transition: "border-color 0.15s",
            }}
              onFocus={e => (e.currentTarget.style.borderColor = "#8B5CF6")}
              onBlur={e => (e.currentTarget.style.borderColor = "var(--border)")}
            >
              <textarea ref={textareaRef}
                value={input}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="告诉 Hermes 你想做什么… (Enter 发送，Shift+Enter 换行)"
                rows={1}
                style={{
                  flex: 1, background: "transparent", border: "none",
                  outline: "none", color: "var(--fg)", fontSize: 13,
                  resize: "none", lineHeight: 1.5,
                }}
              />
              <button type="submit"
                disabled={isLoading || !input.trim()}
                style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: "#8B5CF6", border: "none",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: isLoading || !input.trim() ? "not-allowed" : "pointer",
                  opacity: isLoading || !input.trim() ? 0.3 : 1,
                  flexShrink: 0, transition: "opacity 0.15s",
                }}
              >
                <SendHorizonal style={{ width: 14, height: 14, color: "#fff" }} />
              </button>
            </form>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin  { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
      `}</style>
    </div>
  );
}
