/**
 * API 客户端。
 *
 * 所有请求通过 Next.js rewrites 代理到后端（/api/* → localhost:8080/*），
 * 无需在前端硬编码后端地址。
 */

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} 返回 ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── 岗位 API ─────────────────────────────────────────────────────

export interface Job {
  id: number;
  boss_job_id: string;
  title: string;
  company: string;
  salary: string;
  location: string;
  description: string;
  requirements: string;
  boss_url: string;
  status: string;
  greeting_message: string | null;
  scraped_at: string;
  updated_at: string;
}

export interface JobListResponse {
  items: Job[];
  count: number;
}

/** 工作经历（适配结果用） */
export interface AdaptedExperience {
  company: string;
  role: string;
  duration: string;
  bullets: string[];
}

/** 项目（适配结果用） */
export interface AdaptedProject {
  name: string;
  tech: string;
  github: string;
  highlights: string[];
}

export interface AdaptedResume {
  experiences: AdaptedExperience[];
  projects: AdaptedProject[];
}

/** 获取岗位列表，可按状态筛选。 */
export const getJobs = (params?: {
  status?: string;
  limit?: number;
  offset?: number;
}) => {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const qs = q.toString() ? `?${q}` : "";
  return request<JobListResponse>(`/jobs${qs}`);
};

/** 批准岗位（加入待投递队列）。 */
export const approveJob = (jobId: number) =>
  request(`/jobs/${jobId}/approve`, { method: "POST" });

/** 跳过岗位。 */
export const skipJob = (jobId: number) =>
  request(`/jobs/${jobId}/skip`, { method: "POST" });

/** 更新岗位打招呼语。 */
export const updateGreeting = (jobId: number, message: string) =>
  request(`/jobs/${jobId}/greeting`, {
    method: "PATCH",
    body: JSON.stringify({ message }),
  });

/** 触发爬取任务。 */
export const triggerScrape = (params?: {
  keywords?: string[];
  city?: string;
  salary_code?: string;
  max_pages?: number;
}) =>
  request("/jobs/scrape", {
    method: "POST",
    body: JSON.stringify(params || {}),
  });

/** 为 PENDING 状态且无打招呼语的岗位重新触发生成（无需重新爬取）。 */
export const retryGreetings = () =>
  request("/jobs/retry-greetings", { method: "POST" });

/** 查询爬取任务状态。 */
export const getScrapeStatus = () =>
  request<{
    running: boolean;
    progress: string;
    total: number;
    errors: string[];
    stopped_reason: string | null;
  }>("/jobs/scrape/status");

/** 根据 JD 适配简历内容（仅预览，不写库）。 */
export const adaptResume = (jobId: number) =>
  request<AdaptedResume>(`/jobs/${jobId}/resume-adapt`, { method: "POST" });

// ── 投递 API ─────────────────────────────────────────────────────

export interface Application {
  id: number;
  job_id: number;
  job_title: string;
  company: string;
  status: string;
  greeting_message: string;
  sent_at: string | null;
  error_message: string | null;
  created_at: string;
}

export interface ApplicationListResponse {
  items: Application[];
  count: number;
}

/** 查询投递记录列表。 */
export const getApplications = (status?: string) => {
  const q = status ? `?status=${status}` : "";
  return request<ApplicationListResponse>(`/apply/status${q}`);
};

/** 触发批量投递。 */
export const batchApply = (jobIds?: number[]) =>
  request("/apply/batch", {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds || null }),
  });

/** 查询今日投递统计。 */
export const getTodayStats = () =>
  request<{ today_sent: number; total_sent: number; daily_limit: number; remaining: number }>(
    "/apply/today"
  );

/** 查询投递任务状态。 */
export const getApplyTaskStatus = () =>
  request<{
    running: boolean;
    progress: string;
    success_count: number;
    fail_count: number;
    total_jobs: number;
    stopped_reason: string | null;
    alert: string | null;
  }>("/apply/task-status");

// ── 登录 API ──────────────────────────────────────────────────────

export const triggerLogin = () =>
  request("/auth/login", { method: "POST" });

export const getLoginStatus = () =>
  request<{ logged_in: boolean; waiting_qr: boolean; message: string }>(
    "/auth/status"
  );

export const checkLogin = () =>
  request<{ logged_in: boolean; waiting_qr: boolean; message: string }>(
    "/auth/check", { method: "POST" }
  );

export const logout = () =>
  request("/auth/logout", { method: "POST" });

// ── 用户档案 API ──────────────────────────────────────────────────

export const getProfile = () => request("/profile");
export const updateProfile = (profile: unknown) =>
  request("/profile", { method: "PUT", body: JSON.stringify({ profile }) });

// ── 设置 API ──────────────────────────────────────────────────────

export interface SearchConfig {
  keywords: string[];
  city: string;
  salary_code: string;
}

export const getSettings = () =>
  request<{ search: SearchConfig; [key: string]: unknown }>("/settings");

export const updateSearchSettings = (search: Partial<SearchConfig>) =>
  request("/settings/search", {
    method: "PATCH",
    body: JSON.stringify(search),
  });
