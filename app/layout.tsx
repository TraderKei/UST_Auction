import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const title = "UST AUCTION — 미국 국채 입찰";
const description = "미국 국채 입찰 결과와 예정 일정, 응찰률 및 참여자별 낙찰 비중을 확인하는 다크 대시보드입니다.";

export const metadata: Metadata = {
  title,
  description,
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: { title, description },
  twitter: { card: "summary", title, description },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
