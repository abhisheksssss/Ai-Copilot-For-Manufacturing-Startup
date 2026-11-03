"use client";

import { FormEvent, useState, useEffect } from "react";
import {
  ExternalLink,
  LandPlot,
  Loader2,
  MapPin,
  Search,
  Sparkles,
  Factory,
  Zap,
  Building2,
  ShieldCheck,
  Truck,
  Users,
  Coins,
  ArrowRight,
  Compass,
  CheckCircle2,
  Layers,
} from "lucide-react";
import { toast } from "sonner";

import {
  searchIndustryLocations,
  recommendOptimalLocation,
  fetchLocationStates,
  type LocationSearchResponse,
} from "@/lib/api";
import { useAuthStore } from "@/store/use-auth-store";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const RECOMMENDATION_PRESETS = [
  {
    label: "🔋 EV Lithium-Ion Battery Pack",
    query: "I want to start a 500 units/day EV Lithium-ion battery pack assembly plant with 25 workers and 15,000 sq ft shed",
  },
  {
    label: "🍪 Confectionery & Bakery",
    query: "Automated bakery, biscuit, and confectionery food processing plant with 40 workers",
  },
  {
    label: "☀️ Solar PV Module Testing & Assembly",
    query: "Setting up a solar PV module assembling and testing factory with 30 workers and 25,000 sq ft built-up area",
  },
  {
    label: "💊 Herbal & Ayurvedic Formulations",
    query: "Herbal and ayurvedic formulation packaging facility with 20 workers, 12,000 sq ft area, dry process without effluent",
  },
  {
    label: "🧴 Plastic Injection Molding",
    query: "Plastic injection molding and packaging container unit with 18 workers, 10,000 sq ft area",
  },
];

const SPECIFIC_LOCATION_PRESETS = [
  {
    label: "📍 Surat, Gujarat (Textiles)",
    query: "Textile park in Surat",
    state: "Gujarat",
  },
  {
    label: "📍 Pune, Maharashtra (Auto & Engineering)",
    query: "Chakan auto cluster in Pune",
    state: "Maharashtra",
  },
  {
    label: "📍 Haridwar, Uttarakhand (Pharma & Ayurveda)",
    query: "SIIDCUL Industrial Estate in Haridwar",
    state: "Uttarakhand",
  },
  {
    label: "📍 Ahmedabad, Gujarat (Plastics & Solar)",
    query: "Sanand GIDC in Ahmedabad",
    state: "Gujarat",
  },
  {
    label: "📍 Sriperumbudur, Tamil Nadu (Electronics)",
    query: "Electronics manufacturing in Sriperumbudur",
    state: "Tamil Nadu",
  },
];

const DEFAULT_INDIAN_STATES = [
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
  "Uttarakhand",
  "Himachal Pradesh",
  "Odisha",
  "Delhi",
];

export default function LocationFinderPage() {
  const { token } = useAuthStore();

  // Active Tab: "recommendation" | "specific"
  const [activeTab, setActiveTab] = useState<"recommendation" | "specific">("recommendation");

  // Common State
  const [availableStates, setAvailableStates] = useState<string[]>(DEFAULT_INDIAN_STATES);
  const [isSearching, setIsSearching] = useState(false);
  const [response, setResponse] = useState<LocationSearchResponse | null>(null);

  // Portion 1: Recommendation Advisor State
  const [recQuery, setRecQuery] = useState(
    "I want to start a 500 units/day EV Lithium-ion battery pack assembly plant with 25 workers and 15,000 sq ft shed"
  );
  const [recStatePref, setRecStatePref] = useState("All India");

  // Portion 2: Specific Location State
  const [specQuery, setSpecQuery] = useState("Textile park in Surat");
  const [specState, setSpecState] = useState("");

  // Load 35 states from backend catalogue
  useEffect(() => {
    if (!token) return;
    fetchLocationStates(token)
      .then((states) => {
        if (Array.isArray(states) && states.length > 0) {
          setAvailableStates(states);
        }
      })
      .catch(() => {
        // Fallback to default list
      });
  }, [token]);

  // Handle Recommendation Submit
  async function handleRecommendationSubmit(event?: FormEvent) {
    if (event) event.preventDefault();
    if (!token) return;
    const clean = recQuery.trim();
    if (clean.length < 2) {
      toast.error("Enter your plant or industry specifications.");
      return;
    }

    setIsSearching(true);
    try {
      const stateFilter = recStatePref === "All India" ? null : recStatePref;
      const res = await recommendOptimalLocation(clean, token, {
        state_preference: stateFilter,
        limit: 5,
        enrich: true,
      });
      setResponse(res);
      toast.success("Optimal location recommendation generated!");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not generate location recommendation");
    } finally {
      setIsSearching(false);
    }
  }

  // Handle Specific Location Submit
  async function handleSpecificSubmit(event?: FormEvent) {
    if (event) event.preventDefault();
    if (!token) return;
    const clean = specQuery.trim();
    if (clean.length < 2) {
      toast.error("Enter a target district, city, or park name.");
      return;
    }

    setIsSearching(true);
    try {
      const stateFilter = specState || null;
      const res = await searchIndustryLocations(clean, token, {
        state_filter: stateFilter,
        mode: "specific",
        limit: 5,
        enrich: true,
      });
      setResponse(res);
      toast.success("Found industrial parks for your location!");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not search industrial locations");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8 sm:px-8 space-y-8">
      {/* Page Header */}
      <div className="max-w-3xl space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full w-fit border border-emerald-200">
          <Compass className="h-3.5 w-3.5" /> India Industrial Land Bank (IILB) Intelligence
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">
          Factory Location & Siting Advisor
        </h1>
        <p className="text-sm text-zinc-600 leading-relaxed">
          Discover the single most optimal manufacturing cluster for your product in India with deep supply chain & state subsidy rationales, or explore 3,993+ government-verified industrial parks in your chosen target state.
        </p>
      </div>

      {/* Two Separate Portions Tab Switcher */}
      <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-zinc-100/90 border border-zinc-200/80 max-w-xl">
        <button
          type="button"
          onClick={() => {
            setActiveTab("recommendation");
            setResponse(null);
          }}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs sm:text-sm font-semibold transition-all duration-150 ${
            activeTab === "recommendation"
              ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/60"
              : "text-zinc-600 hover:text-zinc-900 hover:bg-white/50"
          }`}
        >
          <Sparkles className={`h-4 w-4 ${activeTab === "recommendation" ? "text-amber-500" : "text-zinc-400"}`} />
          <span>AI Optimal Location Advisor</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveTab("specific");
            setResponse(null);
          }}
          className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs sm:text-sm font-semibold transition-all duration-150 ${
            activeTab === "specific"
              ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/60"
              : "text-zinc-600 hover:text-zinc-900 hover:bg-white/50"
          }`}
        >
          <MapPin className={`h-4 w-4 ${activeTab === "specific" ? "text-emerald-600" : "text-zinc-400"}`} />
          <span>Specific Location Explorer</span>
        </button>
      </div>

      {/* PORTION 1: AI Optimal Location Advisor */}
      {activeTab === "recommendation" && (
        <Card className="border-zinc-200/90 shadow-sm bg-gradient-to-br from-white via-zinc-50/30 to-amber-50/20">
          <CardHeader className="pb-3 border-b border-zinc-100">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base font-bold text-zinc-900 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-amber-500" />
                  Generate Optimal Location Recommendation
                </CardTitle>
                <p className="text-xs text-zinc-500 mt-1">
                  Describe what you want to manufacture. Our engine evaluates supplier density, state policies, port logistics, and SPCB clearance speed to recommend the #1 industrial cluster.
                </p>
              </div>
              <Badge className="bg-amber-50 text-amber-800 border-amber-200 shrink-0 text-[11px] font-medium">
                5-Pillar Siting Analysis
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="p-5 space-y-4">
            <form onSubmit={handleRecommendationSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-zinc-700 mb-1.5">
                    Plant & Industry Description
                  </label>
                  <Input
                    value={recQuery}
                    onChange={(e) => setRecQuery(e.target.value)}
                    placeholder="e.g. 500 units/day EV Lithium-ion battery pack assembly plant with 25 workers"
                    className="h-11 bg-white"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-700 mb-1.5">
                    State Preference
                  </label>
                  <select
                    value={recStatePref}
                    onChange={(e) => setRecStatePref(e.target.value)}
                    className="w-full h-11 px-3 text-xs bg-white border border-zinc-200 rounded-md text-zinc-800 focus:outline-hidden focus:ring-2 focus:ring-zinc-900 font-medium"
                  >
                    <option value="All India">All India (Recommend Best)</option>
                    {availableStates.map((st) => (
                      <option key={st} value={st}>
                        Within {st} only
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                <div className="flex flex-wrap gap-1.5 items-center">
                  <span className="text-[11px] font-medium text-zinc-500 mr-1">Quick presets:</span>
                  {RECOMMENDATION_PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => setRecQuery(p.query)}
                      className="rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-[11px] text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50 transition-colors shadow-2xs font-medium"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>

                <Button
                  type="submit"
                  disabled={isSearching}
                  className="h-11 px-6 gap-2 bg-zinc-900 hover:bg-zinc-800 text-white font-medium shrink-0 self-start sm:self-auto"
                >
                  {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4 text-amber-400" />}
                  Generate Recommendation
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* PORTION 2: Specific Location Explorer */}
      {activeTab === "specific" && (
        <Card className="border-zinc-200/90 shadow-sm bg-gradient-to-br from-white via-zinc-50/30 to-emerald-50/20">
          <CardHeader className="pb-3 border-b border-zinc-100">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base font-bold text-zinc-900 flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-emerald-600" />
                  Search Industrial Parks in a Specific Location
                </CardTitle>
                <p className="text-xs text-zinc-500 mt-1">
                  Already decided where to establish your plant? Search saved industrial parks directly by state, district, or park name. No unsolicited relocation advice is provided.
                </p>
              </div>
              <Badge className="bg-emerald-50 text-emerald-800 border-emerald-200 shrink-0 text-[11px] font-medium">
                Fixed Location Mode
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="p-5 space-y-4">
            <form onSubmit={handleSpecificSubmit} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="md:col-span-3">
                  <label className="block text-xs font-semibold text-zinc-700 mb-1.5">
                    Target District, City, or Industrial Park Name
                  </label>
                  <Input
                    value={specQuery}
                    onChange={(e) => setSpecQuery(e.target.value)}
                    placeholder="e.g. Surat, Sanand GIDC, Chakan Industrial Area, Haridwar"
                    className="h-11 bg-white"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-700 mb-1.5">
                    Filter by State (Optional)
                  </label>
                  <select
                    value={specState}
                    onChange={(e) => setSpecState(e.target.value)}
                    className="w-full h-11 px-3 text-xs bg-white border border-zinc-200 rounded-md text-zinc-800 focus:outline-hidden focus:ring-2 focus:ring-zinc-900 font-medium"
                  >
                    <option value="">All States</option>
                    {availableStates.map((st) => (
                      <option key={st} value={st}>
                        {st}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                <div className="flex flex-wrap gap-1.5 items-center">
                  <span className="text-[11px] font-medium text-zinc-500 mr-1">Popular hubs:</span>
                  {SPECIFIC_LOCATION_PRESETS.map((p) => (
                    <button
                      key={p.label}
                      type="button"
                      onClick={() => {
                        setSpecQuery(p.query);
                        setSpecState(p.state);
                      }}
                      className="rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-[11px] text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50 transition-colors shadow-2xs font-medium"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>

                <Button
                  type="submit"
                  disabled={isSearching}
                  className="h-11 px-6 gap-2 bg-zinc-900 hover:bg-zinc-800 text-white font-medium shrink-0 self-start sm:self-auto"
                >
                  {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4 text-emerald-400" />}
                  Search Location
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* RESULTS DISPLAY SECTION */}
      {response && (
        <section className="space-y-6">
          {/* AI OPTIMAL LOCATION RECOMMENDATION HERO (When recommendation is present) */}
          {response.recommendation && (
            <Card className="border-amber-200/80 bg-gradient-to-br from-amber-50/40 via-white to-amber-50/10 shadow-sm overflow-hidden">
              <div className="bg-gradient-to-r from-amber-500 to-amber-600 px-6 py-4 text-white flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase tracking-wider bg-white/20 px-2 py-0.5 rounded">
                      AI Siting Recommendation
                    </span>
                    <span className="text-xs font-semibold text-amber-100">
                      {response.recommendation.sector}
                    </span>
                  </div>
                  <h2 className="text-xl sm:text-2xl font-bold">
                    {response.recommendation.recommended_cluster}
                  </h2>
                  <p className="text-xs text-amber-100 flex items-center gap-1.5">
                    <MapPin className="h-3.5 w-3.5" />
                    <span>
                      {response.recommendation.recommended_district}, {response.recommendation.recommended_state}, India
                    </span>
                  </p>
                </div>

                <div className="bg-white/10 backdrop-blur-xs rounded-xl p-3 border border-white/20 flex sm:flex-col items-center justify-center gap-1 self-start sm:self-auto">
                  <span className="text-2xl sm:text-3xl font-extrabold text-white">
                    {response.recommendation.suitability_score}
                  </span>
                  <span className="text-[10px] font-semibold text-amber-100 uppercase tracking-wider">
                    Suitability Score
                  </span>
                </div>
              </div>

              <CardContent className="p-6 space-y-5">
                {/* Executive Summary */}
                <div className="rounded-xl bg-zinc-50 p-4 border border-zinc-200/80 text-xs sm:text-sm text-zinc-800 leading-relaxed font-medium">
                  <span className="font-bold text-zinc-900 block mb-1">Why this land will be good for you:</span>
                  {response.recommendation.why_recommended_summary}
                </div>

                {/* 5 Industrial Advantage Pillars */}
                <div className="space-y-2.5">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-500 flex items-center gap-1.5">
                    <Layers className="h-3.5 w-3.5 text-amber-600" />
                    5 Industrial Advantage Pillars for your Plant
                  </h3>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                    {/* Pillar 1: Supply Chain */}
                    <div className="rounded-xl border border-zinc-200 bg-white p-3.5 space-y-1.5 shadow-2xs">
                      <div className="flex items-center gap-2 text-xs font-bold text-zinc-900">
                        <div className="h-6 w-6 rounded-md bg-amber-100 text-amber-800 flex items-center justify-center shrink-0">
                          <Zap className="h-3.5 w-3.5" />
                        </div>
                        <span>Supply Chain & OEM Density</span>
                      </div>
                      <p className="text-xs text-zinc-600 leading-relaxed">
                        {response.recommendation.key_advantages.supply_chain_ecosystem}
                      </p>
                    </div>

                    {/* Pillar 2: State Subsidies & Policy */}
                    <div className="rounded-xl border border-zinc-200 bg-white p-3.5 space-y-1.5 shadow-2xs">
                      <div className="flex items-center gap-2 text-xs font-bold text-zinc-900">
                        <div className="h-6 w-6 rounded-md bg-emerald-100 text-emerald-800 flex items-center justify-center shrink-0">
                          <Coins className="h-3.5 w-3.5" />
                        </div>
                        <span>State Policy & Subsidies</span>
                      </div>
                      <p className="text-xs text-zinc-600 leading-relaxed">
                        {response.recommendation.key_advantages.state_subsidies_policy}
                      </p>
                    </div>

                    {/* Pillar 3: Logistics & Port Connectivity */}
                    <div className="rounded-xl border border-zinc-200 bg-white p-3.5 space-y-1.5 shadow-2xs">
                      <div className="flex items-center gap-2 text-xs font-bold text-zinc-900">
                        <div className="h-6 w-6 rounded-md bg-sky-100 text-sky-800 flex items-center justify-center shrink-0">
                          <Truck className="h-3.5 w-3.5" />
                        </div>
                        <span>Logistics & Port Connectivity</span>
                      </div>
                      <p className="text-xs text-zinc-600 leading-relaxed">
                        {response.recommendation.key_advantages.logistics_connectivity}
                      </p>
                    </div>

                    {/* Pillar 4: SPCB Clearances */}
                    <div className="rounded-xl border border-zinc-200 bg-white p-3.5 space-y-1.5 shadow-2xs">
                      <div className="flex items-center gap-2 text-xs font-bold text-zinc-900">
                        <div className="h-6 w-6 rounded-md bg-blue-100 text-blue-800 flex items-center justify-center shrink-0">
                          <ShieldCheck className="h-3.5 w-3.5" />
                        </div>
                        <span>SPCB Siting & Green Clearance</span>
                      </div>
                      <p className="text-xs text-zinc-600 leading-relaxed">
                        {response.recommendation.key_advantages.spcb_clearance_siting}
                      </p>
                    </div>

                    {/* Pillar 5: Skilled Workforce */}
                    <div className="rounded-xl border border-zinc-200 bg-white p-3.5 space-y-1.5 shadow-2xs">
                      <div className="flex items-center gap-2 text-xs font-bold text-zinc-900">
                        <div className="h-6 w-6 rounded-md bg-purple-100 text-purple-800 flex items-center justify-center shrink-0">
                          <Users className="h-3.5 w-3.5" />
                        </div>
                        <span>Skilled Technical Workforce</span>
                      </div>
                      <p className="text-xs text-zinc-600 leading-relaxed">
                        {response.recommendation.key_advantages.skilled_workforce}
                      </p>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* USER SPECIFIED LOCATION BANNER (When location was explicitly requested) */}
          {response.user_specified_location && !response.recommendation && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
              <div className="text-xs space-y-1">
                <p className="font-bold text-emerald-950">
                  Showing verified industrial parks in your requested location: {response.user_specified_location}
                </p>
                <p className="text-emerald-800">
                  Your location preference has been strictly honored. The catalogue below displays government-verified industrial land plots and plug-and-play sheds strictly located in your requested area.
                </p>
              </div>
            </div>
          )}

          {/* CATALOGUE INDUSTRIAL PARKS LIST */}
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200/80 pb-3">
              <div>
                <h3 className="text-base font-bold text-zinc-900">
                  {response.recommendation
                    ? `Top Verified Industrial Parks in ${response.recommendation.recommended_district}, ${response.recommendation.recommended_state}`
                    : `Matching Industrial Parks for “${response.query}”`}
                </h3>
                <p className="text-xs text-zinc-500">
                  Filtered from {response.total_catalogue_locations.toLocaleString()} official parks in the India Industrial Land Bank catalogue.
                </p>
              </div>

              <Badge variant="outline" className="gap-1.5 border-zinc-200 bg-white text-zinc-700 text-xs">
                <Sparkles className="h-3 w-3 text-amber-500" />
                Google Places: {response.google_places_enrichment === "enabled" ? "Enriched" : "Standard"}
              </Badge>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {response.results.map((location, index) => (
                <Card key={location.id} className="border-zinc-200/90 hover:border-zinc-300 transition-all hover:shadow-sm">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-mono font-semibold uppercase tracking-wider text-zinc-400">
                          {response.recommendation ? `Recommended Park #${index + 1}` : `Match #${index + 1}`}
                        </p>
                        <CardTitle className="mt-1 text-base font-bold leading-snug text-zinc-900">
                          {location.name}
                        </CardTitle>
                      </div>
                      <Badge className="shrink-0 bg-zinc-100 text-zinc-800 hover:bg-zinc-100 border border-zinc-200 text-xs">
                        {location.sector}
                      </Badge>
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-4 text-xs">
                    <p className="text-zinc-600 leading-relaxed">{location.summary}</p>

                    <div className="grid grid-cols-2 gap-2.5">
                      <div className="rounded-lg bg-zinc-50 p-2.5 border border-zinc-100">
                        <span className="block text-[10px] text-zinc-500 uppercase font-semibold">Location</span>
                        <span className="font-bold text-zinc-900">{location.district}, {location.state}</span>
                      </div>
                      <div className="rounded-lg bg-zinc-50 p-2.5 border border-zinc-100">
                        <span className="block text-[10px] text-zinc-500 uppercase font-semibold">Available Land</span>
                        <span className="font-bold text-emerald-700">
                          {location.land_available_hectares.toLocaleString()} hectares
                        </span>
                      </div>
                      <div className="rounded-lg bg-zinc-50 p-2.5 border border-zinc-100">
                        <span className="block text-[10px] text-zinc-500 uppercase font-semibold">Park Type</span>
                        <span className="font-medium text-zinc-800">{location.industrial_park_type || "Not specified"}</span>
                      </div>
                      <div className="rounded-lg bg-zinc-50 p-2.5 border border-zinc-100">
                        <span className="block text-[10px] text-zinc-500 uppercase font-semibold">Infrastructure</span>
                        <span className="font-medium text-zinc-800">
                          {location.plug_and_play ? "Plug-and-play Ready" : "Industrial Plot (Greenfield)"}
                        </span>
                      </div>
                    </div>

                    {location.live_place && (
                      <div className="rounded-lg border border-sky-100 bg-sky-50/60 p-2.5 text-sky-950 space-y-1">
                        <p className="font-bold flex items-center gap-1.5">
                          <MapPin className="h-3 w-3 text-sky-600" />
                          <span>Google Places Verified</span>
                        </p>
                        <p className="text-[11px] text-sky-900">{location.live_place.formatted_address || location.live_place.name}</p>
                        {location.live_place.rating != null && (
                          <p className="text-[11px] text-sky-800 font-semibold">
                            Rating: {location.live_place.rating} ({location.live_place.user_rating_count ?? 0} reviews)
                          </p>
                        )}
                      </div>
                    )}

                    <div className="flex flex-wrap gap-1.5">
                      {location.match_reasons.map((reason) => (
                        <Badge key={reason} variant="outline" className="font-normal text-[11px] text-zinc-600 bg-white">
                          {reason}
                        </Badge>
                      ))}
                    </div>

                    <div className="border-t border-zinc-100 pt-2 flex items-center justify-between">
                      <a
                        href={location.maps_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 font-semibold text-sky-700 hover:text-sky-900 transition-colors"
                      >
                        <span>View on Google Maps</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>

                      <span className="text-[10px] text-zinc-400 font-mono">
                        ID: {location.id}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <p className="mt-4 flex items-start gap-2 text-[11px] leading-relaxed text-zinc-500">
              <LandPlot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-400" />
              <span>{response.disclaimer}</span>
            </p>
          </div>
        </section>
      )}
    </div>
  );
}
