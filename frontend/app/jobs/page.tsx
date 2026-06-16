/**
 * 岗位列表页 — 全量浏览 + 筛选 + JD 适配简历
 */

"use client";

import { useEffect, useState } from "react";
import {
  getJobs,
  Job,
  approveJob,
  skipJob,
  batchApply,
  adaptResume,
  AdaptedResume,
  AdaptedExperience,
  AdaptedProject,
} from "@/lib/api";
import { STATUS_LABELS, formatDate } from "@/lib/utils";
import { ExternalLinkIcon, ChevronDownIcon, ChevronUpIcon, SparklesIcon } from "lucide-react";

const STATUS_FILTERS = [
  { value: "", label: "全部" },
  { value: "matched", label: "待审核" },
  { value: "approved", label: "已批准" },
  { value: "sent", label: "已投递" },
  { value: "skipped", label: "已跳过" },
];

function statusBadge(status: string): { bg: string; color: string } {
  const map: Record<string, { bg: string; color: string }> = {
    matched:      { bg: "rgba(139,92,246,0.10)",  color: "#8B5CF6" },
    pending:      { bg: "rgba(59,130,246,0.10)",  color: "#3B82F6" },
    approved:     { bg: "rgba(59,130,246,0.10)",  color: "#3B82F6" },
    sent:         { bg: "rgba(16,185,129,0.10)",  color: "#10B981" },
    low_priority: { bg: "rgba(152,152,184,0.12)", color: "#9898B8" },
    skipped:      { bg: "rgba(152,152,184,0.12)", color: "#9898B8" },
    failed:       { bg: "rgba(244,63,94,0.10)",   color: "#F43F5E" },
  };
  return map[status] ?? { bg: "rgba(152,152,184,0.12)", color: "#9898B8" };
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // 适配简历状态：jobId → { loading, result, error }
  const [adaptState, setAdaptState] = useState<
    Record<number, { loading: boolean; result: AdaptedResume | null; error: string | null }>
  >({});

  const fetchJobs = async () => {
    setLoading(true);
    try {
      const res = await getJobs({
        status: statusFilter || undefined,
        limit: 200,
      });
      setJobs(res.items);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJobs();
  }, [statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleApprove = async (jobId: number) => {
    await approveJob(jobId);
    fetchJobs();
    // 批准后立即触发投递（只投递这一个岗位）
    try {
      await batchApply([jobId]);
    } catch {
      // 投递任务已在运行时会返回 409，忽略即可
    }
  };

  const handleSkip = async (jobId: number) => {
    await skipJob(jobId);
    fetchJobs();
  };

  const handleAdapt = async (job: Job) => {
    setAdaptState((prev) => ({
      ...prev,
      [job.id]: { loading: true, result: null, error: null },
    }));
    try {
      const result = await adaptResume(job.id);
      setAdaptState((prev) => ({
        ...prev,
        [job.id]: { loading: false, result, error: null },
      }));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "适配失败，请重试";
      setAdaptState((prev) => ({
        ...prev,
        [job.id]: { loading: false, result: null, error: msg },
      }));
    }
  };

  return (
    <div className="space-y-4">
      {/* ── 筛选栏 ──────────────────────────────────────────── */}
      <div className="bg-white rounded-xl p-4 flex flex-wrap gap-3 items-center" style={{ border: "3px solid rgba(255,255,255,0.92)", boxShadow: "8px 8px 22px rgba(139,92,246,0.09), -2px -2px 7px rgba(255,255,255,0.88)" }}>
        <div className="flex gap-2 flex-wrap">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className="px-3 py-1.5 text-sm rounded-xl border font-bold transition-none"
              style={statusFilter === f.value
                ? { background: "#8B5CF6", color: "#fff", borderColor: "rgba(139,92,246,0.40)", boxShadow: "0 4px 12px rgba(139,92,246,0.28)" }
                : { background: "transparent", color: "#5B5B7A", borderColor: "rgba(139,92,246,0.20)" }
              }
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 统计 ────────────────────────────────────────────── */}
      <p className="text-sm text-gray-500">
        共 <span className="font-medium text-gray-800">{jobs.length}</span> 个岗位
      </p>

      {/* ── 岗位表格 ────────────────────────────────────────── */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">加载中…</div>
      ) : (
        <div className="bg-white rounded-xl border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">岗位</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">公司</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">薪资</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">状态</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">时间</th>
                <th className="text-center px-4 py-3 font-medium text-gray-600">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {jobs.map((job) => {
                const adapt = adaptState[job.id];
                return (
                  <>
                    <tr
                      key={job.id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() =>
                        setExpandedId(expandedId === job.id ? null : job.id)
                      }
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900">{job.title}</div>
                        <div className="text-xs text-gray-400">{job.location}</div>
                      </td>
                      <td className="px-4 py-3 text-gray-700">{job.company}</td>
                      <td className="px-4 py-3 font-bold" style={{ color: "#3B82F6" }}>{job.salary || "—"}</td>
                      <td className="px-4 py-3 text-center">
                        <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: statusBadge(job.status).bg, color: statusBadge(job.status).color }}>
                          {STATUS_LABELS[job.status] || job.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 text-xs">
                        {formatDate(job.scraped_at)}
                      </td>
                      <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-center gap-2">
                          <a
                            href={job.boss_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-gray-400 hover:text-blue-500"
                          >
                            <ExternalLinkIcon className="w-4 h-4" />
                          </a>
                          {job.status === "matched" && (
                            <>
                              <button
                                onClick={() => handleApprove(job.id)}
                                className="text-xs px-2 py-1 font-bold rounded-lg transition-none"
                                style={{ background: "#10B981", color: "#fff", boxShadow: "0 3px 8px rgba(16,185,129,0.25)" }}
                              >
                                批准
                              </button>
                              <button
                                onClick={() => handleSkip(job.id)}
                                className="text-xs px-2 py-1 rounded"
                                style={{ color: "#9898B8", border: "1px solid rgba(152,152,184,0.30)" }}
                              >
                                跳过
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>

                    {/* 展开行 */}
                    {expandedId === job.id && (
                      <tr key={`${job.id}-expand`} style={{ background: "rgba(139,92,246,0.03)" }}>
                        <td colSpan={6} className="px-6 py-5">
                          <div className="space-y-4 text-sm">
                            {/* 岗位描述 */}
                            {(job.description || job.requirements) && (
                              <div>
                                <div className="font-medium text-gray-700 mb-1">岗位描述</div>
                                <pre
                                  className="text-gray-600 leading-relaxed bg-white border border-gray-100 rounded-lg px-3 py-2 whitespace-pre-wrap"
                                  style={{ fontFamily: "inherit", fontSize: 12, maxHeight: 240, overflowY: "auto" }}
                                >
                                  {job.description || job.requirements}
                                </pre>
                              </div>
                            )}

                            {/* 打招呼草稿 */}
                            {job.greeting_message && (
                              <div>
                                <div className="font-medium text-gray-700 mb-1">打招呼草稿</div>
                                <p className="text-gray-600 leading-relaxed bg-white border border-gray-100 rounded-lg px-3 py-2">
                                  {job.greeting_message}
                                </p>
                              </div>
                            )}

                            {/* 适配简历区域 */}
                            <div>
                              <div className="flex items-center gap-3 mb-3">
                                <div className="font-medium text-gray-700">JD 简历适配</div>
                                {(job.status === "matched" || job.status === "approved") && (
                                  <button
                                    onClick={() => handleAdapt(job)}
                                    disabled={adapt?.loading}
                                    className="flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-xl disabled:opacity-50"
                                    style={{ background: "#8B5CF6", color: "#fff", border: "none", boxShadow: "0 4px 12px rgba(139,92,246,0.30)" }}
                                  >
                                    <SparklesIcon className="w-3.5 h-3.5" />
                                    {adapt?.loading ? "生成中…" : adapt?.result ? "重新生成" : "适配简历"}
                                  </button>
                                )}
                              </div>

                              {adapt?.error && (
                                <p className="text-xs text-red-500 mb-2">{adapt.error}</p>
                              )}

                              {adapt?.result && (
                                <AdaptedResumePanel result={adapt.result} />
                              )}

                              {!adapt && (
                                <p className="text-xs text-gray-400">
                                  点击「适配简历」，AI 将根据此岗位 JD 对你的经历措辞进行针对性调整（不编造内容）。
                                </p>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
          {jobs.length === 0 && (
            <div className="text-center py-12 text-gray-400">没有符合条件的岗位</div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── 适配简历对比面板 ──────────────────────────────────────────── */

function AdaptedResumePanel({ result }: { result: AdaptedResume }) {
  return (
    <div className="space-y-4">
      {result.experiences.map((exp, i) => (
        <ExperienceBlock key={i} exp={exp} />
      ))}
      {result.projects.map((proj, i) => (
        <ProjectBlock key={i} proj={proj} />
      ))}
    </div>
  );
}

function ExperienceBlock({ exp }: { exp: AdaptedExperience }) {
  return (
    <div className="bg-white rounded-lg p-4" style={{ border: "2px solid rgba(139,92,246,0.12)" }}>
      <div className="flex items-center gap-2 mb-2">
        <span className="font-semibold" style={{ color: "#1A1A2E" }}>{exp.company}</span>
        <span style={{ color: "#9898B8" }}>·</span>
        <span style={{ color: "#5B5B7A" }}>{exp.role}</span>
        <span className="ml-auto text-xs" style={{ color: "#9898B8" }}>{exp.duration}</span>
      </div>
      <ul className="space-y-1.5">
        {exp.bullets.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-xs" style={{ color: "#1A1A2E" }}>
            <span className="mt-1 w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "#8B5CF6" }} />
            {b}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProjectBlock({ proj }: { proj: AdaptedProject }) {
  return (
    <div className="bg-white rounded-lg p-4" style={{ border: "2px solid rgba(59,130,246,0.12)" }}>
      <div className="flex items-center gap-2 mb-1">
        <span className="font-semibold" style={{ color: "#1A1A2E" }}>{proj.name}</span>
        {proj.github && (
          <a
            href={proj.github}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs hover:underline ml-auto"
            style={{ color: "#3B82F6" }}
          >
            GitHub
          </a>
        )}
      </div>
      <p className="text-xs mb-2" style={{ color: "#9898B8" }}>{proj.tech}</p>
      <ul className="space-y-1.5">
        {proj.highlights.map((h, i) => (
          <li key={i} className="flex items-start gap-2 text-xs" style={{ color: "#1A1A2E" }}>
            <span className="mt-1 w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "#3B82F6" }} />
            {h}
          </li>
        ))}
      </ul>
    </div>
  );
}
