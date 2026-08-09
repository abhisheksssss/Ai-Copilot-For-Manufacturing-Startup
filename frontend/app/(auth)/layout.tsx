import { BadgeIndianRupee, Building2, ClipboardCheck, Search, Zap } from "lucide-react";
import React from "react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto grid min-h-[calc(100vh-56px)] max-w-screen-xl items-center gap-12 px-4 py-12 lg:grid-cols-[1fr_400px]">
      <div className="max-w-xl">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
          <Zap className="h-3.5 w-3.5" />
          Multi-agent AI planner
        </div>
        <h2 className="text-4xl font-bold leading-tight tracking-tight text-zinc-900 sm:text-5xl">
          Build your MSME business plan in minutes
        </h2>
        <p className="mt-4 text-base leading-relaxed text-zinc-500">
          Create an account to access the AI planning workspace. Our agents research government schemes, factory requirements, supplier markets, and business strategy — all in one session.
        </p>
        <div className="mt-8 flex flex-wrap gap-4">
          {[
            { icon: ClipboardCheck, label: "Business strategy" },
            { icon: Building2, label: "Factory layout" },
            { icon: BadgeIndianRupee, label: "MSME subsidies" },
            { icon: Search, label: "Market research" },
          ].map(({ icon: Icon, label }) => (
            <div key={label} className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs font-medium text-zinc-600 shadow-sm">
              <Icon className="h-3.5 w-3.5 text-zinc-400" />
              {label}
            </div>
          ))}
        </div>
      </div>
      {children}
    </div>
  );
}
