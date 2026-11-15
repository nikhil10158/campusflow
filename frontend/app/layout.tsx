import type { Metadata } from "next";
import { DM_Sans } from "next/font/google";

import { Providers } from "@/components/Providers";

import "./globals.css";

const dmSans = DM_Sans({ variable: "--font-dm-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CampusFlow",
  description: "Find and book campus rooms, labs, guest rooms and parking. Synthetic demo data.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${dmSans.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
