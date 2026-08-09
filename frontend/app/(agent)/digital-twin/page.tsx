"use client";

import { useRef, useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { useAuthStore } from "@/store/use-auth-store";
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
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";

// Import shared types from FactoryCanvas (avoids duplication, no circular deps)
import type {
  SceneZone,
  SceneDescriptor,
  FactoryCanvasProps,
} from "./FactoryCanvas";

// Dynamically import the 3D canvas — ssr:false keeps Three.js out of Node.js
const FactoryCanvas = dynamic<FactoryCanvasProps>(
  () => import("./FactoryCanvas"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full w-full items-center justify-center bg-[#0a0f1e]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-400" />
          <p className="text-sm text-cyan-400/60">Initializing 3D Engine...</p>
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


// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  highlight,
  danger,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
  danger?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-3 transition-all ${
        danger
          ? "border-red-500/40 bg-red-950/30"
          : highlight
          ? "border-cyan-500/40 bg-cyan-950/20"
          : "border-white/10 bg-white/5"
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <Icon
          className={`h-3.5 w-3.5 ${
            danger ? "text-red-400" : highlight ? "text-cyan-400" : "text-slate-400"
          }`}
        />
        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
          {label}
        </span>
      </div>
      <p
        className={`text-lg font-bold leading-tight ${
          danger ? "text-red-300" : highlight ? "text-cyan-300" : "text-white"
        }`}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-[10px] text-slate-500">{sub}</p>}
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
  "I want to manufacture 50,000 EV chargers/month in Gujarat with ₹10 crore budget",
  "Setup a PCB assembly factory in Pune targeting 30,000 units/month with ₹5 crore",
  "Plastic injection molding unit in Chennai, 80,000 units/month, ₹8 crore budget",
  "Solar panel assembly factory in Rajasthan, 20,000 panels/month, ₹15 crore",
];

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function DigitalTwinPage() {
  const { token } = useAuthStore();

  const [query, setQuery] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set());
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [twinData, setTwinData] = useState<DigitalTwinData | null>(null);
  const [selectedZone, setSelectedZone] = useState<SceneZone | null>(null);
  const [showFinancials, setShowFinancials] = useState(false);
  const [whatIfQuery, setWhatIfQuery] = useState("");
  const [isWhatIf, setIsWhatIf] = useState(false);
  const [activeTab, setActiveTab] = useState<"simulation" | "financial" | "suggestions">(
    "simulation"
  );

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const generateTwin = useCallback(
    async (queryText: string, whatIfMod?: string) => {
      if (!queryText.trim()) return;
      if (!token) {
        toast.error("Please log in first.");
        return;
      }

      setIsGenerating(true);
      setCompletedStages(new Set());
      setCurrentStage("parsing");
      setTwinData(null);
      setSelectedZone(null);

      const stageOrder = STAGES.map((s) => s.id);
      let stageIdx = 0;

      // Advance stages every ~2s visually
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
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        if (!response.body) throw new Error("No response body");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        // ── SSE buffer ──────────────────────────────────────────────────────
        // The digital_twin_result payload can be 50-100KB. TCP/browser chunking
        // splits it across many read() calls. We must accumulate into a buffer
        // and only parse complete "data: ..." lines.
        let sseBuffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          // Append new chunk to buffer (stream:true keeps multi-byte chars intact)
          sseBuffer += decoder.decode(value, { stream: true });

          // Split on double-newline (SSE event boundary)
          const parts = sseBuffer.split("\n\n");
          // Last element may be incomplete — keep it in the buffer
          sseBuffer = parts.pop() ?? "";

          for (const part of parts) {
            // Each part may have multiple "data: ..." lines (rare but valid SSE)
            const lines = part.split("\n");
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              try {
                const event = JSON.parse(line.slice(6));
                if (event.type === "digital_twin_result") {
                  setTwinData(event.data as DigitalTwinData);
                  setCompletedStages(new Set(stageOrder));
                  setCurrentStage(null);
                } else if (event.type === "error") {
                  toast.error(`Generation error: ${event.message}`);
                }
              } catch {
                // Incomplete JSON — part of a larger chunk, safe to ignore
              }
            }
          }
        }

        // Flush any remaining buffered data after stream ends
        if (sseBuffer.trim()) {
          const lines = sseBuffer.split("\n");
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === "digital_twin_result") {
                setTwinData(event.data as DigitalTwinData);
                setCompletedStages(new Set(stageOrder));
                setCurrentStage(null);
              }
            } catch {
              // ignore
            }
          }
        }

      } catch (err) {
        toast.error("Failed to generate Digital Twin. Please try again.");
        console.error(err);
      } finally {
        clearInterval(stageTimer);
        setIsGenerating(false);
        setCurrentStage(null);
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
    setIsWhatIf(false);
  };

  const fmt = (n: number) => new Intl.NumberFormat("en-IN").format(Math.round(n));
  const fmtCr = (n: number) => `₹${(n / 1e7).toFixed(2)} Cr`;
  const fmtL = (n: number) => `₹${(n / 1e5).toFixed(1)}L`;

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col overflow-hidden bg-[#080d1a] text-white">
      {/* ── Header ── */}
      <div className="flex shrink-0 items-center justify-between border-b border-white/10 bg-[#080d1a]/80 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600">
            <Factory className="h-4 w-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-white">
              AI Factory Digital Twin
            </h1>
            <p className="text-[10px] text-slate-500">
              Computational 3D factory simulation before you build
            </p>
          </div>
        </div>
        {twinData && (
          <button
            onClick={() => generateTwin(query)}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-white/10 transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            Regenerate
          </button>
        )}
      </div>

      {/* ── Main Layout ── */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── Left Panel: Query + Sidebar ── */}
        <div className="flex w-[340px] shrink-0 flex-col border-r border-white/10 overflow-hidden">
          {/* Query Input */}
          <div className="border-b border-white/10 p-4">
            <form onSubmit={handleSubmit} className="space-y-2">
              <textarea
                ref={textareaRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleSubmit(e as unknown as React.FormEvent);
                }}
                placeholder="Describe your factory... e.g. I want to manufacture 50,000 EV chargers/month in Gujarat with ₹10 crore budget"
                rows={4}
                className="w-full resize-none rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-slate-200 placeholder-slate-500 focus:border-cyan-500/50 focus:outline-none focus:ring-1 focus:ring-cyan-500/30 transition-all"
              />
              <button
                type="submit"
                disabled={isGenerating || !query.trim()}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-cyan-900/30 hover:from-cyan-500 hover:to-blue-500 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating Twin...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    Generate Digital Twin
                  </>
                )}
              </button>
            </form>

            {/* Example queries */}
            {!twinData && !isGenerating && (
              <div className="mt-3 space-y-1.5">
                <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                  Try an example
                </p>
                {EXAMPLE_QUERIES.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      setQuery(q);
                      generateTwin(q);
                    }}
                    className="w-full rounded-lg border border-white/5 bg-white/3 px-3 py-2 text-left text-[10px] text-slate-400 hover:border-cyan-500/30 hover:bg-cyan-950/20 hover:text-slate-300 transition-all"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Generation Progress */}
          {isGenerating && (
            <div className="border-b border-white/10 p-4 space-y-2">
              <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                Generating...
              </p>
              {STAGES.map((stage) => {
                const isDone = completedStages.has(stage.id);
                const isActive = currentStage === stage.id;
                return (
                  <div key={stage.id} className="flex items-center gap-2.5">
                    <div
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] transition-all ${
                        isDone
                          ? "bg-cyan-500"
                          : isActive
                          ? "bg-blue-600 ring-2 ring-blue-400/30"
                          : "border border-white/10 bg-white/5"
                      }`}
                    >
                      {isDone ? (
                        <CheckCircle2 className="h-3 w-3 text-white" />
                      ) : isActive ? (
                        <Loader2 className="h-2.5 w-2.5 animate-spin text-white" />
                      ) : (
                        <span className="text-slate-500">{stage.icon}</span>
                      )}
                    </div>
                    <span
                      className={`text-xs ${
                        isDone
                          ? "text-cyan-400"
                          : isActive
                          ? "text-white"
                          : "text-slate-600"
                      }`}
                    >
                      {stage.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Simulation Results Sidebar */}
          {twinData && !isGenerating && (
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {/* Tab switcher */}
              <div className="flex gap-1 rounded-lg bg-white/5 p-1">
                {(["simulation", "financial", "suggestions"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`flex-1 rounded-md py-1 text-[10px] font-medium capitalize transition-all ${
                      activeTab === tab
                        ? "bg-cyan-600 text-white"
                        : "text-slate-500 hover:text-slate-300"
                    }`}
                  >
                    {tab === "simulation" ? "Sim" : tab === "financial" ? "Finance" : "Tips"}
                  </button>
                ))}
              </div>

              {/* SIMULATION TAB */}
              {activeTab === "simulation" && (
                <div className="space-y-2">
                  <StatCard
                    icon={Factory}
                    label="Monthly Output"
                    value={`${fmt(twinData.simulation.effective_throughput_per_month)} units`}
                    sub={`Target: ${fmt(twinData.config.target_monthly_units as number)} units`}
                    highlight={twinData.simulation.target_met}
                  />
                  <StatCard
                    icon={AlertTriangle}
                    label="Bottleneck"
                    value={twinData.simulation.bottleneck_step}
                    sub={`${fmt(twinData.simulation.bottleneck_capacity_per_day)} units/day limit`}
                    danger
                  />
                  <StatCard
                    icon={Users}
                    label="Total Workers"
                    value={`${twinData.simulation.total_workers} people`}
                    sub="Across all shifts"
                  />
                  <StatCard
                    icon={Zap}
                    label="Power Load"
                    value={`${twinData.simulation.total_power_kw.toFixed(0)} kW`}
                    sub={`${fmtL(twinData.simulation.estimated_monthly_power_cost_inr)}/month electricity`}
                  />

                  {/* Machine utilization bars */}
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-2">
                    <p className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                      Machine Utilization
                    </p>
                    {twinData.simulation.step_capacities.map((sc) => (
                      <div key={sc.step_name} className="space-y-0.5">
                        <div className="flex items-center justify-between">
                          <span
                            className={`text-[10px] ${
                              sc.is_bottleneck ? "text-red-400 font-semibold" : "text-slate-400"
                            }`}
                          >
                            {sc.step_name} {sc.is_bottleneck && "⚠"}
                          </span>
                          <span className="text-[10px] text-slate-500">
                            {sc.utilization_percent.toFixed(0)}%
                          </span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                          <div
                            className={`h-full rounded-full transition-all duration-700 ${
                              sc.is_bottleneck
                                ? "bg-red-500"
                                : sc.utilization_percent > 80
                                ? "bg-amber-500"
                                : "bg-cyan-500"
                            }`}
                            style={{ width: `${Math.min(sc.utilization_percent, 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* FINANCIAL TAB */}
              {activeTab === "financial" && (
                <div className="space-y-2">
                  <StatCard
                    icon={IndianRupee}
                    label="Total CAPEX"
                    value={fmtCr(twinData.financials.total_capex_inr)}
                    highlight
                  />
                  <StatCard
                    icon={IndianRupee}
                    label="Monthly Revenue"
                    value={fmtL(twinData.financials.monthly_revenue_inr)}
                    sub={`Profit: ${fmtL(twinData.financials.monthly_profit_inr)}/month`}
                  />
                  <StatCard
                    icon={TrendingUp}
                    label="Gross Margin"
                    value={`${twinData.financials.gross_margin_percent.toFixed(1)}%`}
                    highlight={twinData.financials.gross_margin_percent > 20}
                  />
                  <StatCard
                    icon={BarChart3}
                    label="Break-even"
                    value={`${twinData.financials.break_even_months.toFixed(0)} months`}
                    sub={`Annual ROI: ${twinData.financials.annual_roi_percent.toFixed(0)}%`}
                    highlight={twinData.financials.break_even_months < 30}
                  />

                  {/* Scenario comparison */}
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-2">
                    <p className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                      Scenario Comparison
                    </p>
                    {[
                      twinData.financials.conservative,
                      twinData.financials.balanced,
                      twinData.financials.aggressive,
                    ].map((s: Record<string, unknown>) => (
                      <div
                        key={s.label as string}
                        className="flex items-center justify-between rounded-lg border border-white/5 bg-white/3 px-2.5 py-2"
                      >
                        <span className="text-[10px] font-medium text-slate-300">
                          {(s.label as string).split(" ")[0]}
                        </span>
                        <div className="flex gap-3 text-right">
                          <div>
                            <p className="text-[9px] text-slate-500">ROI</p>
                            <p className="text-[10px] font-semibold text-cyan-400">
                              {(s.annual_roi_percent as number).toFixed(0)}%
                            </p>
                          </div>
                          <div>
                            <p className="text-[9px] text-slate-500">B/E</p>
                            <p className="text-[10px] font-semibold text-slate-300">
                              {(s.break_even_months as number).toFixed(0)}mo
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* SUGGESTIONS TAB */}
              {activeTab === "suggestions" && (
                <div className="space-y-2">
                  <p className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                    AI Optimization Suggestions
                  </p>
                  {twinData.simulation.optimization_suggestions.map((sug, i) => (
                    <div
                      key={i}
                      className="rounded-xl border border-white/10 bg-white/5 p-3 text-[11px] text-slate-300 leading-relaxed"
                    >
                      {sug}
                    </div>
                  ))}
                  {/* Summary */}
                  <div className="rounded-xl border border-cyan-500/20 bg-cyan-950/20 p-3">
                    <p className="text-[10px] font-medium uppercase tracking-wider text-cyan-400 mb-2">
                      Expert Summary
                    </p>
                    <p className="text-[11px] text-slate-300 leading-relaxed">
                      {twinData.summary_text}
                    </p>
                  </div>

                  {/* What-if */}
                  <div className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-2">
                    <p className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                      What-If Simulator
                    </p>
                    <form onSubmit={handleWhatIf} className="space-y-2">
                      <input
                        type="text"
                        value={whatIfQuery}
                        onChange={(e) => setWhatIfQuery(e.target.value)}
                        placeholder="e.g. increase production to 100k/month"
                        className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[11px] text-slate-200 placeholder-slate-600 focus:border-cyan-500/50 focus:outline-none"
                      />
                      <button
                        type="submit"
                        disabled={isGenerating || !whatIfQuery.trim()}
                        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-blue-700 px-3 py-2 text-[11px] font-semibold text-white hover:bg-blue-600 disabled:opacity-50 transition-colors"
                      >
                        <RefreshCw className="h-3 w-3" />
                        Simulate What-If
                      </button>
                    </form>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── 3D Canvas Area ── */}
        <div className="relative flex-1 overflow-hidden bg-[#0a0f1e]">
          {!twinData && !isGenerating && (
            <div className="flex h-full w-full flex-col items-center justify-center gap-6 text-center">
              <div className="relative">
                <div className="absolute inset-0 rounded-full bg-cyan-500/10 blur-3xl" />
                <div className="relative flex h-24 w-24 items-center justify-center rounded-2xl border border-white/10 bg-white/5">
                  <Factory className="h-12 w-12 text-cyan-400/60" />
                </div>
              </div>
              <div className="max-w-sm space-y-2">
                <h2 className="text-xl font-bold text-white">
                  Build Your Factory Twin
                </h2>
                <p className="text-sm text-slate-500">
                  Describe your manufacturing idea on the left. The AI will simulate
                  production capacity, detect bottlenecks, and render your factory in 3D.
                </p>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center max-w-md">
                {[
                  { icon: "⚙️", label: "Capacity Simulation" },
                  { icon: "🔴", label: "Bottleneck Detection" },
                  { icon: "📊", label: "Financial Modeling" },
                ].map((f) => (
                  <div
                    key={f.label}
                    className="rounded-xl border border-white/10 bg-white/5 p-3"
                  >
                    <div className="text-2xl mb-1">{f.icon}</div>
                    <p className="text-[10px] text-slate-400">{f.label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {isGenerating && !twinData && (
            <div className="flex h-full w-full flex-col items-center justify-center gap-4">
              <div className="relative h-32 w-32">
                <div className="absolute inset-0 animate-ping rounded-full bg-cyan-500/20" />
                <div className="absolute inset-4 animate-spin rounded-full border-2 border-transparent border-t-cyan-500" />
                <div className="absolute inset-8 animate-pulse rounded-full bg-cyan-600/30" />
                <Factory className="absolute inset-0 m-auto h-10 w-10 text-cyan-400" />
              </div>
              <div className="text-center">
                <p className="font-semibold text-white">Generating Your Factory Twin</p>
                <p className="text-sm text-slate-500 mt-1">
                  NVIDIA AI is simulating your factory...
                </p>
              </div>
            </div>
          )}

          {twinData && (
            <>
              <FactoryCanvas
                scene={twinData.scene}
                onZoneClick={setSelectedZone}
              />

              {/* Controls hint */}
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-white/10 bg-black/60 px-4 py-1.5 text-[10px] text-slate-400 backdrop-blur-sm pointer-events-none">
                🖱 Drag to rotate · Scroll to zoom · Right-drag to pan
              </div>

              {/* Zone info panel on click */}
              {selectedZone && (
                <div className="absolute right-4 top-4 w-64 rounded-2xl border border-white/10 bg-black/80 p-4 backdrop-blur-lg">
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="text-sm font-bold text-white leading-tight">
                      {selectedZone.name}
                    </h3>
                    <button
                      onClick={() => setSelectedZone(null)}
                      className="text-slate-500 hover:text-white"
                    >
                      ✕
                    </button>
                  </div>
                  {selectedZone.is_bottleneck && (
                    <div className="mb-3 flex items-center gap-1.5 rounded-lg bg-red-950/60 px-2.5 py-1.5">
                      <AlertTriangle className="h-3 w-3 text-red-400" />
                      <span className="text-[10px] font-semibold text-red-300">
                        BOTTLENECK DETECTED
                      </span>
                    </div>
                  )}
                  <div className="space-y-1.5">
                    {Object.entries(selectedZone.metadata).map(([k, v]) => (
                      <div key={k} className="flex items-center justify-between">
                        <span className="text-[10px] capitalize text-slate-500">
                          {k.replace(/_/g, " ")}
                        </span>
                        <span className="text-[10px] font-medium text-slate-300">
                          {String(v)}
                        </span>
                      </div>
                    ))}
                    {selectedZone.metadata.description != null && (
                      <p className="mt-2 text-[10px] text-slate-400 leading-relaxed border-t border-white/10 pt-2">
                        {String(selectedZone.metadata.description)}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
