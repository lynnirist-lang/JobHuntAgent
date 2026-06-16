"use client";

import { useState } from "react";
import { Job, approveJob, skipJob, updateGreeting } from "@/lib/api";
import { STATUS_LABELS, formatDate } from "@/lib/utils";
import { CheckIcon, XIcon, PencilIcon, ExternalLinkIcon } from "lucide-react";

interface JobCardProps {
  job: Job;
  onAction?: () => void;
}

const STATUS_STYLE: Record<string, { bg: string; color: string; border: string }> = {
  matched:      { bg: "rgba(139,92,246,0.10)",  color: "#8B5CF6", border: "rgba(139,92,246,0.24)"  },
  pending:      { bg: "rgba(59,130,246,0.10)",  color: "#3B82F6", border: "rgba(59,130,246,0.24)"  },
  approved:     { bg: "rgba(59,130,246,0.10)",  color: "#3B82F6", border: "rgba(59,130,246,0.24)"  },
  sent:         { bg: "rgba(16,185,129,0.10)",  color: "#10B981", border: "rgba(16,185,129,0.24)"  },
  low_priority: { bg: "rgba(152,152,184,0.12)", color: "#9898B8", border: "rgba(152,152,184,0.22)" },
  skipped:      { bg: "rgba(152,152,184,0.12)", color: "#9898B8", border: "rgba(152,152,184,0.22)" },
  failed:       { bg: "rgba(244,63,94,0.10)",   color: "#F43F5E", border: "rgba(244,63,94,0.24)"   },
};

export default function JobCard({ job, onAction }: JobCardProps) {
  const [editing, setEditing] = useState(false);
  const [greeting, setGreeting] = useState(job.greeting_message || "");
  const [loading, setLoading] = useState(false);

  const handleApprove = async () => {
    setLoading(true);
    try {
      if (greeting !== job.greeting_message) await updateGreeting(job.id, greeting);
      await approveJob(job.id);
      onAction?.();
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    setLoading(true);
    try {
      await skipJob(job.id);
      onAction?.();
    } finally {
      setLoading(false);
    }
  };

  const st = STATUS_STYLE[job.status] ?? STATUS_STYLE.low_priority;

  return (
    <div
      style={{
        background: "rgba(255,255,255,0.95)",
        borderRadius: 20,
        border: "3px solid rgba(255,255,255,0.95)",
        boxShadow: "8px 8px 24px rgba(139,92,246,0.10), -2px -2px 8px rgba(255,255,255,0.88), inset 0 1px 0 rgba(255,255,255,0.97)",
        padding: "18px 18px 14px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        transition: "box-shadow 0.2s ease, transform 0.2s ease",
      }}
      onMouseEnter={(e) => {
        const d = e.currentTarget as HTMLDivElement;
        d.style.transform = "translateY(-2px)";
        d.style.boxShadow = "10px 10px 30px rgba(139,92,246,0.16), -3px -3px 10px rgba(255,255,255,0.92), inset 0 1px 0 rgba(255,255,255,0.97)";
      }}
      onMouseLeave={(e) => {
        const d = e.currentTarget as HTMLDivElement;
        d.style.transform = "translateY(0)";
        d.style.boxShadow = "8px 8px 24px rgba(139,92,246,0.10), -2px -2px 8px rgba(255,255,255,0.88), inset 0 1px 0 rgba(255,255,255,0.97)";
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <h3
            style={{
              fontFamily: "var(--font-fredoka), 'Fredoka', sans-serif",
              fontWeight: 600,
              fontSize: 16,
              color: "var(--fg)",
              lineHeight: 1.25,
              marginBottom: 3,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {job.title}
          </h3>
          <p style={{ fontSize: 12, color: "var(--muted2)", margin: 0, fontWeight: 600 }}>
            {job.company} · {job.location}
          </p>
        </div>
        <span
          style={{
            background: st.bg,
            color: st.color,
            border: `2px solid ${st.border}`,
            borderRadius: 20,
            fontSize: 11,
            fontWeight: 700,
            padding: "3px 10px",
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}
        >
          {STATUS_LABELS[job.status] || job.status}
        </span>
      </div>

      {/* Salary */}
      <div
        style={{
          fontSize: 15,
          fontWeight: 800,
          background: "linear-gradient(135deg, #8B5CF6, #3B82F6)",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
        }}
      >
        {job.salary}
      </div>

      {/* Greeting */}
      {job.greeting_message && (
        <div
          style={{
            background: "rgba(139,92,246,0.05)",
            border: "2px solid rgba(139,92,246,0.14)",
            borderRadius: 14,
            padding: "10px 12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "#8B5CF6" }}>打招呼草稿</span>
            {!editing && (
              <button
                onClick={() => setEditing(true)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--muted2)",
                  fontSize: 11,
                  display: "flex",
                  alignItems: "center",
                  gap: 3,
                  cursor: "pointer",
                  padding: 0,
                  transition: "color 0.15s",
                  fontFamily: "inherit",
                }}
                onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "#8B5CF6")}
                onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.color = "var(--muted2)")}
              >
                <PencilIcon size={11} /> 编辑
              </button>
            )}
          </div>
          {editing ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <textarea
                value={greeting}
                onChange={(e) => setGreeting(e.target.value)}
                style={{
                  fontSize: 12,
                  width: "100%",
                  border: "2px solid rgba(139,92,246,0.18)",
                  borderRadius: 10,
                  padding: "8px 10px",
                  resize: "vertical",
                  minHeight: 76,
                  outline: "none",
                  background: "rgba(255,255,255,0.95)",
                  color: "var(--fg)",
                  fontFamily: "var(--font-nunito), 'Nunito', sans-serif",
                  fontWeight: 500,
                }}
                onFocus={(e) => ((e.target as HTMLTextAreaElement).style.borderColor = "rgba(139,92,246,0.45)")}
                onBlur={(e) => ((e.target as HTMLTextAreaElement).style.borderColor = "rgba(139,92,246,0.18)")}
              />
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={async () => { await updateGreeting(job.id, greeting); setEditing(false); }}
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    background: "linear-gradient(135deg, #A78BFA, #8B5CF6)",
                    color: "white",
                    border: "2px solid rgba(255,255,255,0.4)",
                    borderRadius: 10,
                    padding: "6px 14px",
                    cursor: "pointer",
                    boxShadow: "3px 3px 8px rgba(139,92,246,0.28)",
                    transition: "transform 0.15s",
                    fontFamily: "var(--font-nunito), 'Nunito', sans-serif",
                  }}
                  onMouseDown={(e) => ((e.currentTarget as HTMLButtonElement).style.transform = "scale(0.94)")}
                  onMouseUp={(e) => ((e.currentTarget as HTMLButtonElement).style.transform = "scale(1)")}
                >
                  保存
                </button>
                <button
                  onClick={() => { setEditing(false); setGreeting(job.greeting_message || ""); }}
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    background: "none",
                    border: "none",
                    color: "var(--muted2)",
                    cursor: "pointer",
                    padding: "6px 10px",
                    fontFamily: "var(--font-nunito), 'Nunito', sans-serif",
                  }}
                >
                  取消
                </button>
              </div>
            </div>
          ) : (
            <p
              style={{
                fontSize: 12,
                color: "var(--muted)",
                lineHeight: 1.6,
                margin: 0,
                display: "-webkit-box",
                WebkitLineClamp: 3,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              } as React.CSSProperties}
            >
              {greeting}
            </p>
          )}
        </div>
      )}

      {/* Action buttons */}
      {(job.status === "matched" || job.status === "pending") && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingTop: 10,
            borderTop: "2px solid rgba(139,92,246,0.08)",
          }}
        >
          <a
            href={job.boss_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: 11,
              color: "var(--muted2)",
              display: "flex",
              alignItems: "center",
              gap: 4,
              textDecoration: "none",
              fontWeight: 600,
              transition: "color 0.15s",
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.color = "#8B5CF6")}
            onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.color = "var(--muted2)")}
          >
            <ExternalLinkIcon size={12} /> 查看原帖
          </a>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleSkip}
              disabled={loading}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                padding: "7px 14px",
                fontSize: 12,
                fontWeight: 700,
                color: "var(--muted)",
                background: "rgba(255,255,255,0.9)",
                border: "2px solid rgba(152,152,184,0.24)",
                borderRadius: 12,
                cursor: "pointer",
                boxShadow: "2px 2px 6px rgba(139,92,246,0.07)",
                opacity: loading ? 0.5 : 1,
                transition: "transform 0.15s",
                fontFamily: "var(--font-nunito), 'Nunito', sans-serif",
              }}
              onMouseDown={(e) => ((e.currentTarget as HTMLButtonElement).style.transform = "scale(0.94)")}
              onMouseUp={(e) => ((e.currentTarget as HTMLButtonElement).style.transform = "scale(1)")}
            >
              <XIcon size={13} /> 跳过
            </button>
            <button
              onClick={handleApprove}
              disabled={loading || !job.greeting_message}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                padding: "7px 14px",
                fontSize: 12,
                fontWeight: 700,
                color: "white",
                background: "linear-gradient(135deg, #34D399, #10B981)",
                border: "2px solid rgba(255,255,255,0.4)",
                borderRadius: 12,
                cursor: "pointer",
                boxShadow: "3px 3px 10px rgba(16,185,129,0.30)",
                opacity: loading || !job.greeting_message ? 0.5 : 1,
                transition: "transform 0.15s",
                fontFamily: "var(--font-nunito), 'Nunito', sans-serif",
              }}
              onMouseDown={(e) => ((e.currentTarget as HTMLButtonElement).style.transform = "scale(0.94)")}
              onMouseUp={(e) => ((e.currentTarget as HTMLButtonElement).style.transform = "scale(1)")}
            >
              <CheckIcon size={13} /> 批准投递
            </button>
          </div>
        </div>
      )}

      {/* Approved state */}
      {job.status === "approved" && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            fontSize: 12,
            fontWeight: 700,
            color: "#3B82F6",
            background: "rgba(59,130,246,0.08)",
            border: "2px solid rgba(59,130,246,0.22)",
            borderRadius: 12,
            padding: "8px 14px",
          }}
        >
          <CheckIcon size={14} />
          已加入投递队列，等待批量发送
        </div>
      )}

      <div style={{ fontSize: 11, color: "var(--muted2)", textAlign: "right", marginTop: -4, fontWeight: 600 }}>
        {formatDate(job.scraped_at)}
      </div>
    </div>
  );
}
