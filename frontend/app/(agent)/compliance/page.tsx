"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuthStore } from "@/store/use-auth-store";
import {
  ShieldCheck,
  Leaf,
  SunMedium,
  FileText,
  Building2,
  Zap,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Coins,
  Search,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Info,
  Flame,
  Droplets,
  HardHat,
  ArrowRight,
  Loader2,
  Printer,
  Layers,
  SlidersHorizontal,
} from "lucide-react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const INDIAN_STATES = [
  "Maharashtra",
  "Gujarat",
  "Tamil Nadu",
  "Karnataka",
  "Telangana",
  "Uttar Pradesh",
  "Rajasthan",
  "Haryana",
  "Madhya Pradesh",
  "Andhra Pradesh",
  "Punjab",
  "West Bengal",
  "Kerala",
  "Odisha",
  "Delhi NCR",
];

const PRESET_QUERIES = [
  {
    label: "🔋 EV Battery Pack Assembly (Pune)",
    query: "I want to start a 500 units/day EV Lithium-ion battery pack assembly plant in Pune, Maharashtra with 25 workers and 15,000 sq ft shed.",
  },
  {
    label: "🥤 Plastic Injection Molding (Gujarat)",
    query: "Setting up a plastic injection molding and packaging container unit in Ahmedabad, Gujarat with 18 workers, 10,000 sq ft area, and 6,000 kWh monthly power.",
  },
  {
    label: "🍫 Food & Confectionery (Haryana)",
    query: "Establish an automated bakery, biscuit, and confectionery food processing plant in Gurugram, Haryana with 40 workers and 20,000 sq ft shed.",
  },
  {
    label: "💊 Ayurvedic Pharma Formulations (Uttarakhand)",
    query: "Herbal and ayurvedic formulation packaging facility in Haridwar, Uttarakhand with 20 workers, 12,000 sq ft area, dry process without effluent.",
  },
  {
    label: "☀️ Solar PV Module Assembly (Rajasthan)",
    query: "Setting up a solar PV module assembling and testing factory in Jaipur, Rajasthan with 30 workers and 25,000 sq ft built-up area.",
  },
];

interface SectorSummary {
  slug: string;
  title: string;
  category: "Red" | "Orange" | "Green" | "White" | "Blue" | string;
  pollution_index_score: number;
  pollution_index_range: string;
  cpcb_serial_no: string;
  requires_cte: boolean;
  requires_cto: boolean;
  validity_period: string;
  etp_apcd_mandatory: boolean;
  tags: string[];
}

interface PermitItem {
  id: string;
  name: string;
  authority: string;
  category: string;
  mandatory: boolean;
  lead_time_days: number;
  estimated_fee_inr: number;
  description: string;
  documents_required: string[];
}

interface CarbonMetrics {
  scope_1_kg_co2_monthly: number;
  scope_2_kg_co2_monthly: number;
  total_carbon_tons_annual: number;
  emissions_per_unit_kg: number;
  scope_1_breakdown: string;
  scope_2_breakdown: string;
}

interface SolarProjection {
  recommended_capacity_kwp: number;
  estimated_capex_inr: number;
  annual_generation_kwh: number;
  annual_savings_inr: number;
  payback_period_years: number;
  annual_carbon_offset_tons: number;
  lifetime_25yr_savings_inr: number;
  usable_roof_area_sqft: number;
}

interface ComplianceResponse {
  matched_sector: SectorSummary;
  spcb_category: string;
  pollution_index_score: number;
  category_rationale: string;
  star_rating_eligible: boolean;
  required_permits: PermitItem[];
  carbon_metrics: CarbonMetrics;
  solar_projection: SolarProjection;
  compliance_roadmap: string[];
  sector_guidelines_markdown?: string | null;
}

export default function CompliancePage() {
  const { token } = useAuthStore();

  // Natural Language AI Search State
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [showManualParams, setShowManualParams] = useState(false);

  // Search & Master Sector state
  const [sectorsList, setSectorsList] = useState<SectorSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState<SectorSummary | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Form Parameters
  const [stateName, setStateName] = useState("Maharashtra");
  const [monthlyPowerKwh, setMonthlyPowerKwh] = useState(8500);
  const [monthlyDieselLiters, setMonthlyDieselLiters] = useState(250);
  const [workforceCount, setWorkforceCount] = useState(25);
  const [builtUpAreaSqft, setBuiltUpAreaSqft] = useState(15000);
  const [productionUnits, setProductionUnits] = useState(1000);

  // Checkboxes
  const [hasChemicalTreatment, setHasChemicalTreatment] = useState(false);
  const [hasEffluentDischarge, setHasEffluentDischarge] = useState(false);
  const [hasSteamBoiler, setHasSteamBoiler] = useState(false);

  // Assessment Results
  const [loading, setLoading] = useState(false);
  const [assessment, setAssessment] = useState<ComplianceResponse | null>(null);
  const [expandedPermits, setExpandedPermits] = useState<Record<string, boolean>>({});
  const [showFullGuideline, setShowFullGuideline] = useState(false);

  // Fetch initial sectors for autocomplete
  const fetchSectors = useCallback(async (query = "") => {
    try {
      const res = await fetch(`${API_URL}/api/compliance/sectors?q=${encodeURIComponent(query)}&limit=20`);
      if (res.ok) {
        const data = await res.json();
        setSectorsList(data);
      }
    } catch (err) {
      console.error("Failed to load CPCB sectors", err);
    }
  }, []);

  useEffect(() => {
    fetchSectors();
  }, [fetchSectors]);

  // Handle outside click for sector dropdown
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Natural Language AI Assessment
  const handleAIQuerySubmit = async (queryText?: string) => {
    const textToSearch = (queryText ?? aiPrompt).trim();
    if (!textToSearch) {
      toast.error("Please enter a description of the factory you wish to establish.");
      return;
    }

    setAiLoading(true);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/compliance/ai-query`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query: textToSearch }),
      });

      if (!res.ok) {
        throw new Error(`AI analysis failed with status: ${res.status}`);
      }

      const data: ComplianceResponse = await res.json();
      setAssessment(data);

      if (data.matched_sector) {
        setSelectedSector(data.matched_sector);
        setSearchQuery(data.matched_sector.title);
      }

      toast.success("AI successfully parsed factory details & generated compliance roadmap!");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to run AI assessment";
      toast.error(message);
    } finally {
      setAiLoading(false);
      setLoading(false);
    }
  };

  // Run assessment on manual form submit
  const handleRunAssessment = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoading(true);

    try {
      const payload = {
        industry_slug: selectedSector?.slug ?? null,
        custom_industry_text: searchQuery || selectedSector?.title || aiPrompt || "Manufacturing Unit",
        state: stateName,
        monthly_power_kwh: Number(monthlyPowerKwh),
        monthly_diesel_liters: Number(monthlyDieselLiters),
        workforce_count: Number(workforceCount),
        built_up_area_sqft: Number(builtUpAreaSqft),
        monthly_production_units: Number(productionUnits),
        has_chemical_treatment: hasChemicalTreatment,
        has_effluent_discharge: hasEffluentDischarge,
        has_steam_boiler: hasSteamBoiler,
      };

      const res = await fetch(`${API_URL}/api/compliance/assess`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`Assessment failed with status: ${res.status}`);
      }

      const data: ComplianceResponse = await res.json();
      setAssessment(data);
      toast.success("Environmental & ESG assessment generated successfully!");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to run assessment";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const togglePermit = (id: string) => {
    setExpandedPermits((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Category styling helper
  const getCategoryTheme = (cat: string) => {
    switch (cat.toLowerCase()) {
      case "red":
        return {
          bg: "bg-rose-50",
          border: "border-rose-200",
          text: "text-rose-700",
          pill: "bg-rose-600 text-white",
          subtlePill: "bg-rose-100 text-rose-800",
          badgeBorder: "border-rose-300",
        };
      case "orange":
        return {
          bg: "bg-amber-50",
          border: "border-amber-200",
          text: "text-amber-800",
          pill: "bg-amber-600 text-white",
          subtlePill: "bg-amber-100 text-amber-800",
          badgeBorder: "border-amber-300",
        };
      case "green":
        return {
          bg: "bg-emerald-50",
          border: "border-emerald-200",
          text: "text-emerald-800",
          pill: "bg-emerald-600 text-white",
          subtlePill: "bg-emerald-100 text-emerald-800",
          badgeBorder: "border-emerald-300",
        };
      case "white":
        return {
          bg: "bg-slate-50",
          border: "border-slate-200",
          text: "text-slate-800",
          pill: "bg-slate-700 text-white",
          subtlePill: "bg-slate-100 text-slate-800",
          badgeBorder: "border-slate-300",
        };
      case "blue":
        return {
          bg: "bg-sky-50",
          border: "border-sky-200",
          text: "text-sky-800",
          pill: "bg-sky-600 text-white",
          subtlePill: "bg-sky-100 text-sky-800",
          badgeBorder: "border-sky-300",
        };
      default:
        return {
          bg: "bg-zinc-50",
          border: "border-zinc-200",
          text: "text-zinc-800",
          pill: "bg-zinc-700 text-white",
          subtlePill: "bg-zinc-100 text-zinc-800",
          badgeBorder: "border-zinc-300",
        };
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-[#F8F7F4] p-4 md:p-8">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* ── Top Header ── */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-zinc-200 pb-5">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 text-white shadow-sm">
                <ShieldCheck className="h-4 w-4" />
              </span>
              <h1 className="text-xl md:text-2xl font-bold tracking-tight text-zinc-900">
                ESG, Carbon Footprint & Regulatory Compliance Tracker
              </h1>
            </div>
            <p className="mt-1 text-xs md:text-sm text-zinc-500">
              India-first statutory clearance engine (CPCB 419 Sectors, CTE/CTO, DISH, Fire NOC) + Scope 1/2 GHG & Solar Payback Optimizer.
            </p>
          </div>

          {assessment && (
            <button
              onClick={() => window.print()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 transition"
            >
              <Printer className="h-3.5 w-3.5" />
              Print Report
            </button>
          )}
        </div>

        {/* ── 1. AI NATURAL LANGUAGE SEARCH BOX (PRIMARY) ── */}
        <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50/70 via-white to-white p-5 md:p-6 shadow-sm">
          <div className="flex items-center justify-between gap-2 mb-2">
            <h2 className="text-sm font-bold uppercase tracking-wider text-emerald-900 flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-emerald-600" />
              AI Factory Compliance Consultant
            </h2>
            <span className="text-[11px] font-medium text-emerald-700 bg-emerald-100/60 px-2.5 py-0.5 rounded-full">
              419 CPCB Sectors Knowledge Base
            </span>
          </div>

          <p className="text-xs text-zinc-600 mb-3">
            Describe the manufacturing unit you want to establish. Our AI parses the process, matches official CPCB guidelines, and generates your complete legal & clean energy roadmap.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleAIQuerySubmit();
            }}
            className="space-y-3"
          >
            <div className="relative">
              <textarea
                rows={3}
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="e.g., I want to open a 500 units/day EV battery pack assembly facility in Pune, Maharashtra with 25 workers, 15,000 sq ft shed, and around 8,500 kWh power..."
                className="w-full rounded-xl border border-zinc-300 bg-white p-3.5 text-sm text-zinc-900 placeholder-zinc-400 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 shadow-inner"
              />
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              {/* Preset suggestion chips */}
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[11px] font-medium text-zinc-500">Quick Prompts:</span>
                {PRESET_QUERIES.map((preset, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      setAiPrompt(preset.query);
                      handleAIQuerySubmit(preset.query);
                    }}
                    className="rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-[11px] font-medium text-zinc-700 hover:border-emerald-400 hover:bg-emerald-50/60 transition shadow-xs"
                  >
                    {preset.label}
                  </button>
                ))}
              </div>

              {/* Action Button */}
              <button
                type="submit"
                disabled={aiLoading || !aiPrompt.trim()}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-zinc-900 px-6 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-zinc-800 focus:outline-none transition disabled:opacity-50"
              >
                {aiLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Analyzing Factory Query...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 text-emerald-400" />
                    Assess with AI
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Toggle Manual Parameters */}
          <div className="mt-4 pt-3 border-t border-emerald-100 flex items-center justify-between text-xs">
            <span className="text-zinc-500">Want to fine-tune power, workers, or specific chemical overrides?</span>
            <button
              type="button"
              onClick={() => setShowManualParams(!showManualParams)}
              className="inline-flex items-center gap-1 font-semibold text-emerald-700 hover:text-emerald-800 transition"
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
              {showManualParams ? "Hide Detailed Parameters" : "Fine-Tune Parameters Manually"}
            </button>
          </div>
        </div>

        {/* ── 2. DETAILED PARAMETERS PANEL (COLLAPSIBLE) ── */}
        {showManualParams && (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm space-y-4 transition-all">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-500 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-emerald-600" />
              Manual Sector Selection & Operational Parameters
            </h2>

            <form onSubmit={handleRunAssessment} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Sector Autocomplete Search */}
                <div className="relative md:col-span-2" ref={dropdownRef}>
                  <label className="block text-xs font-medium text-zinc-700 mb-1">
                    CPCB Industrial Sector (Search 419 Sectors)
                  </label>
                  <div className="relative">
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => {
                        setSearchQuery(e.target.value);
                        setSelectedSector(null);
                        fetchSectors(e.target.value);
                        setIsDropdownOpen(true);
                      }}
                      onFocus={() => setIsDropdownOpen(true)}
                      placeholder="Search official CPCB sectors (e.g. Battery, Automobile, Food, Plastic)..."
                      className="w-full rounded-lg border border-zinc-300 bg-white px-3.5 py-2 pl-9 text-sm text-zinc-900 placeholder-zinc-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    />
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
                    {selectedSector && (
                      <span
                        className={`absolute right-2.5 top-2 px-2 py-0.5 text-xs rounded-full font-medium ${
                          getCategoryTheme(selectedSector.category).subtlePill
                        }`}
                      >
                        {selectedSector.category} Category (PI: {selectedSector.pollution_index_score})
                      </span>
                    )}
                  </div>

                  {/* Dropdown Menu */}
                  {isDropdownOpen && sectorsList.length > 0 && (
                    <div className="absolute z-50 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-zinc-200 bg-white py-1 shadow-lg">
                      {sectorsList.map((item) => {
                        const theme = getCategoryTheme(item.category);
                        return (
                          <button
                            key={item.slug}
                            type="button"
                            onClick={() => {
                              setSelectedSector(item);
                              setSearchQuery(item.title);
                              setIsDropdownOpen(false);
                            }}
                            className="flex w-full items-center justify-between px-3.5 py-2 text-left text-xs hover:bg-zinc-50 border-b border-zinc-100 last:border-none"
                          >
                            <span className="truncate font-medium text-zinc-800 pr-2">
                              {item.title}
                            </span>
                            <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${theme.subtlePill}`}>
                              {item.category} (PI: {item.pollution_index_score})
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* State Selection */}
                <div>
                  <label className="block text-xs font-medium text-zinc-700 mb-1">
                    Plant Location (State)
                  </label>
                  <select
                    value={stateName}
                    onChange={(e) => setStateName(e.target.value)}
                    className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  >
                    {INDIAN_STATES.map((st) => (
                      <option key={st} value={st}>
                        {st}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Numerical Inputs */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 pt-2">
                <div>
                  <label className="block text-[11px] font-medium text-zinc-600 mb-1">
                    Monthly Power (kWh)
                  </label>
                  <input
                    type="number"
                    value={monthlyPowerKwh}
                    onChange={(e) => setMonthlyPowerKwh(Number(e.target.value))}
                    min={100}
                    className="w-full rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-zinc-600 mb-1">
                    Backup Diesel (L/month)
                  </label>
                  <input
                    type="number"
                    value={monthlyDieselLiters}
                    onChange={(e) => setMonthlyDieselLiters(Number(e.target.value))}
                    min={0}
                    className="w-full rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-zinc-600 mb-1">
                    Workforce (Employees)
                  </label>
                  <input
                    type="number"
                    value={workforceCount}
                    onChange={(e) => setWorkforceCount(Number(e.target.value))}
                    min={1}
                    className="w-full rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-zinc-600 mb-1">
                    Factory Shed (sq. ft)
                  </label>
                  <input
                    type="number"
                    value={builtUpAreaSqft}
                    onChange={(e) => setBuiltUpAreaSqft(Number(e.target.value))}
                    min={500}
                    className="w-full rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-medium text-zinc-600 mb-1">
                    Monthly Output (Units)
                  </label>
                  <input
                    type="number"
                    value={productionUnits}
                    onChange={(e) => setProductionUnits(Number(e.target.value))}
                    min={1}
                    className="w-full rounded-lg border border-zinc-300 px-3 py-1.5 text-xs text-zinc-900 focus:border-emerald-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* Checkbox overrides */}
              <div className="flex flex-wrap items-center gap-4 pt-2 border-t border-zinc-100 text-xs">
                <label className="flex items-center gap-2 cursor-pointer text-zinc-700">
                  <input
                    type="checkbox"
                    checked={hasChemicalTreatment}
                    onChange={(e) => setHasChemicalTreatment(e.target.checked)}
                    className="rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="flex items-center gap-1">
                    <Flame className="h-3.5 w-3.5 text-rose-500" />
                    Involves Acid/Electroplating Chemical Treatment
                  </span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer text-zinc-700">
                  <input
                    type="checkbox"
                    checked={hasEffluentDischarge}
                    onChange={(e) => setHasEffluentDischarge(e.target.checked)}
                    className="rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="flex items-center gap-1">
                    <Droplets className="h-3.5 w-3.5 text-sky-500" />
                    Generates Industrial Trade Effluent
                  </span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer text-zinc-700">
                  <input
                    type="checkbox"
                    checked={hasSteamBoiler}
                    onChange={(e) => setHasSteamBoiler(e.target.checked)}
                    className="rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                  />
                  <span className="flex items-center gap-1">
                    <HardHat className="h-3.5 w-3.5 text-amber-500" />
                    Uses High-Pressure Steam Boiler
                  </span>
                </label>
              </div>

              {/* Submit Action */}
              <div className="pt-2 flex justify-end">
                <button
                  type="submit"
                  disabled={loading}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 focus:outline-none transition disabled:opacity-50"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Running CPCB Classifier & Carbon Math...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      Update Assessment
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ── 3. ASSESSMENT RESULTS ── */}
        {assessment && (
          <div className="space-y-6">
            {/* Category Classification Banner */}
            {(() => {
              const theme = getCategoryTheme(assessment.spcb_category);
              return (
                <div className={`rounded-xl border ${theme.border} ${theme.bg} p-6 shadow-sm`}>
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`px-3 py-1 text-xs font-bold uppercase rounded-md tracking-wider ${theme.pill}`}>
                          {assessment.spcb_category} Category
                        </span>
                        <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-white border border-zinc-200 text-zinc-800">
                          CPCB Pollution Index: {assessment.pollution_index_score} / 100
                        </span>
                        {assessment.matched_sector.cpcb_serial_no && (
                          <span className="text-xs text-zinc-500 px-2 py-1">
                            Ref: {assessment.matched_sector.cpcb_serial_no}
                          </span>
                        )}
                        {assessment.star_rating_eligible && (
                          <span className="text-xs font-medium px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                            ★ Star-Rating Incentive Eligible
                          </span>
                        )}
                      </div>

                      <h3 className="text-lg md:text-xl font-bold text-zinc-900">
                        {assessment.matched_sector.title}
                      </h3>
                      <p className="text-sm text-zinc-600 leading-relaxed max-w-3xl">
                        {assessment.category_rationale}
                      </p>
                    </div>

                    <div className="shrink-0 flex flex-col gap-1.5 text-xs text-zinc-600 bg-white/80 p-3 rounded-lg border border-zinc-200">
                      <div>
                        <strong>CTE Required:</strong>{" "}
                        <span className={assessment.matched_sector.requires_cte ? "text-rose-600 font-semibold" : "text-emerald-600 font-semibold"}>
                          {assessment.matched_sector.requires_cte ? "Yes (Mandatory)" : "Exempt"}
                        </span>
                      </div>
                      <div>
                        <strong>CTO Required:</strong>{" "}
                        <span className={assessment.matched_sector.requires_cto ? "text-rose-600 font-semibold" : "text-emerald-600 font-semibold"}>
                          {assessment.matched_sector.requires_cto ? "Yes (Mandatory)" : "Exempt"}
                        </span>
                      </div>
                      <div>
                        <strong>Consent Validity:</strong> {assessment.matched_sector.validity_period}
                      </div>
                      <div>
                        <strong>ETP/APCD System:</strong>{" "}
                        <span className={assessment.matched_sector.etp_apcd_mandatory ? "text-rose-600 font-medium" : "text-zinc-600"}>
                          {assessment.matched_sector.etp_apcd_mandatory ? "Mandatory Dedicated ETP/APCD" : "Standard Safeguards"}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()}

            {/* Key Metrics Grid: Carbon Footprint & Rooftop Solar */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Carbon Footprint Card */}
              <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="p-2 rounded-lg bg-emerald-50 text-emerald-700">
                      <Leaf className="h-4 w-4" />
                    </span>
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-900">Carbon Footprint (GHG)</h3>
                      <p className="text-[11px] text-zinc-500">Scope 1 & Scope 2 Operational Emissions</p>
                    </div>
                  </div>
                  <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-1 rounded">
                    {assessment.carbon_metrics.total_carbon_tons_annual} Tons CO₂e / Year
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-zinc-50 border border-zinc-100">
                    <span className="text-[11px] font-medium text-zinc-500 block">Scope 1 (Diesel DG Sets)</span>
                    <span className="text-base font-bold text-zinc-900">
                      {assessment.carbon_metrics.scope_1_kg_co2_monthly.toLocaleString()} <span className="text-xs font-normal text-zinc-500">kg/mo</span>
                    </span>
                    <span className="text-[10px] text-zinc-400 block mt-1 truncate">
                      {assessment.carbon_metrics.scope_1_breakdown}
                    </span>
                  </div>

                  <div className="p-3 rounded-lg bg-zinc-50 border border-zinc-100">
                    <span className="text-[11px] font-medium text-zinc-500 block">Scope 2 (Grid Electricity)</span>
                    <span className="text-base font-bold text-zinc-900">
                      {assessment.carbon_metrics.scope_2_kg_co2_monthly.toLocaleString()} <span className="text-xs font-normal text-zinc-500">kg/mo</span>
                    </span>
                    <span className="text-[10px] text-zinc-400 block mt-1 truncate">
                      {assessment.carbon_metrics.scope_2_breakdown}
                    </span>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-emerald-50/60 border border-emerald-100 flex items-center justify-between">
                  <div className="text-xs">
                    <strong className="text-emerald-900">Carbon Intensity Per Product:</strong>
                    <p className="text-[11px] text-emerald-700">Estimated carbon embodied per finished manufactured unit</p>
                  </div>
                  <span className="text-sm font-bold text-emerald-900">
                    {assessment.carbon_metrics.emissions_per_unit_kg} kg CO₂e / unit
                  </span>
                </div>
              </div>

              {/* Rooftop Solar Optimizer Card */}
              <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="p-2 rounded-lg bg-amber-50 text-amber-700">
                      <SunMedium className="h-4 w-4" />
                    </span>
                    <div>
                      <h3 className="text-sm font-semibold text-zinc-900">Rooftop Solar & Power Optimizer</h3>
                      <p className="text-[11px] text-zinc-500">
                        {assessment.solar_projection.usable_roof_area_sqft.toLocaleString()} sq. ft usable shadow-free roof
                      </p>
                    </div>
                  </div>
                  <span className="text-xs font-bold text-amber-800 bg-amber-50 px-2 py-1 rounded">
                    Payback: {assessment.solar_projection.payback_period_years} Years
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-100">
                    <span className="text-[11px] text-zinc-500 block">Recommended Plant</span>
                    <span className="text-sm font-bold text-zinc-900">
                      {assessment.solar_projection.recommended_capacity_kwp} <span className="text-xs font-normal">kWp</span>
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-100">
                    <span className="text-[11px] text-zinc-500 block">Estimated CAPEX</span>
                    <span className="text-sm font-bold text-zinc-900">
                      ₹{(assessment.solar_projection.estimated_capex_inr / 100000).toFixed(1)} <span className="text-xs font-normal">Lakhs</span>
                    </span>
                  </div>

                  <div className="p-2.5 rounded-lg bg-zinc-50 border border-zinc-100">
                    <span className="text-[11px] text-zinc-500 block">Annual Bill Savings</span>
                    <span className="text-sm font-bold text-emerald-600">
                      ₹{(assessment.solar_projection.annual_savings_inr / 100000).toFixed(1)} <span className="text-xs font-normal">Lakhs</span>
                    </span>
                  </div>
                </div>

                {/* Progress bar visual for payback */}
                <div className="space-y-1.5">
                  <div className="flex justify-between text-[11px] text-zinc-500">
                    <span>Payback Timeline: {assessment.solar_projection.payback_period_years} of 25 Year Asset Life</span>
                    <span className="font-semibold text-emerald-600">
                      25-Yr Net Profit: ₹{(assessment.solar_projection.lifetime_25yr_savings_inr / 100000).toFixed(1)} Lakhs
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-zinc-100 overflow-hidden">
                    <div
                      className="h-full bg-amber-500 rounded-full"
                      style={{
                        width: `${Math.min(100, (assessment.solar_projection.payback_period_years / 25) * 100)}%`,
                      }}
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] text-zinc-500 bg-amber-50/60 p-2 rounded-lg border border-amber-100">
                  <span className="flex items-center gap-1 text-amber-900 font-medium">
                    <Zap className="h-3.5 w-3.5 text-amber-600" />
                    Clean Generation: {assessment.solar_projection.annual_generation_kwh.toLocaleString()} kWh/yr
                  </span>
                  <span className="text-amber-800">
                    Offsets {assessment.solar_projection.annual_carbon_offset_tons} Tons CO₂e annually
                  </span>
                </div>
              </div>
            </div>

            {/* Statutory Clearances & Required Permits Checklist */}
            <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
                <div className="flex items-center gap-2">
                  <span className="p-2 rounded-lg bg-zinc-900 text-white">
                    <FileText className="h-4 w-4" />
                  </span>
                  <div>
                    <h3 className="text-base font-bold text-zinc-900">
                      Required Statutory Approvals & Permits Checklist
                    </h3>
                    <p className="text-xs text-zinc-500">
                      Mandatory government clearances under Water Act, Air Act, Factories Act, and Fire Safety
                    </p>
                  </div>
                </div>
                <span className="text-xs font-semibold px-2.5 py-1 rounded bg-zinc-100 text-zinc-700">
                  {assessment.required_permits.length} Clearances Identified
                </span>
              </div>

              <div className="space-y-3">
                {assessment.required_permits.map((permit) => {
                  const isOpen = !!expandedPermits[permit.id];
                  return (
                    <div
                      key={permit.id}
                      className="rounded-lg border border-zinc-200 bg-white transition hover:border-zinc-300"
                    >
                      <div
                        onClick={() => togglePermit(permit.id)}
                        className="flex cursor-pointer items-center justify-between p-3.5 text-left"
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                              permit.mandatory ? "bg-rose-100 text-rose-700" : "bg-zinc-100 text-zinc-600"
                            }`}
                          >
                            {permit.mandatory ? "!" : "i"}
                          </span>
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="text-sm font-semibold text-zinc-900">{permit.name}</h4>
                              <span className="rounded bg-zinc-100 px-2 py-0.5 text-[10px] font-medium text-zinc-600">
                                {permit.category}
                              </span>
                            </div>
                            <span className="text-xs text-zinc-500">{permit.authority}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-4">
                          <div className="hidden sm:flex flex-col text-right text-xs">
                            <span className="font-semibold text-zinc-800">
                              {permit.estimated_fee_inr > 0 ? `₹${permit.estimated_fee_inr.toLocaleString()}` : "Zero Govt Fee"}
                            </span>
                            <span className="text-[11px] text-zinc-500 flex items-center gap-1 justify-end">
                              <Clock className="h-3 w-3" /> {permit.lead_time_days} Days
                            </span>
                          </div>
                          {isOpen ? <ChevronUp className="h-4 w-4 text-zinc-400" /> : <ChevronDown className="h-4 w-4 text-zinc-400" />}
                        </div>
                      </div>

                      {isOpen && (
                        <div className="border-t border-zinc-100 bg-zinc-50/50 p-4 space-y-3 text-xs text-zinc-700">
                          <p>{permit.description}</p>

                          <div>
                            <strong className="block text-[11px] uppercase tracking-wider text-zinc-500 mb-1.5">
                              Mandatory Documentation Required:
                            </strong>
                            <ul className="grid grid-cols-1 md:grid-cols-2 gap-1.5">
                              {permit.documents_required.map((doc, idx) => (
                                <li key={idx} className="flex items-center gap-2 text-zinc-600">
                                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
                                  <span>{doc}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Strategic Compliance Roadmap */}
            <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm space-y-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-800 flex items-center gap-2">
                <Layers className="h-4 w-4 text-emerald-600" />
                Strategic Statutory Roadmap
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                {assessment.compliance_roadmap.map((step, idx) => (
                  <div key={idx} className="p-3 rounded-lg bg-zinc-50 border border-zinc-100 text-xs text-zinc-700 space-y-1">
                    <span className="inline-block px-1.5 py-0.5 rounded bg-zinc-200 font-bold text-[10px] text-zinc-800 mb-1">
                      Step {idx + 1}
                    </span>
                    <p>{step.replace(/^\d+\.\s*/, "")}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* CPCB Sector Guidelines (OKF Markdown Section) */}
            {assessment.sector_guidelines_markdown && (
              <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-zinc-100 pb-2">
                  <h3 className="text-sm font-bold text-zinc-900 flex items-center gap-2">
                    <FileText className="h-4 w-4 text-emerald-600" />
                    CPCB Technical Mitigation Guidelines ({assessment.matched_sector.title})
                  </h3>
                  <button
                    onClick={() => setShowFullGuideline(!showFullGuideline)}
                    className="text-xs font-medium text-emerald-600 hover:text-emerald-700"
                  >
                    {showFullGuideline ? "Collapse Guide" : "Expand Full Guide"}
                  </button>
                </div>

                <div
                  className={`prose prose-sm max-w-none text-zinc-700 ${
                    showFullGuideline ? "" : "max-h-60 overflow-hidden relative"
                  }`}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {assessment.sector_guidelines_markdown}
                  </ReactMarkdown>
                  {!showFullGuideline && (
                    <div className="absolute bottom-0 inset-x-0 h-16 bg-gradient-to-t from-white to-transparent pointer-events-none" />
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
