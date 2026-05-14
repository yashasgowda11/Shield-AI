import type { Metadata } from "next";
import "./globals.css";
import LayoutShell from "@/components/layout/LayoutShell";

export const metadata: Metadata = {
  title: "Shield AI",
  description: "Multi-agent AI platform for enterprise contract review",
  icons: {
    icon: [{ url: "/shield-ai-icon.svg", type: "image/svg+xml" }],
    apple: "/shield-ai-icon.svg",
    shortcut: "/shield-ai-icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full flex" style={{ background: "var(--bg-base)" }}>
        <LayoutShell>{children}</LayoutShell>
      </body>
    </html>
  );
}
