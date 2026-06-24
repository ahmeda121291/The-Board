import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Boardroom",
  description: "Autonomous capital allocator — live dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
