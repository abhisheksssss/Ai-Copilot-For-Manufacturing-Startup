"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { Factory, LogOut, Loader2, ClipboardCheck, MessageSquare, Menu, ChevronLeft, Cpu, ShieldCheck, User, ChevronDown, MapPinned } from "lucide-react";

import { useAuthStore } from "@/store/use-auth-store";

export default function AgentsLayout({ children }: { children: React.ReactNode }) {
  const { token, user, isReady, initializeAuth, logout } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    if (userMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [userMenuOpen]);

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
    { name: "Location Finder", href: "/locations", icon: MapPinned },
    { name: "ESG & Compliance", href: "/compliance", icon: ShieldCheck },
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
        <header className="relative flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 bg-white/90 px-4 backdrop-blur-sm z-30">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 transition-colors"
              aria-label="Toggle Sidebar"
            >
              {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
            
            <div className="flex items-baseline gap-2">
              {!sidebarOpen && (
                <span className="text-sm font-semibold tracking-tight text-zinc-900">Manufacturing Copilot</span>
              )}
              <span className="hidden text-xs text-zinc-400 sm:inline">AI planning for Indian MSMEs</span>
            </div>
          </div>

          {/* User Profile Popover / Dropdown on Right Side */}
          <div className="relative" ref={userMenuRef}>
            <button
              onClick={() => setUserMenuOpen((prev) => !prev)}
              className="flex items-center gap-2 rounded-full border border-zinc-200 bg-zinc-50 py-1 pl-1 pr-2.5 text-xs font-medium text-zinc-700 transition hover:bg-zinc-100 hover:border-zinc-300 focus:outline-none focus:ring-2 focus:ring-zinc-900/10 shadow-xs"
              aria-label="User Account Information"
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-zinc-900 text-white shadow-xs">
                <User className="h-3.5 w-3.5" />
              </div>
              <span className="hidden max-w-[140px] truncate sm:inline font-medium text-zinc-800">
                {user?.email?.split("@")[0] ?? "Account"}
              </span>
              <ChevronDown className={`h-3.5 w-3.5 text-zinc-400 transition-transform duration-200 ${userMenuOpen ? "rotate-180" : ""}`} />
            </button>

            {userMenuOpen && (
              <div className="absolute right-0 mt-2 w-72 rounded-xl border border-zinc-200 bg-white p-4 shadow-xl z-50">
                <div className="mb-3 flex items-center gap-2.5 border-b border-zinc-100 pb-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-zinc-900 text-white shadow-xs">
                    <User className="h-4 w-4" />
                  </div>
                  <div className="overflow-hidden">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                      Your Account Information
                    </p>
                    <p className="truncate text-xs font-semibold text-zinc-900" title={user?.email ?? ""}>
                      {user?.email ?? "—"}
                    </p>
                  </div>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2">
                    <span className="text-zinc-500">Email</span>
                    <span className="max-w-[150px] truncate font-medium text-zinc-800">{user?.email ?? "—"}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2">
                    <span className="text-zinc-500">Role</span>
                    <span className="font-semibold capitalize text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      {user?.role ?? "user"}
                    </span>
                  </div>
                </div>

                <div className="mt-3 pt-3 border-t border-zinc-100">
                  <button
                    onClick={() => {
                      setUserMenuOpen(false);
                      logout();
                    }}
                    className="flex w-full items-center justify-center gap-2 rounded-lg bg-zinc-100 px-3 py-2 text-xs font-medium text-zinc-700 hover:bg-rose-50 hover:text-rose-700 transition-colors"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    Sign out
                  </button>
                </div>
              </div>
            )}
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
