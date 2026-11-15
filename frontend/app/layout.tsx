import type { Metadata } from "next";
import { Barlow, Barlow_Condensed, Chivo_Mono } from "next/font/google";

import { Providers } from "@/components/Providers";

import "./globals.css";

const barlow = Barlow({ variable: "--font-barlow", subsets: ["latin"], weight: ["400", "500", "600"] });
const barlowCondensed = Barlow_Condensed({ variable: "--font-barlow-condensed", subsets: ["latin"], weight: ["500", "600", "700"] });
const chivoMono = Chivo_Mono({ variable: "--font-chivo-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "CampusFlow",
  description: "Agentic campus space planner: free rooms, bookings, guest house and parking. Synthetic demo data.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${barlow.variable} ${barlowCondensed.variable} ${chivoMono.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
