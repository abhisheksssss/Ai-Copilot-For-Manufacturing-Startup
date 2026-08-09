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
  ChevronRight,
  Activity,
  Target,
  Cpu,
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

// ─── Crisp Light Stat Card ───────────────────────────────────────────────────

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
    cyan:    { border: "border-cyan-200",    bg: "bg-cyan-50/70",    text: "text-cyan-700", value: "text-slate-900" },
    purple:  { border: "border-purple-200",  bg: "bg-purple-50/70",  text: "text-purple-700", value: "text-slate-900" },
    amber:   { border: "border-amber-200",   bg: "bg-amber-50/70",   text: "text-amber-700", value: "text-slate-900" },
    emerald: { border: "border-emerald-200", bg: "bg-emerald-50/70", text: "text-emerald-700", value: "text-slate-900" },
  };
  const c = danger
    ? { border: "border-red-200", bg: "bg-red-50/80", text: "text-red-700", value: "text-red-950" }
    : success
    ? { border: "border-emerald-200", bg: "bg-emerald-50/80", text: "text-emerald-700", value: "text-slate-900" }
    : colorMap[color];

  return (
    <div className={`relative rounded-xl border ${c.border} ${c.bg} p-3.5 shadow-2xs transition-all hover:shadow-xs`}>
      <div className="flex items-center gap-2 mb-1.5">
        <Icon className={`h-3.5 w-3.5 ${c.text}`} />
        <span className={`text-[9px] font-bold uppercase tracking-[0.12em] ${c.text}`}>
          {label}
        </span>
      </div>
      <p className={`text-base font-bold leading-tight ${c.value}`}>{value}</p>
      {sub && <p className="mt-0.5 text-[10px] text-slate-500 font-medium">{sub}</p>}
    </div>
  );
}

// ─── Progress Stage ───────────────────────────────────────────────────────────

const STAGES = [
  { id: "parsing",    label: "Parsing Requirements",   icon: "🔍" },
  { id: "simulating", label: "Production Simulation",   icon: "⚙️" },
  { id: "financial",  label: "Financial Projection",    icon: "💰" },
  { id: "scene",      label: "Building 3D Scene",       icon: "🏭" },
  { id: "summary",    label: "AI Insights",             icon: "📝" },
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

  const [query, setQuery] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set());
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [twinData, setTwinData] = useState<DigitalTwinData | null>(null);
  const [selectedZone, setSelectedZone] = useState<SceneZone | null>(null);
  const [whatIfQuery, setWhatIfQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"simulation" | "financial" | "suggestions">("simulation");

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
        let sseBuffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          sseBuffer += decoder.decode(value, { stream: true });
          const parts = sseBuffer.split("\n\n");
          sseBuffer = parts.pop() ?? "";

          for (const part of parts) {
            for (const line of part.split("\n")) {
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
              } catch { /* incomplete chunk */ }
            }
          }
        }

        if (sseBuffer.trim()) {
          for (const line of sseBuffer.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === "digital_twin_result") {
                setTwinData(event.data as DigitalTwinData);
                setCompletedStages(new Set(stageOrder));
                setCurrentStage(null);
              }
            } catch { /* ignore */ }
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
  };

  const fmt   = (n: number) => new Intl.NumberFormat("en-IN").format(Math.round(n));
  const fmtCr = (n: number) => `₹${(n / 1e7).toFixed(2)} Cr`;
  const fmtL  = (n: number) => `₹${(n / 1e5).toFixed(1)}L`;

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col overflow-hidden bg-slate-50 text-slate-900">

      {/* ── Clean Light Top Bar ── */}
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 py-3 shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white shadow-xs">
            <Factory className="h-4.5 w-4.5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-slate-900">
              AI Factory Digital Twin
            </h1>
            <p className="text-[10px] text-slate-500">
              Real-time 3D factory simulation before investment
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {twinData && (
            <div className="flex items-center gap-1.5 rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1">
              <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[10px] font-bold text-emerald-700">LIVE SIMULATION</span>
            </div>
          )}
          {twinData && (
            <button
              onClick={() => generateTwin(query)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-900 hover:text-white transition-all shadow-2xs"
            >
              <RefreshCw className="h-3 w-3" />
              Regenerate
            </button>
          )}
        </div>
      </div>

      {/* ── Main Layout ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT PANEL (Light Theme Sidebar) ── */}
        <div className="flex w-[330px] shrink-0 flex-col border-r border-slate-200 bg-white overflow-hidden shadow-2xs">

          {/* Query Input */}
          <div className="border-b border-slate-200 p-4 bg-white">
            <form onSubmit={handleSubmit} className="space-y-3">
              <textarea
                ref={textareaRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey))
                    handleSubmit(e as unknown as React.FormEvent);
                }}
                placeholder="Describe your factory idea... e.g. Manufacture 50,000 EV chargers/month in Gujarat, ₹10 crore budget"
                rows={4}
                className="w-full resize-none rounded-xl border border-slate-200 bg-slate-50/50 p-3 text-xs text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900/10 transition-all shadow-2xs"
              />
              <button
                type="submit"
                disabled={isGenerating || !query.trim()}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-bold text-white shadow-md hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 transition-all"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin text-white" />
                    Simulating Factory...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4 text-white" />
                    Generate Digital Twin
                  </>
                )}
              </button>
            </form>

            {/* Examples */}
            {!twinData && !isGenerating && (
              <div className="mt-3.5 space-y-1.5">
                <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-400">
                  Try an example
                </p>
                {EXAMPLE_QUERIES.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => { setQuery(q); generateTwin(q); }}
                    className="group flex w-full items-start gap-2 rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 text-left text-[10px] text-slate-700 hover:border-slate-400 hover:bg-slate-100 hover:text-slate-900 transition-all shadow-2xs"
                  >
                    <ChevronRight className="h-3 w-3 shrink-0 mt-0.5 text-slate-400 group-hover:text-slate-900 transition-colors" />
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Generation Progress */}
          {isGenerating && (
            <div className="border-b border-slate-200 p-4 space-y-2.5 bg-slate-50/80">
              <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-slate-500">
                Generating Simulation...
              </p>
              {STAGES.map((stage) => {
                const isDone   = completedStages.has(stage.id);
                const isActive = currentStage === stage.id;
                return (
                  <div key={stage.id} className="flex items-center gap-3">
                    <div
                      className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full transition-all ${
                        isDone
                          ? "bg-slate-900 text-white"
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
                          ? "text-slate-900 font-semibold"
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
          {twinData && !isGenerating && (
            <div className="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-thin">
              {/* Tab switcher */}
              <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-100 p-1">
                {(["simulation", "financial", "suggestions"] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`flex-1 rounded-md py-1.5 text-[10px] font-bold uppercase tracking-wider transition-all ${
                      activeTab === tab
                        ? "bg-slate-900 text-white shadow-xs"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {tab === "simulation" ? "Sim" : tab === "financial" ? "Finance" : "AI Tips"}
                  </button>
                ))}
              </div>

              {/* SIMULATION TAB */}
              {activeTab === "simulation" && (
                <div className="space-y-2">
                  <GlowStatCard
                    icon={Factory}
                    label="Monthly Output"
                    value={`${fmt(twinData.simulation.effective_throughput_per_month)} units`}
                    sub={`Target: ${fmt(twinData.config.target_monthly_units as number)} units`}
                    color="cyan"
                    success={twinData.simulation.target_met}
                  />
                  <GlowStatCard
                    icon={AlertTriangle}
                    label="Bottleneck"
                    value={twinData.simulation.bottleneck_step}
                    sub={`${fmt(twinData.simulation.bottleneck_capacity_per_day)} units/day limit`}
                    danger
                  />
                  <GlowStatCard
                    icon={Users}
                    label="Total Workers"
                    value={`${twinData.simulation.total_workers} people`}
                    sub="Across all production shifts"
                    color="purple"
                  />
                  <GlowStatCard
                    icon={Zap}
                    label="Power Load"
                    value={`${twinData.simulation.total_power_kw.toFixed(0)} kW`}
                    sub={`${fmtL(twinData.simulation.estimated_monthly_power_cost_inr)}/month`}
                    color="amber"
                  />

                  {/* Machine Utilization */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2.5 shadow-2xs">
                    <div className="flex items-center gap-2">
                      <Cpu className="h-3.5 w-3.5 text-slate-700" />
                      <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500">
                        Machine Utilization
                      </p>
                    </div>
                    {twinData.simulation.step_capacities.map((sc) => (
                      <div key={sc.step_name} className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className={`text-[10px] ${sc.is_bottleneck ? "text-red-700 font-bold" : "text-slate-700"}`}>
                            {sc.step_name} {sc.is_bottleneck && "⚠"}
                          </span>
                          <span className={`text-[10px] font-bold ${sc.is_bottleneck ? "text-red-600" : sc.utilization_percent > 80 ? "text-amber-600" : "text-emerald-700"}`}>
                            {sc.utilization_percent.toFixed(0)}%
                          </span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full transition-all duration-700 ${
                              sc.is_bottleneck
                                ? "bg-red-500"
                                : sc.utilization_percent > 80
                                ? "bg-amber-500"
                                : "bg-slate-900"
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
                  <GlowStatCard
                    icon={IndianRupee}
                    label="Total CAPEX"
                    value={fmtCr(twinData.financials.total_capex_inr)}
                    color="purple"
                  />
                  <GlowStatCard
                    icon={Activity}
                    label="Monthly Revenue"
                    value={fmtL(twinData.financials.monthly_revenue_inr)}
                    sub={`Profit: ${fmtL(twinData.financials.monthly_profit_inr)}/mo`}
                    color="emerald"
                  />
                  <GlowStatCard
                    icon={TrendingUp}
                    label="Gross Margin"
                    value={`${twinData.financials.gross_margin_percent.toFixed(1)}%`}
                    color={twinData.financials.gross_margin_percent > 20 ? "emerald" : "amber"}
                  />
                  <GlowStatCard
                    icon={Target}
                    label="Break-even"
                    value={`${twinData.financials.break_even_months.toFixed(0)} months`}
                    sub={`Annual ROI: ${twinData.financials.annual_roi_percent.toFixed(0)}%`}
                    color={twinData.financials.break_even_months < 30 ? "emerald" : "amber"}
                  />

                  {/* Scenario Comparison */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2 shadow-2xs">
                    <div className="flex items-center gap-2">
                      <BarChart3 className="h-3.5 w-3.5 text-slate-700" />
                      <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500">
                        Scenario Comparison
                      </p>
                    </div>
                    {[
                      { data: twinData.financials.conservative, color: "border-amber-200 bg-amber-50/60", badge: "bg-amber-100 text-amber-800" },
                      { data: twinData.financials.balanced,     color: "border-cyan-200 bg-cyan-50/60",   badge: "bg-cyan-100 text-cyan-800" },
                      { data: twinData.financials.aggressive,   color: "border-emerald-200 bg-emerald-50/60", badge: "bg-emerald-100 text-emerald-800" },
                    ].map(({ data: s, color, badge }) => (
                      <div key={s.label as string} className={`flex items-center justify-between rounded-lg border ${color} px-3 py-2`}>
                        <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider ${badge}`}>
                          {(s.label as string).split(" ")[0]}
                        </span>
                        <div className="flex gap-4 text-right">
                          <div>
                            <p className="text-[9px] text-slate-500">ROI</p>
                            <p className="text-[11px] font-bold text-slate-900">{(s.annual_roi_percent as number).toFixed(0)}%</p>
                          </div>
                          <div>
                            <p className="text-[9px] text-slate-500">B/E</p>
                            <p className="text-[11px] font-bold text-slate-700">{(s.break_even_months as number).toFixed(0)}mo</p>
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
                  <div className="flex items-center gap-2">
                    <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500">
                      AI Optimization Suggestions
                    </p>
                  </div>
                  {twinData.simulation.optimization_suggestions.map((sug, i) => (
                    <div
                      key={i}
                      className="flex gap-2.5 rounded-xl border border-slate-200 bg-white p-3 shadow-2xs"
                    >
                      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-slate-900 text-[9px] font-bold text-white">{i + 1}</span>
                      <p className="text-[11px] text-slate-700 leading-relaxed">{sug}</p>
                    </div>
                  ))}

                  {/* Expert Summary */}
                  <div className="rounded-xl border border-slate-300 bg-slate-100 p-3 shadow-2xs">
                    <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-900 mb-1">
                      Expert AI Summary
                    </p>
                    <p className="text-[11px] text-slate-800 leading-relaxed">
                      {twinData.summary_text}
                    </p>
                  </div>

                  {/* What-If Simulator */}
                  <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2 shadow-2xs">
                    <p className="text-[9px] font-bold uppercase tracking-[0.12em] text-slate-500">
                      What-If Simulator
                    </p>
                    <form onSubmit={handleWhatIf} className="space-y-2">
                      <input
                        type="text"
                        value={whatIfQuery}
                        onChange={(e) => setWhatIfQuery(e.target.value)}
                        placeholder="e.g. double production capacity"
                        className="w-full rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2 text-[11px] text-slate-900 placeholder-slate-400 focus:border-slate-900 focus:bg-white focus:outline-none"
                      />
                      <button
                        type="submit"
                        disabled={isGenerating || !whatIfQuery.trim()}
                        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-[11px] font-bold text-white hover:bg-slate-800 disabled:opacity-40 transition-all shadow-xs"
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

        {/* ── 3D CANVAS AREA (Dedicated Dark 3D Viewport) ── */}
        <div className="relative flex-1 overflow-hidden bg-[#060b16]">

          {/* Empty state */}
          {!twinData && !isGenerating && (
            <div className="flex h-full w-full flex-col items-center justify-center gap-8 text-center px-8">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_#0e1f3a_0%,_#060b16_70%)]" />
              <div
                className="absolute inset-0 opacity-20"
                style={{
                  backgroundImage: "linear-gradient(rgba(6,182,212,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.15) 1px, transparent 1px)",
                  backgroundSize: "40px 40px",
                }}
              />

              <div className="relative z-10 flex flex-col items-center gap-6">
                <div className="relative">
                  <div className="absolute inset-0 rounded-3xl bg-cyan-500/20 blur-3xl scale-150" />
                  <div className="relative flex h-28 w-28 items-center justify-center rounded-2xl border border-cyan-500/30 bg-gradient-to-br from-cyan-500/20 to-blue-600/20 shadow-2xl shadow-cyan-500/20 backdrop-blur">
                    <Factory className="h-14 w-14 text-cyan-400" />
                  </div>
                </div>

                <div className="space-y-2">
                  <h2 className="text-3xl font-black text-white">
                    Build Your{" "}
                    <span className="bg-gradient-to-r from-cyan-400 to-blue-400 bg-clip-text text-transparent">
                      Factory Twin
                    </span>
                  </h2>
                  <p className="max-w-sm text-sm text-slate-400 leading-relaxed">
                    Describe your manufacturing idea on the left. AI will simulate production
                    capacity, detect bottlenecks, model financials, and render your
                    factory in real-time 3D.
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-3 max-w-md w-full">
                  {[
                    { icon: "⚙️", label: "Capacity Simulation",  color: "border-cyan-500/30 bg-cyan-500/5 text-cyan-400" },
                    { icon: "🔴", label: "Bottleneck Detection", color: "border-red-500/30 bg-red-500/5 text-red-400" },
                    { icon: "📊", label: "Financial Modeling",   color: "border-purple-500/30 bg-purple-500/5 text-purple-400" },
                  ].map((f) => (
                    <div
                      key={f.label}
                      className={`rounded-xl border ${f.color} p-4 flex flex-col items-center gap-2 backdrop-blur`}
                    >
                      <span className="text-2xl">{f.icon}</span>
                      <p className={`text-[10px] font-bold uppercase tracking-wider ${f.color.split(" ").pop()}`}>
                        {f.label}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Loading state */}
          {isGenerating && !twinData && (
            <div className="flex h-full w-full flex-col items-center justify-center gap-6">
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_#0e1f3a_0%,_#060b16_70%)]" />
              <div className="relative z-10 flex flex-col items-center gap-6">
                <div className="relative h-36 w-36">
                  <div className="absolute inset-0 animate-ping rounded-full bg-cyan-500/10" style={{ animationDuration: "2s" }} />
                  <div className="absolute inset-2 animate-spin rounded-full border border-transparent border-t-cyan-500 border-r-cyan-500/50" style={{ animationDuration: "1.5s" }} />
                  <div className="absolute inset-5 animate-spin rounded-full border border-transparent border-t-blue-500 border-l-blue-500/50" style={{ animationDuration: "2.5s", animationDirection: "reverse" }} />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Factory className="h-12 w-12 text-cyan-400" />
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold text-white">Generating Your Factory Twin</p>
                  <p className="text-sm text-slate-400 mt-1">
                    {currentStage ? STAGES.find(s => s.id === currentStage)?.label : "Processing..."}
                  </p>
                </div>
                {/* Progress bar */}
                <div className="w-64 h-1 bg-white/[0.06] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full transition-all duration-700"
                    style={{ width: `${((completedStages.size) / STAGES.length) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* 3D Scene — wrapped in Error Boundary */}
          {twinData && (
            <>
              <FactoryErrorBoundary>
                <FactoryCanvas
                  scene={twinData.scene}
                  onZoneClick={setSelectedZone}
                />
              </FactoryErrorBoundary>

              {/* Controls hint */}
              <div className="absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full border border-white/10 bg-black/50 px-4 py-2 text-[10px] font-medium text-slate-400 shadow-xl backdrop-blur-md pointer-events-none">
                🖱 Drag to rotate · Scroll to zoom · Right-drag to pan
              </div>

              {/* Factory label badge */}
              <div className="absolute top-4 left-4 rounded-xl border border-cyan-500/20 bg-black/50 px-3 py-2 backdrop-blur-md">
                <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-cyan-400">Digital Twin</p>
                <p className="text-xs font-semibold text-white mt-0.5 max-w-[200px] truncate">
                  {twinData.query}
                </p>
              </div>

              {/* Throughput badge */}
              <div className="absolute top-4 right-4 rounded-xl border border-emerald-500/20 bg-black/50 px-3 py-2 backdrop-blur-md">
                <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-emerald-400">Throughput</p>
                <p className="text-sm font-bold text-white mt-0.5">
                  {fmt(twinData.simulation.effective_throughput_per_month)}<span className="text-[10px] text-slate-400 ml-1">units/mo</span>
                </p>
              </div>

              {/* Zone info popup */}
              {selectedZone && (
                <div className="absolute bottom-14 right-5 w-72 rounded-2xl border border-white/10 bg-black/70 p-4 shadow-2xl backdrop-blur-xl">
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="text-sm font-bold text-white leading-tight">
                      {selectedZone.name}
                    </h3>
                    <button
                      onClick={() => setSelectedZone(null)}
                      className="text-slate-500 hover:text-white transition-colors text-lg leading-none"
                    >
                      ✕
                    </button>
                  </div>
                  {selectedZone.is_bottleneck && (
                    <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-2.5 py-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
                      <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider">
                        Bottleneck Detected
                      </span>
                    </div>
                  )}
                  <div className="space-y-2">
                    <div className="flex items-center gap-1.5">
                      <div className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: selectedZone.color }} />
                      <span className="text-[10px] font-semibold text-slate-300 capitalize">{selectedZone.zone_type}</span>
                    </div>
                    <div className="border-t border-white/[0.06] pt-2 space-y-1.5">
                      {Object.entries(selectedZone.metadata).map(([k, v]) => (
                        <div key={k} className="flex items-center justify-between">
                          <span className="text-[10px] capitalize text-slate-500">
                            {k.replace(/_/g, " ")}
                          </span>
                          <span className="text-[10px] font-medium text-slate-200">
                            {String(v)}
                          </span>
                        </div>
                      ))}
                    </div>
                    {selectedZone.metadata.description != null && (
                      <p className="text-[10px] text-slate-400 leading-relaxed border-t border-white/[0.06] pt-2">
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
