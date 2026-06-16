import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/sidebar";
import { Fredoka, Nunito } from "next/font/google";

const fredoka = Fredoka({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-fredoka",
  display: "swap",
});
const nunito = Nunito({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-nunito",
  display: "swap",
});

export const metadata: Metadata = {
  title: "求职助手",
  description: "自动化 BOSS 直聘投递助手",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${fredoka.variable} ${nunito.variable}`}>
      <body>
        <Sidebar />
        <div style={{ marginLeft: "var(--sidebar-w)", minHeight: "100vh" }}>
          {children}
        </div>
      </body>
    </html>
  );
}
