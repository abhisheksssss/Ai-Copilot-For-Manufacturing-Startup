// app/layout.tsx
import type { Metadata } from "next";
import "./globals.css";
import { AppProviders } from "@/components/app-providers";
import { Toaster } from "@/components/ui/sonner";

export const metadata: Metadata = {
  title: "Manufacturing Copilot",
  description: "AI copilot for manufacturing startups and MSMEs",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AppProviders>
          {children}
          <Toaster richColors position="top-right" />
        </AppProviders>
      </body>
    </html>
  );
}