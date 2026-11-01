"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import { useAuthStore } from "@/store/use-auth-store";
import { useCopilotStore } from "@/store/use-copilot-store";
import {
  Factory,
  Loader2,
  Send,
  Zap,
  Users,
  BarChart3,
  AlertTriangle,
  CheckCircle2,
  TrendingUp,
  RefreshCw,
  IndianRupee,
  ChevronRight,
  ChevronLeft,
  Activity,
  Target,
  Cpu,
  Sparkles,
  Layers,
  X,
  ClipboardCheck,
  History,
  Clock,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import { FactoryErrorBoundary } from "./FactoryErrorBoundary";

import type {
  SceneZone,
  SceneDescriptor,
  FactoryCanvasProps,
} from "./FactoryCanvas";

const FactoryCanvas = dynamic<FactoryCanvasProps>(
  () => import("./FactoryCanvas"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center bg-[#060b16]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
          <p className="text-xs font-semibold text-cyan-400 tracking-widest uppercase">
            Initializing 3D Engine...
          </p>
        </div>
      </div>
    ),
  }
);

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────────

interface StepCapacity {
  step_name: string;
  sequence: number;
  capacity_per_day: number;
  utilization_percent: number;
  is_bottleneck: boolean;
  machine_count: number;
  workers: number;
}

interface SimulationResult {
  effective_throughput_per_day: number;
  effective_throughput_per_month: number;
  target_met: boolean;
  production_gap: number;
  bottleneck_step: string;
  bottleneck_capacity_per_day: number;
  step_capacities: StepCapacity[];
  total_workers: number;
  total_power_kw: number;
  estimated_monthly_power_cost_inr: number;
  optimization_suggestions: string[];
}

interface FinancialSummary {
  total_capex_inr: number;
  monthly_opex_inr: number;
  monthly_revenue_inr: number;
  monthly_profit_inr: number;
  gross_margin_percent: number;
  break_even_months: number;
  annual_roi_percent: number;
  conservative: Record<string, unknown>;
  balanced: Record<string, unknown>;
  aggressive: Record<string, unknown>;
}

interface DigitalTwinData {
  query: string;
  config: Record<string, unknown>;
  simulation: SimulationResult;
  financials: FinancialSummary;
  scene: SceneDescriptor;
  summary_text: string;
}

// ─── Number Formatting Helpers (Null-Safe) ────────────────────────────────────

function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return isFinite(n) ? n : fallback;
}

const fmt = (n: unknown) =>
  new Intl.NumberFormat("en-IN").format(Math.round(num(n)));
const fmtCr = (n: unknown) => `₹${(num(n) / 1e7).toFixed(2)} Cr`;
const fmtL = (n: unknown) => `₹${(num(n) / 1e5).toFixed(1)}L`;

// ─── Crisp Light Stat Card ────────────────────────────────────────────────────

function GlowStatCard({
  icon: Icon,
  label,
  value,
  sub,
  color = "cyan",
  danger,
  success,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  sub?: string;
  color?: "cyan" | "purple" | "amber" | "emerald";
  danger?: boolean;
  success?: boolean;
}) {
  const colorMap = {
    cyan: {
      border: "border-cyan-200/80",
      bg: "bg-gradient-to-br from-cyan-50/90 to-white",
      iconBg: "bg-cyan-100/80 text-cyan-700",
      text: "text-cyan-800",
      value: "text-slate-900",
    },
    purple: {
      border: "border-purple-200/80",
      bg: "bg-gradient-to-br from-purple-50/90 to-white",
      iconBg: "bg-purple-100/80 text-purple-700",
      text: "text-purple-800",
      value: "text-slate-900",
    },
    amber: {
      border: "border-amber-200/80",
      bg: "bg-gradient-to-br from-amber-50/90 to-white",
      iconBg: "bg-amber-100/80 text-amber-700",
      text: "text-amber-800",
      value: "text-slate-900",
    },
    emerald: {
      border: "border-emerald-200/80",
      bg: "bg-gradient-to-br from-emerald-50/90 to-white",
      iconBg: "bg-emerald-100/80 text-emerald-700",
      text: "text-emerald-800",
      value: "text-slate-900",
    },
  };

  const c = danger
    ? {
        border: "border-red-200",
        bg: "bg-gradient-to-br from-red-50/90 to-white",
        iconBg: "bg-red-100 text-red-700",
        text: "text-red-700",
        value: "text-red-950",
      }
    : success
    ? {
        border: "border-emerald-200",
        bg: "bg-gradient-to-br from-emerald-50/90 to-white",
        iconBg: "bg-emerald-100 text-emerald-700",
        text: "text-emerald-700",
        value: "text-slate-900",
      }
    : colorMap[color];

  return (
    <div
      className={`relative rounded-xl border ${c.border} ${c.bg} p-3.5 shadow-2xs transition-all hover:shadow-xs`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className={`text-[9px] font-bold uppercase tracking-[0.12em] ${c.text}`}>
          {label}
        </span>
        <div className={`flex h-6 w-6 items-center justify-center rounded-lg ${c.iconBg}`}>
          <Icon className="h-3.5 w-3.5" />
        </div>
      </div>
      <p className={`text-base font-extrabold tracking-tight leading-tight ${c.value}`}>
        {value}
      </p>
      {sub && <p className="mt-1 text-[10px] text-slate-500 font-medium">{sub}</p>}
    </div>
  );
}

// ─── Progress Stage ───────────────────────────────────────────────────────────

const STAGES = [
  { id: "parsing", label: "Parsing Requirements", icon: "🔍" },
  { id: "simulating", label: "Production Simulation", icon: "⚙️" },
  { id: "financial", label: "Financial Projection", icon: "💰" },
  { id: "scene", label: "Building 3D Scene", icon: "🏭" },
  { id: "summary", label: "AI Insights", icon: "📝" },
];

const EXAMPLE_QUERIES = [
  "Manufacture 50,000 EV chargers/month in Gujarat, ₹10 crore budget",
  "PCB assembly factory in Pune, 30,000 units/month, ₹5 crore",
  "Plastic injection molding in Chennai, 80,000 units/month, ₹8 crore",
  "Solar panel assembly in Rajasthan, 20,000 panels/month, ₹15 crore",
];

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DigitalTwinPage() {
  const { token } = useAuthStore();
  const { history } = useCopilotStore();

  // Filter strictly for planner history items (plans made by AI Planner)
  const plannerHistory = history.filter((item) => item.source === "planner");

  const [query, setQuery] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set());
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [twinData, setTwinData] = useState<DigitalTwinData | null>(null);
  const [selectedZone, setSelectedZone] = useState<SceneZone | null>(null);
  const [whatIfQuery, setWhatIfQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"simulation" | "financial" | "suggestions" | "history">("simulation");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Clean up any active SSE stream on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const generateTwin = useCallback(
    async (queryText: string, whatIfMod?: string) => {
      if (!queryText.trim()) return;
      if (!token) {
        toast.error("Please log in first.");
        return;
      }

      // Abort any previous in-flight request
      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;

      setIsGenerating(true);
      setCompletedStages(new Set());
      setCurrentStage("parsing");
      setSelectedZone(null);

      // Only clear twinData if this is a brand-new query (keep scene visible during What-If)
      if (!whatIfMod) {
        setTwinData(null);
      }

      const stageOrder = STAGES.map((s) => s.id);
      let stageIdx = 0;

      const stageTimer = setInterval(() => {
        stageIdx = Math.min(stageIdx + 1, stageOrder.length - 1);
        setCurrentStage(stageOrder[stageIdx]);
        setCompletedStages((prev) => {
          const next = new Set(prev);
          if (stageIdx > 0) next.add(stageOrder[stageIdx - 1]);
          return next;
        });
      }, 2200);

      try {
        const endpoint = whatIfMod
          ? "/api/digital-twin/what-if"
          : "/api/digital-twin/generate";

        const body = whatIfMod
          ? { query: queryText, modification: whatIfMod }
          : { query: queryText };

        const response = await fetch(`${API_URL}${endpoint}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        if (!response.body) throw new Error("No response body");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = "";

        const processLine = (line: string) => {
          if (!line.startsWith("data: ")) return;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "digital_twin_result") {
              setTwinData(event.data as DigitalTwinData);
              setCompletedStages(new Set(stageOrder));
              setCurrentStage(null);
              if (whatIfMod) {
                setWhatIfQuery("");
                toast.success("What-If scenario applied!");
              }
            } else if (event.type === "error") {
              toast.error(`Generation error: ${event.message}`);
            }
          } catch {
            /* ignore partial JSON chunk */
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          sseBuffer += decoder.decode(value, { stream: true });
          const parts = sseBuffer.split("\n\n");
          sseBuffer = parts.pop() ?? "";

          for (const part of parts) {
            for (const line of part.split("\n")) {
              processLine(line);
            }
          }
        }

        if (sseBuffer.trim()) {
          for (const line of sseBuffer.split("\n")) {
            processLine(line);
          }
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        toast.error("Failed to generate Digital Twin. Please try again.");
        console.error(err);
      } finally {
        clearInterval(stageTimer);
        if (abortControllerRef.current === controller) {
          setIsGenerating(false);
          setCurrentStage(null);
        }
      }
    },
    [token]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    generateTwin(query);
  };

  const handleWhatIf = (e: React.FormEvent) => {
    e.preventDefault();
    if (!whatIfQuery.trim() || !twinData) return;
    generateTwin(twinData.query, whatIfQuery);
  };

  const zones = twinData?.scene?.zones ?? [];

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col overflow-hidden bg-slate-50 text-slate-900">
      {/* ── Clean Light Top Bar ── */}
      {/* <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-3 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white shadow-xs">
            <Factory className="h-4.5 w-4.5 text-cyan-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight text-slate-900">
                AI Factory Digital Twin
              </h1>
              <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-slate-600">
                3D Sim
              </span>
            </div>
            <p className="text-[10px] text-slate-500">
              Real-time 3D factory capacity, bottleneck & financial simulation
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {twinData && (
            <div
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1 ${
                twinData.simulation.target_met
                  ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                  : "border-amber-300 bg-amber-50 text-amber-700"
              }`}
            >
              <div
                className={`h-1.5 w-1.5 rounded-full animate-pulse ${
                  twinData.simulation.target_met ? "bg-emerald-500" : "bg-amber-500"
                }`}
              />
              <span className="text-[10px] font-bold uppercase tracking-wider">
                {twinData.simulation.target_met ? "Target Met" : "Bottleneck Limited"}
              </span>
            </div>
          )}
          {twinData && (
            <button
              onClick={() => generateTwin(query || twinData.query)}
              disabled={isGenerating}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-900 hover:text-white hover:border-slate-900 disabled:opacity-50 transition-all shadow-2xs"
            >
              <RefreshCw className={`h-3 w-3 ${isGenerating ? "animate-spin" : ""}`} />
              Regenerate
            </button>
          )}
        </div>
      </div> */}

      {/* ── Main Layout ── */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* ── LEFT PANEL (Light Theme Sidebar) ── */}
        <div
          className={`flex shrink-0 flex-col border-r border-slate-200 bg-white shadow-2xs transition-all duration-300 ease-in-out z-20 ${
            sidebarOpen
              ? "w-[360px] opacity-100"
              : "w-0 -translate-x-full opacity-0 pointer-events-none border-none overflow-hidden"
          }`}
        >
          {/* Sidebar Top Header with Hide/Collapse Button */}
          <div className="flex shrink-0 items-center justify-between border-b border-slate-200/90 px-4 py-3 bg-slate-50/70">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 text-white shadow-xs">
                <Factory className="h-3.5 w-3.5 text-cyan-400" />
              </div>
              <div>
                <h2 className="text-xs font-bold text-slate-900 tracking-tight">Factory Controls</h2>
                <p className="text-[10px] text-slate-500">3D Digital Twin Engine</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-all"
              title="Hide sidebar (Maximize 3D View)"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </div>

          {/* Query Input */}
          <div className="shrink-0 border-b border-slate-200 p-4 bg-white">
            <form onSubmit={handleSubmit} className="space-y-2.5">
              <div className="relative">
                <textarea
                  ref={textareaRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                      handleSubmit(e as unknown as React.FormEvent);
                    }
                  }}
                  placeholder="Describe your factory... e.g. Manufacture 50,000 EV chargers/month in Gujarat, ₹10 crore budget"
                  rows={3}
                  className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50/60 p-3 text-xs text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900/10 transition-all shadow-2xs"
                />
                <span className="pointer-events-none absolute bottom-2 right-2.5 text-[9px] text-slate-400">
                  Ctrl + Enter
                </span>
              </div>
              <button
                type="submit"
                disabled={isGenerating || !query.trim()}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 transition-all"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
                    Simulating Factory...
                  </>
                ) : (
                  <>
                    <Send className="h-3.5 w-3.5 text-cyan-400" />
                    Generate Digital Twin
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Initial Blueprints & Planner History (shown when not generated) */}
          {!twinData && !isGenerating && (
            <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
              {/* Planner History Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <ClipboardCheck className="h-3.5 w-3.5 text-cyan-600" />
                    <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-700">
                      Saved Factory Plans ({plannerHistory.length})
                    </p>
                  </div>
                  <span className="text-[9px] font-semibold text-slate-400">Click to Simulate</span>
                </div>

                {plannerHistory.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-4 text-center">
                    <ClipboardCheck className="mx-auto h-5 w-5 text-slate-300" />
                    <p className="mt-1.5 text-xs font-semibold text-slate-700">No factory plans found</p>
                    <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">
                      Generate a business roadmap in the Business Planner first, and it will appear here to simulate in 3D.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1 scrollbar-thin">
                    {plannerHistory.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => {
                          setQuery(item.query);
                          generateTwin(item.query);
                        }}
                        className="group flex w-full flex-col items-start gap-1 rounded-xl border border-slate-200/90 bg-slate-50/70 p-2.5 text-left hover:border-cyan-500/70 hover:bg-cyan-50/40 hover:shadow-2xs transition-all"
                      >
                        <div className="flex w-full items-center justify-between">
                          <span className="inline-flex items-center gap-1 rounded-md bg-cyan-100/80 px-1.5 py-0.5 text-[9px] font-bold text-cyan-800">
                            <Sparkles className="h-2.5 w-2.5 text-cyan-600" />
                            Planner AI
                          </span>
                          <span className="text-[9px] text-slate-400">
                            {new Date(item.createdAt).toLocaleDateString("en-IN", {
                              month: "short",
                              day: "numeric",
                            })}
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-slate-800 line-clamp-2 group-hover:text-cyan-950 transition-colors">
                          {item.query}
                        </p>
                        {item.responsePreview && (
                          <p className="text-[10px] text-slate-500 line-clamp-1 italic">
                            {item.responsePreview}
                          </p>
                        )}
                        <div className="flex w-full items-center justify-between mt-0.5 pt-1 border-t border-slate-100">
                          <span className="text-[9px] text-slate-400 flex items-center gap-1">
                            <Clock className="h-2.5 w-2.5" />
                            {new Date(item.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                          <span className="flex items-center gap-0.5 text-[9px] font-bold text-cyan-600 group-hover:translate-x-0.5 transition-transform">
                            Simulate 3D <ChevronRight className="h-2.5 w-2.5" />
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Quick Start Blueprints */}
              <div className="space-y-1.5 pt-2 border-t border-slate-100">
                <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-400">
                  Quick Start Blueprints
                </p>
                {EXAMPLE_QUERIES.map((q, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      setQuery(q);
                      generateTwin(q);
                    }}
                    className="group flex w-full items-start gap-2 rounded-lg border border-slate-200/80 bg-slate-50/60 px-3 py-2 text-left text-[10px] text-slate-700 hover:border-slate-400 hover:bg-slate-100 hover:text-slate-900 transition-all shadow-2xs"
                  >
                    <ChevronRight className="h-3 w-3 shrink-0 mt-0.5 text-slate-400 group-hover:translate-x-0.5 group-hover:text-slate-900 transition-all" />
                    <span className="line-clamp-2">{q}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Generation Progress */}
          {isGenerating && (
            <div className="border-b border-slate-200 p-4 space-y-2.5 bg-slate-50/80">
              <div className="flex items-center justify-between">
                <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-500">
                  Simulation Pipeline
                </p>
                <span className="text-[10px] font-bold text-slate-700">
                  {Math.round((completedStages.size / STAGES.length) * 100)}%
                </span>
              </div>
              {STAGES.map((stage) => {
                const isDone = completedStages.has(stage.id);
                const isActive = currentStage === stage.id;
                return (
                  <div key={stage.id} className="flex items-center gap-3">
                    <div
                      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full transition-all ${
                        isDone
                          ? "bg-emerald-600 text-white"
                          : isActive
                          ? "bg-slate-900 ring-2 ring-slate-400/30 text-white"
                          : "border border-slate-200 bg-white text-slate-400"
                      }`}
                    >
                      {isDone ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-white" />
                      ) : isActive ? (
                        <Loader2 className="h-3 w-3 animate-spin text-white" />
                      ) : (
                        <span className="text-[10px]">{stage.icon}</span>
                      )}
                    </div>
                    <span
                      className={`text-xs transition-colors ${
                        isDone
                          ? "text-slate-700 font-medium"
                          : isActive
                          ? "text-slate-900 font-bold"
                          : "text-slate-400"
                      }`}
                    >
                      {stage.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Results Sidebar */}
          {twinData && (
            <div className="flex-1 overflow-y-auto p-3.5 space-y-3 scrollbar-thin">
              {/* Tab switcher */}
              <div className="grid grid-cols-4 gap-1 rounded-xl border border-slate-200 bg-slate-100/80 p-1">
                {(
                  [
                    { id: "simulation", label: "Operations" },
                    { id: "financial", label: "Financials" },
                    { id: "suggestions", label: "Strategy" },
                    { id: "history", label: `Plans (${plannerHistory.length})` },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`rounded-lg py-1.5 text-[9px] font-bold uppercase tracking-wider transition-all truncate px-1 ${
                      activeTab === tab.id
                        ? "bg-slate-900 text-white shadow-xs"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* SIMULATION TAB */}
              {activeTab === "simulation" && (
                <div className="space-y-2.5">
                  <div className="grid grid-cols-2 gap-2">
                    <GlowStatCard
                      icon={Factory}
                      label="Monthly Output"
                      value={`${fmt(twinData.simulation.effective_throughput_per_month)}`}
                      sub={`Target: ${fmt(twinData.config?.target_monthly_units)} units`}
                      color="cyan"
                      success={twinData.simulation.target_met}
                    />
                    <GlowStatCard
                      icon={AlertTriangle}
                      label="Bottleneck"
                      value={twinData.simulation.bottleneck_step || "None"}
                      sub={`${fmt(twinData.simulation.bottleneck_capacity_per_day)} u/day limit`}
                      danger
                    />
                    <GlowStatCard
                      icon={Users}
                      label="Workforce"
                      value={`${fmt(twinData.simulation.total_workers)}`}
                      sub="Active shift workers"
                      color="purple"
                    />
                    <GlowStatCard
                      icon={Zap}
                      label="Power Load"
                      value={`${num(twinData.simulation.total_power_kw).toFixed(0)} kW`}
                      sub={`${fmtL(twinData.simulation.estimated_monthly_power_cost_inr)}/mo`}
                      color="amber"
                    />
                  </div>

                  {/* Machine Utilization */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3.5 space-y-3 shadow-2xs">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Cpu className="h-3.5 w-3.5 text-slate-700" />
                        <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-600">
                          Line Utilization & Capacity
                        </p>
                      </div>
                      <span className="text-[9px] text-slate-400 font-medium">
                        {twinData.simulation.step_capacities?.length ?? 0} stages
                      </span>
                    </div>
                    <div className="space-y-2.5">
                      {(twinData.simulation.step_capacities ?? []).map((sc) => {
                        const util = num(sc.utilization_percent);
                        return (
                          <div key={sc.step_name} className="space-y-1">
                            <div className="flex items-center justify-between">
                              <span
                                className={`text-[11px] flex items-center gap-1 ${
                                  sc.is_bottleneck
                                    ? "text-red-700 font-bold"
                                    : "text-slate-700 font-medium"
                                }`}
                              >
                                {sc.step_name}
                                {sc.is_bottleneck && (
                                  <span className="rounded bg-red-100 px-1 py-0.2 text-[8px] font-extrabold text-red-700 uppercase">
                                    Bottleneck
                                  </span>
                                )}
                              </span>
                              <span
                                className={`text-[10px] font-bold ${
                                  sc.is_bottleneck
                                    ? "text-red-600"
                                    : util > 85
                                    ? "text-amber-600"
                                    : "text-emerald-700"
                                }`}
                              >
                                {util.toFixed(0)}%
                              </span>
                            </div>
                            <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                              <div
                                className={`h-full rounded-full transition-all duration-700 ${
                                  sc.is_bottleneck
                                    ? "bg-red-500"
                                    : util > 85
                                    ? "bg-amber-500"
                                    : "bg-slate-900"
                                }`}
                                style={{ width: `${Math.min(util, 100)}%` }}
                              />
                            </div>
                            <div className="flex justify-between text-[9px] text-slate-400">
                              <span>{fmt(sc.capacity_per_day)} units/day</span>
                              <span>
                                {sc.machine_count} machines · {sc.workers} staff
                              </span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* FINANCIAL TAB */}
              {activeTab === "financial" && (
                <div className="space-y-2.5">
                  <div className="grid grid-cols-2 gap-2">
                    <GlowStatCard
                      icon={IndianRupee}
                      label="Total CAPEX"
                      value={fmtCr(twinData.financials?.total_capex_inr)}
                      sub={`OPEX: ${fmtL(twinData.financials?.monthly_opex_inr)}/mo`}
                      color="purple"
                    />
                    <GlowStatCard
                      icon={Activity}
                      label="Monthly Revenue"
                      value={fmtL(twinData.financials?.monthly_revenue_inr)}
                      sub={`Net Profit: ${fmtL(twinData.financials?.monthly_profit_inr)}/mo`}
                      color="emerald"
                    />
                    <GlowStatCard
                      icon={TrendingUp}
                      label="Gross Margin"
                      value={`${num(twinData.financials?.gross_margin_percent).toFixed(1)}%`}
                      sub="Before tax & interest"
                      color={
                        num(twinData.financials?.gross_margin_percent) > 20
                          ? "emerald"
                          : "amber"
                      }
                    />
                    <GlowStatCard
                      icon={Target}
                      label="Break-Even"
                      value={`${num(twinData.financials?.break_even_months).toFixed(0)} mo`}
                      sub={`Annual ROI: ${num(twinData.financials?.annual_roi_percent).toFixed(0)}%`}
                      color={
                        num(twinData.financials?.break_even_months) < 30
                          ? "emerald"
                          : "amber"
                      }
                    />
                  </div>

                  {/* Scenario Comparison */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3.5 space-y-2.5 shadow-2xs">
                    <div className="flex items-center gap-2">
                      <BarChart3 className="h-3.5 w-3.5 text-slate-700" />
                      <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-600">
                        Sensitivity Scenarios
                      </p>
                    </div>
                    {[
                      {
                        fallbackLabel: "Conservative",
                        data: twinData.financials?.conservative,
                        color: "border-amber-200/80 bg-amber-50/50",
                        badge: "bg-amber-100 text-amber-800",
                      },
                      {
                        fallbackLabel: "Balanced",
                        data: twinData.financials?.balanced,
                        color: "border-cyan-200/80 bg-cyan-50/50",
                        badge: "bg-cyan-100 text-cyan-800",
                      },
                      {
                        fallbackLabel: "Aggressive",
                        data: twinData.financials?.aggressive,
                        color: "border-emerald-200/80 bg-emerald-50/50",
                        badge: "bg-emerald-100 text-emerald-800",
                      },
                    ].map(({ fallbackLabel, data: s, color, badge }) => {
                      if (!s || typeof s !== "object") return null;
                      const rawLabel =
                        typeof s.label === "string" && s.label.trim()
                          ? s.label.split(" ")[0]
                          : fallbackLabel;
                      return (
                        <div
                          key={fallbackLabel}
                          className={`flex items-center justify-between rounded-lg border ${color} px-3 py-2`}
                        >
                          <span
                            className={`rounded-md px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${badge}`}
                          >
                            {rawLabel}
                          </span>
                          <div className="flex gap-4 text-right">
                            <div>
                              <p className="text-[9px] text-slate-500">Annual ROI</p>
                              <p className="text-[11px] font-bold text-slate-900">
                                {num(s.annual_roi_percent).toFixed(0)}%
                              </p>
                            </div>
                            <div>
                              <p className="text-[9px] text-slate-500">Break-Even</p>
                              <p className="text-[11px] font-bold text-slate-700">
                                {num(s.break_even_months).toFixed(0)} mo
                              </p>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* SUGGESTIONS TAB */}
              {activeTab === "suggestions" && (
                <div className="space-y-3">
                  {/* What-If Simulator moved to top of AI Strategy for easy access */}
                  <div className="rounded-xl border border-slate-200 bg-gradient-to-br from-slate-900 to-slate-800 p-3.5 text-white space-y-2.5 shadow-sm">
                    <div className="flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-cyan-300">
                        What-If Scenario Simulator
                      </p>
                    </div>
                    <form onSubmit={handleWhatIf} className="space-y-2">
                      <input
                        type="text"
                        value={whatIfQuery}
                        onChange={(e) => setWhatIfQuery(e.target.value)}
                        placeholder="e.g. Add 2 more machines to bottleneck step"
                        className="w-full rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-[11px] text-white placeholder-slate-400 focus:border-cyan-400 focus:bg-white/15 focus:outline-none"
                      />
                      <button
                        type="submit"
                        disabled={isGenerating || !whatIfQuery.trim()}
                        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-cyan-500 px-3 py-2 text-[11px] font-bold text-slate-950 hover:bg-cyan-400 disabled:opacity-40 transition-all"
                      >
                        <RefreshCw className={`h-3 w-3 ${isGenerating ? "animate-spin" : ""}`} />
                        {isGenerating ? "Running Simulation..." : "Run What-If Modification"}
                      </button>
                    </form>
                  </div>

                  {/* Expert Summary */}
                  {twinData.summary_text && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5 shadow-2xs">
                      <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-600 mb-1.5">
                        Executive AI Summary
                      </p>
                      <p className="text-[11px] text-slate-700 leading-relaxed">
                        {twinData.summary_text}
                      </p>
                    </div>
                  )}

                  {/* AI Optimization Suggestions */}
                  <div className="space-y-2">
                    <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500 px-0.5">
                      Actionable Optimizations
                    </p>
                    {(twinData.simulation.optimization_suggestions ?? []).map((sug, i) => (
                      <div
                        key={i}
                        className="flex gap-2.5 rounded-xl border border-slate-200 bg-white p-3 shadow-2xs"
                      >
                        <span className="mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full bg-slate-900 text-[9px] font-bold text-white">
                          {i + 1}
                        </span>
                        <p className="text-[11px] text-slate-700 leading-relaxed">{sug}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* SAVED PLANS TAB */}
              {activeTab === "history" && (
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-600">
                      Planner History ({plannerHistory.length})
                    </p>
                    <span className="text-[9px] text-slate-400">Click to switch plan</span>
                  </div>

                  {plannerHistory.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 p-4 text-center">
                      <ClipboardCheck className="mx-auto h-5 w-5 text-slate-300" />
                      <p className="mt-1 text-xs font-semibold text-slate-700">No factory plans found</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">
                        Plans generated in Business Planner will appear here to simulate in 3D.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {plannerHistory.map((item) => {
                        const isActivePlan = twinData?.query === item.query;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => {
                              setQuery(item.query);
                              generateTwin(item.query);
                            }}
                            className={`group flex w-full flex-col items-start gap-1 rounded-xl border p-2.5 text-left transition-all ${
                              isActivePlan
                                ? "border-cyan-500 bg-cyan-50/50 ring-1 ring-cyan-500/20"
                                : "border-slate-200/90 bg-slate-50/70 hover:border-cyan-500/70 hover:bg-cyan-50/30"
                            }`}
                          >
                            <div className="flex w-full items-center justify-between">
                              <span
                                className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[9px] font-bold ${
                                  isActivePlan
                                    ? "bg-cyan-600 text-white"
                                    : "bg-cyan-100/80 text-cyan-800"
                                }`}
                              >
                                <Sparkles className="h-2.5 w-2.5" />
                                {isActivePlan ? "Active in 3D" : "Planner AI"}
                              </span>
                              <span className="text-[9px] text-slate-400">
                                {new Date(item.createdAt).toLocaleDateString("en-IN", {
                                  month: "short",
                                  day: "numeric",
                                })}
                              </span>
                            </div>
                            <p className="text-xs font-semibold text-slate-800 line-clamp-2 group-hover:text-cyan-950 transition-colors">
                              {item.query}
                            </p>
                            <div className="flex w-full items-center justify-between mt-0.5 pt-1 border-t border-slate-100">
                              <span className="text-[9px] text-slate-400">
                                {isActivePlan ? "Currently Simulated" : "Click to simulate"}
                              </span>
                              <span className="flex items-center gap-0.5 text-[9px] font-bold text-cyan-600 group-hover:translate-x-0.5 transition-transform">
                                {isActivePlan ? "Active" : "Simulate 3D →"}
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── 3D CANVAS AREA (Dedicated Dark 3D Viewport) ── */}
        <div className="relative flex-1 overflow-hidden bg-[#060b16]">
          {/* Floating Show Sidebar Button when collapsed */}
          {!sidebarOpen && (
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="absolute top-4 left-4 z-30 flex items-center gap-2 rounded-xl border border-slate-700/60 bg-slate-900/90 px-3.5 py-2.5 text-xs font-semibold text-white shadow-xl backdrop-blur-md hover:bg-slate-800 hover:border-cyan-500/50 hover:text-cyan-300 transition-all group"
              title="Show Factory Controls"
            >
              <ChevronRight className="h-4 w-4 text-cyan-400 group-hover:translate-x-0.5 transition-transform" />
              <span>Factory Controls</span>
              {plannerHistory.length > 0 && (
                <span className="rounded-full bg-cyan-500/20 px-1.5 py-0.5 text-[9px] font-bold text-cyan-300">
                  {plannerHistory.length}
                </span>
              )}
            </button>
          )}
          {/* Empty state */}
          {!twinData && !isGenerating && (
            <div className="flex h-full w-full flex-col items-center justify-center gap-8 text-center px-8">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_#0e1f3a_0%,_#060b16_70%)]" />
              <div
                className="absolute inset-0 opacity-20"
                style={{
                  backgroundImage:
                    "linear-gradient(rgba(6,182,212,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.15) 1px, transparent 1px)",
                  backgroundSize: "40px 40px",
                }}
              />

              <div className="relative z-10 flex flex-col items-center gap-6">
                <div className="relative">
                  <div className="absolute inset-0 rounded-3xl bg-cyan-500/20 blur-3xl scale-150" />
                  <div className="relative flex h-24 w-24 items-center justify-center rounded-2xl border border-cyan-500/30 bg-gradient-to-br from-cyan-500/20 to-blue-600/20 shadow-2xl shadow-cyan-500/20 backdrop-blur">
                    <Factory className="h-12 w-12 text-cyan-400" />
                  </div>
                </div>

                <div className="space-y-2">
                  <h2 className="text-3xl font-black text-white">
                    Build Your{" "}
                    <span className="bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">
                      Factory Twin
                    </span>
                  </h2>
                  <p className="max-w-md text-sm text-slate-400 leading-relaxed">
                    Describe your manufacturing plant on the left. AI will calculate line
                    capacities, pinpoint bottlenecks, project ROI, and assemble an
                    interactive 3D layout.
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-3 max-w-md w-full">
                  {[
                    {
                      icon: "⚙️",
                      label: "Line Balancing",
                      color: "border-cyan-500/30 bg-cyan-500/5 text-cyan-400",
                    },
                    {
                      icon: "🔴",
                      label: "Bottleneck Radar",
                      color: "border-red-500/30 bg-red-500/5 text-red-400",
                    },
                    {
                      icon: "📊",
                      label: "CAPEX / ROI Model",
                      color: "border-purple-500/30 bg-purple-500/5 text-purple-400",
                    },
                  ].map((f) => (
                    <div
                      key={f.label}
                      className={`rounded-xl border ${f.color} p-4 flex flex-col items-center gap-2 backdrop-blur`}
                    >
                      <span className="text-2xl">{f.icon}</span>
                      <p
                        className={`text-[10px] font-bold uppercase tracking-wider ${f.color
                          .split(" ")
                          .pop()}`}
                      >
                        {f.label}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Initial Loading state */}
          {isGenerating && !twinData && (
            <div className="flex h-full w-full flex-col items-center justify-center gap-6">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_#0e1f3a_0%,_#060b16_70%)]" />
              <div className="relative z-10 flex flex-col items-center gap-6">
                <div className="relative h-32 w-32">
                  <div
                    className="absolute inset-0 animate-ping rounded-full bg-cyan-500/10"
                    style={{ animationDuration: "2s" }}
                  />
                  <div
                    className="absolute inset-2 animate-spin rounded-full border border-transparent border-t-cyan-500 border-r-cyan-500/50"
                    style={{ animationDuration: "1.5s" }}
                  />
                  <div
                    className="absolute inset-5 animate-spin rounded-full border border-transparent border-t-blue-500 border-l-blue-500/50"
                    style={{ animationDuration: "2.5s", animationDirection: "reverse" }}
                  />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Factory className="h-10 w-10 text-cyan-400" />
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold text-white">
                    Synthesizing 3D Digital Twin
                  </p>
                  <p className="text-sm text-cyan-400/90 mt-1 font-medium">
                    {currentStage
                      ? STAGES.find((s) => s.id === currentStage)?.label
                      : "Initializing..."}
                  </p>
                </div>
                <div className="w-64 h-1.5 bg-white/[0.08] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-400 to-blue-500 rounded-full transition-all duration-700"
                    style={{
                      width: `${Math.max((completedStages.size / STAGES.length) * 100, 12)}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* 3D Scene — wrapped in Error Boundary */}
          {twinData && (
            <>
              <FactoryErrorBoundary resetKey={twinData.query}>
                <FactoryCanvas
                  scene={twinData.scene}
                  selectedZoneId={selectedZone?.id ?? null}
                  onZoneClick={setSelectedZone}
                />
              </FactoryErrorBoundary>

              {/* Non-destructive What-If Loading Banner */}
              {isGenerating && (
                <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2.5 rounded-full border border-cyan-500/40 bg-slate-950/85 px-4 py-2 text-xs font-semibold text-cyan-300 shadow-2xl backdrop-blur-md">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-400" />
                  <span>
                    Recalculating:{" "}
                    {currentStage
                      ? STAGES.find((s) => s.id === currentStage)?.label
                      : "Updating scene..."}
                  </span>
                </div>
              )}

              {/* Top-left Factory Badge */}
              <div
                className={`absolute top-4 ${
                  sidebarOpen ? "left-4" : "left-44"
                } z-20 rounded-xl border border-white/10 bg-slate-950/75 px-3.5 py-2.5 backdrop-blur-md max-w-[260px] transition-all duration-300`}
              >
                <div className="flex items-center gap-1.5">
                  <Layers className="h-3 w-3 text-cyan-400" />
                  <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-cyan-400">
                    Active Blueprint
                  </p>
                </div>
                <p className="text-xs font-semibold text-white mt-0.5 truncate">
                  {twinData.query}
                </p>
              </div>

              {/* Top-right KPI Pill */}
              <div className="absolute top-4 right-4 flex items-center gap-3 rounded-xl border border-white/10 bg-slate-950/75 px-3.5 py-2 backdrop-blur-md">
                <div>
                  <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-emerald-400">
                    Throughput
                  </p>
                  <p className="text-sm font-bold text-white">
                    {fmt(twinData.simulation.effective_throughput_per_month)}
                    <span className="text-[10px] text-slate-400 ml-1">u/mo</span>
                  </p>
                </div>
                <div className="h-6 w-[1px] bg-white/10" />
                <div>
                  <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-purple-400">
                    Est. ROI
                  </p>
                  <p className="text-sm font-bold text-white">
                    {num(twinData.financials?.annual_roi_percent).toFixed(0)}%
                    <span className="text-[10px] text-slate-400 ml-1">/yr</span>
                  </p>
                </div>
              </div>

              {/* Interactive Zone Quick-Select Bar + Controls Hint */}
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2 max-w-[90%]">
                {zones.length > 0 && (
                  <div className="flex items-center gap-1.5 overflow-x-auto rounded-xl border border-white/10 bg-slate-950/80 px-2.5 py-1.5 shadow-xl backdrop-blur-md scrollbar-none max-w-full">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-slate-400 px-1.5 shrink-0">
                      Zones:
                    </span>
                    {zones.map((z) => {
                      const active = selectedZone?.id === z.id;
                      return (
                        <button
                          key={z.id}
                          onClick={() => setSelectedZone(active ? null : z)}
                          className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-semibold transition-all shrink-0 ${
                            active
                              ? "bg-cyan-500 text-slate-950 font-bold shadow-xs"
                              : z.is_bottleneck
                              ? "border border-red-500/40 bg-red-500/15 text-red-300 hover:bg-red-500/25"
                              : "bg-white/5 text-slate-300 hover:bg-white/15 hover:text-white"
                          }`}
                        >
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{
                              backgroundColor: z.is_bottleneck ? "#ef4444" : z.color,
                            }}
                          />
                          {z.name}
                          {z.is_bottleneck && " ⚠"}
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="rounded-full border border-white/10 bg-black/50 px-3.5 py-1 text-[10px] font-medium text-slate-400 backdrop-blur-md pointer-events-none">
                  🖱 Left-drag to orbit · Scroll to zoom · Right-drag to pan · Click a zone to inspect
                </div>
              </div>

              {/* Zone Inspector Modal Card */}
              {selectedZone && (
                <div className="absolute bottom-20 right-5 z-20 w-80 rounded-2xl border border-white/15 bg-slate-950/85 p-4 shadow-2xl backdrop-blur-xl animate-in fade-in slide-in-from-bottom-2 duration-200">
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <div
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: selectedZone.color }}
                        />
                        <span className="text-[9px] font-bold uppercase tracking-wider text-cyan-400">
                          {selectedZone.zone_type || "Production Zone"}
                        </span>
                      </div>
                      <h3 className="text-sm font-bold text-white leading-tight mt-0.5">
                        {selectedZone.name}
                      </h3>
                    </div>
                    <button
                      onClick={() => setSelectedZone(null)}
                      className="rounded-lg p-1 text-slate-400 hover:bg-white/10 hover:text-white transition-colors"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>

                  {selectedZone.is_bottleneck && (
                    <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/15 px-2.5 py-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                      <span className="text-[10px] font-bold text-red-300 uppercase tracking-wider">
                        Primary Line Bottleneck
                      </span>
                    </div>
                  )}

                  {selectedZone.metadata &&
                    Object.keys(selectedZone.metadata).filter((k) => k !== "description")
                      .length > 0 && (
                      <div className="border-t border-white/10 pt-2.5 space-y-1.5">
                        {Object.entries(selectedZone.metadata)
                          .filter(([k]) => k !== "description")
                          .map(([k, v]) => (
                            <div key={k} className="flex items-center justify-between gap-2">
                              <span className="text-[10px] capitalize text-slate-400">
                                {k.replace(/_/g, " ")}
                              </span>
                              <span className="text-[10px] font-semibold text-slate-100 text-right">
                                {String(v)}
                              </span>
                            </div>
                          ))}
                      </div>
                    )}

                  {selectedZone.metadata?.description != null && (
                    <p className="mt-2.5 text-[10px] text-slate-300 leading-relaxed border-t border-white/10 pt-2.5">
                      {String(selectedZone.metadata.description)}
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}