import type { Metadata } from "next";

import AppToaster from "@/components/ui/AppToaster";

import "./globals.css";

export const metadata: Metadata = {
  title: "VieScanner – Trích xuất thông tin CCCD",
  description:
    "Hệ thống tự động trích xuất thông tin từ Căn cước công dân Việt Nam và xuất ra file Excel.",
  applicationName: "VieScanner",
  keywords: ["CCCD", "OCR", "Vietnam", "Excel", "trích xuất"],
  authors: [{ name: "VieScanner Team" }],
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        {children}
        <AppToaster />
      </body>
    </html>
  );
}
