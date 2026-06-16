"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { BriefcaseIcon, LayoutDashboardIcon, SendIcon, RocketIcon, BotIcon } from "lucide-react";

const links = [
  {
    href: "/",
    label: "仪表板",
    icon: LayoutDashboardIcon,
    activeGradient: "from-violet-500 to-purple-600",
    activeShadow: "shadow-violet-200",
  },
  {
    href: "/jobs",
    label: "岗位列表",
    icon: BriefcaseIcon,
    activeGradient: "from-pink-500 to-rose-500",
    activeShadow: "shadow-pink-200",
  },
  {
    href: "/apply",
    label: "投递记录",
    icon: SendIcon,
    activeGradient: "from-cyan-400 to-blue-500",
    activeShadow: "shadow-cyan-200",
  },
  {
    href: "/chat",
    label: "AI 助手",
    icon: BotIcon,
    activeGradient: "from-emerald-500 to-teal-500",
    activeShadow: "shadow-emerald-200",
  },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <header
      className="sticky top-0 z-50 border-b border-purple-100/70 shadow-sm shadow-purple-50/80"
      style={{
        background: "rgba(255,255,255,0.88)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
      }}
    >
      <div className="max-w-7xl mx-auto px-4 h-16 flex items-center gap-2">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 mr-6 group shrink-0">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-pink-500 flex items-center justify-center shadow-md shadow-violet-200 transition-all duration-200 group-hover:shadow-violet-300 group-hover:scale-110">
            <RocketIcon className="w-5 h-5 text-white" />
          </div>
          <span
            className="font-black text-xl text-gradient"
            style={{ fontFamily: "var(--font-nunito, Nunito, sans-serif)" }}
          >
            求职助手
          </span>
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-1">
          {links.map(({ href, label, icon: Icon, activeGradient, activeShadow }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 text-sm font-semibold px-4 py-2 rounded-xl transition-all duration-200 cursor-pointer",
                  active
                    ? `bg-gradient-to-r ${activeGradient} text-white shadow-md ${activeShadow}`
                    : "text-gray-500 hover:text-gray-900 hover:bg-purple-50 hover:scale-105"
                )}
                style={{ fontFamily: "var(--font-nunito, Nunito, sans-serif)" }}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
