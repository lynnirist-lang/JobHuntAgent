import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn/ui 标准工具：合并 Tailwind class names，处理冲突。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 将匹配分映射为颜色类名（规格：≥80 绿 / 60-79 黄 / <60 红）。 */
export function scoreColor(score: number | null): string {
  if (score === null || score === undefined) return "text-gray-400";
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-yellow-600";
  return "text-red-500";
}

/** 将匹配分映射为背景 Badge 颜色。 */
export function scoreBadgeClass(score: number | null): string {
  if (score === null || score === undefined) return "bg-gray-100 text-gray-600";
  if (score >= 80) return "bg-green-100 text-green-700";
  if (score >= 60) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-600";
}

/** 投递状态文字映射。 */
export const STATUS_LABELS: Record<string, string> = {
  pending: "待处理",
  matched: "已匹配",
  approved: "已批准",
  skipped: "已跳过",
  sent: "已投递",
  read: "已读",
  replied: "有回复",
  low_priority: "低优先级",
  failed: "投递失败",
};

/** 格式化 ISO 时间为本地时间字符串。 */
export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
