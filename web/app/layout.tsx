import type { Metadata, Viewport } from "next";
import "./globals.css";
import { PwaRegister } from "./components/pwa-register";
import { ErrorBoundary } from "./components/error-boundary";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: { default: "AIMusicMed", template: "%s · AIMusicMed" },
  description: "音乐冥想，是陪伴情绪的一剂温柔良方。听见此刻，慢慢抵达想去的情绪。",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "AIMusicMed" },
  openGraph: {
    type: "website",
    locale: "zh_CN",
    url: "/",
    siteName: "AIMusicMed",
    title: "AIMusicMed · 为此刻的你生成音乐冥想",
    description: "音乐冥想，是陪伴情绪的一剂温柔良方。听见此刻，慢慢抵达想去的情绪。",
    images: [{ url: "/og.png", alt: "AIMusicMed 音乐冥想" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "AIMusicMed · 为此刻的你生成音乐冥想",
    description: "音乐冥想，是陪伴情绪的一剂温柔良方。听见此刻，慢慢抵达想去的情绪。",
    images: ["/og.png"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6f1" },
    { media: "(prefers-color-scheme: dark)", color: "#102825" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: `try{const t=localStorage.getItem('aim-theme');if(t==='dark'||(t!=='light'&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.dataset.theme='dark'}catch{}` }} />
        <ErrorBoundary>{children}</ErrorBoundary>
        <PwaRegister />
      </body>
    </html>
  );
}
