"use client";

import Link from "next/link";
import { Factory, ArrowRight, Zap, Building2, Search, ClipboardCheck, BadgeIndianRupee } from "lucide-react";
import { useAuthStore } from "@/store/use-auth-store";
import { useEffect } from "react";

export default function LandingPage() {
  const { initializeAuth, token } = useAuthStore();

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  return (
    <div className="flex min-h-screen flex-col bg-[#F8F7F4] text-zinc-900 antialiased">
      {/* ── Header ── */}
      <header className="sticky top-0 z-40 border-b border-zinc-200 bg-white/90 px-4 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-screen-xl items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-900">
              <Factory className="h-4 w-4 text-white" />
            </div>
            <span className="text-sm font-bold tracking-tight">Manufacturing Copilot</span>
          </div>
          
          <div className="flex items-center gap-3">
            {token ? (
              <Link
                href="/planner"
                className="flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
              >
                Go to App
                <ArrowRight className="h-4 w-4" />
              </Link>
            ) : (
              <>
                <Link href="/login" className="text-sm font-medium text-zinc-600 hover:text-zinc-900 transition">
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
                >
                  Get Started
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── Hero Section ── */}
      <main className="flex-1">
        <div className="mx-auto max-w-screen-xl px-4 py-24 sm:py-32">
          <div className="mx-auto max-w-2xl text-center">
            <div className="mb-8 inline-flex items-center gap-2 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
              <Zap className="h-3.5 w-3.5" />
              Multi-agent AI planner for MSMEs
            </div>
            
            <h1 className="text-5xl font-extrabold leading-tight tracking-tight text-zinc-900 sm:text-6xl">
              Build your factory plan in minutes
            </h1>
            
            <p className="mx-auto mt-6 max-w-xl text-lg leading-relaxed text-zinc-500">
              This is where we will tell you about our project, what we are providing, and how that will help others. We will implement the full landing page later!
            </p>
            
            <div className="mt-10 flex items-center justify-center gap-4">
              <Link
                href={token ? "/planner" : "/signup"}
                className="flex items-center gap-2 rounded-lg bg-zinc-900 px-6 py-3.5 text-sm font-semibold text-white shadow-sm transition hover:bg-zinc-800"
              >
                Launch Copilot
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
          
          <div className="mx-auto mt-16 max-w-3xl grid grid-cols-2 gap-4 sm:grid-cols-4">
             {[
                { icon: ClipboardCheck, label: "Business strategy" },
                { icon: Building2, label: "Factory layout" },
                { icon: BadgeIndianRupee, label: "MSME subsidies" },
                { icon: Search, label: "Market research" },
              ].map(({ icon: Icon, label }) => (
                <div key={label} className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
                  <Icon className="h-6 w-6 text-zinc-400" />
                  <span className="text-xs font-medium text-zinc-600">{label}</span>
                </div>
              ))}
          </div>
        </div>
      </main>
    </div>
  );
}
