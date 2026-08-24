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

const siteOrigin = new URL("https://fv-treasury-auctions.no1-trader-kang.chatgpt.site");
const title = "FV Terminal — U.S. Treasury Auctions";
const description = "A modern primary-market terminal for U.S. Treasury auction schedules, compact prior results, demand signals, and data architecture.";

export const metadata: Metadata = {
  metadataBase: siteOrigin,
  title,
  description,
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
  openGraph: { title, description, images: [{ url: "/og.png", width: 1200, height: 630, alt: "FV Terminal U.S. Treasury Auctions" }] },
  twitter: { card: "summary_large_image", title, description, images: ["/og.png"] },
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
