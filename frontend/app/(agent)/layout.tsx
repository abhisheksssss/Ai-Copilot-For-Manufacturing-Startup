"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Factory, LogOut, Loader2, ClipboardCheck, MessageSquare, Menu, ChevronLeft, Cpu } from "lucide-react";

import { useAuthStore } from "@/store/use-auth-store";

export default function AgentsLayout({ children }: { children: React.ReactNode }) {
  const { token, user, isReady, initializeAuth, logout } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  useEffect(() => {
    if (isReady && !token) {
      router.replace("/login");
    }
  }, [isReady, token, router]);

  if (!isReady || !token) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#F8F7F4]">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-900">
            <Factory className="h-5 w-5 text-white" />
          </div>
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading workspace
          </div>
        </div>
      </div>
    );
  }

  const navItems = [
    { name: "Business Planner", href: "/planner", icon: ClipboardCheck },
    { name: "Agent Chat", href: "/chat", icon: MessageSquare },
    { name: "Factory Digital Twin", href: "/digital-twin", icon: Cpu },
  ];

  return (
    <div className="flex min-h-screen bg-[#F8F7F4] text-zinc-900 antialiased overflow-hidden">
      {/* ── Sidebar ── */}
      <aside
        className={`relative z-50 flex shrink-0 flex-col border-r border-zinc-200 bg-white transition-all duration-300 ${
          sidebarOpen ? "w-64" : "w-0 overflow-hidden border-none"
        }`}
      >
        <div className="flex h-14 items-center gap-2.5 border-b border-zinc-200 px-4 shrink-0 whitespace-nowrap">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-900">
            <Factory className="h-4 w-4 text-white shrink-0" />
          </div>
          <span className="truncate text-sm font-semibold tracking-tight text-zinc-900">
            Manufacturing Copilot
          </span>
        </div>

        <nav className="flex-1 space-y-1 p-3 whitespace-nowrap">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                pathname === item.href
                  ? "bg-zinc-100 text-zinc-900"
                  : "text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900"
              }`}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{item.name}</span>
            </Link>
          ))}
        </nav>

        <div className="border-t border-zinc-200 p-3 shrink-0 whitespace-nowrap">
          <div className="mb-2 flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2 text-sm">
            <span className="truncate font-medium text-zinc-700">{user?.email ?? "—"}</span>
          </div>
          <button
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition-colors"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            Sign out
          </button>
        </div>
      </aside>

      {/* ── Main Content Area ── */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Header */}
        <header className="flex h-14 shrink-0 items-center gap-4 border-b border-zinc-200 bg-white/90 px-4 backdrop-blur-sm">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
            aria-label="Toggle Sidebar"
          >
            {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
          
          <div className="flex flex-1 items-baseline gap-2">
            {!sidebarOpen && (
              <span className="text-sm font-semibold tracking-tight">Manufacturing Copilot</span>
            )}
            <span className="hidden text-xs text-zinc-400 sm:inline">AI planning for Indian MSMEs</span>
          </div>
        </header>

        {/* Scrollable Page Content */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
