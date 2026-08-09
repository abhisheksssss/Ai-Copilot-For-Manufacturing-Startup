"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/store/use-auth-store";
import {
  Factory,
  ArrowRight,
  Zap,
  Building2,
  Search,
  ClipboardCheck,
  BadgeIndianRupee,
  Cpu,
  Activity,
  BarChart3,
  AlertTriangle,
  CheckCircle2,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Layers3,
  Users,
  Compass,
  FileText,
  ChevronRight,
  Check,
} from "lucide-react";

export default function LandingPage() {
  const { initializeAuth, token } = useAuthStore();
  const [activeTab, setActiveTab] = useState<"orchestrator" | "twin" | "schemes">("orchestrator");

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  return (
    <div className="flex min-h-screen flex-col bg-[#F8F7F4] text-zinc-900 antialiased selection:bg-zinc-900 selection:text-white">

      {/* ── 1. STICKY HEADER ── */}
      <header className="sticky top-0 z-50 border-b border-zinc-200/80 bg-white/85 px-4 backdrop-blur-md transition-all">
        <div className="mx-auto flex h-16 max-w-screen-xl items-center justify-between">
          
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-zinc-900 text-white shadow-md transition-transform group-hover:scale-105">
              <Factory className="h-5 w-5 text-white" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-extrabold tracking-tight text-zinc-900 leading-tight">
                AI Manufacturing Copilot
              </span>
              <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest">
                For Indian MSMEs
              </span>
            </div>
          </Link>

          {/* Navigation Links */}
          <nav className="hidden md:flex items-center gap-8 text-xs font-semibold text-zinc-600">
            <a href="#agents" className="hover:text-zinc-900 transition-colors">AI Agents</a>
            <a href="#digital-twin" className="hover:text-zinc-900 transition-colors">3D Digital Twin</a>
            <a href="#features" className="hover:text-zinc-900 transition-colors">Capabilities</a>
            <a href="#schemes" className="hover:text-zinc-900 transition-colors">Govt Schemes</a>
            <a href="#workflow" className="hover:text-zinc-900 transition-colors">How It Works</a>
          </nav>

          {/* CTA Buttons */}
          <div className="flex items-center gap-3">
            {token ? (
              <Link
                href="/planner"
                className="flex items-center gap-2 rounded-xl bg-zinc-900 px-4 py-2 text-xs font-bold text-white shadow-md hover:bg-zinc-800 transition-all hover:scale-[1.02]"
              >
                Go to Copilot App
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="text-xs font-bold text-zinc-700 hover:text-zinc-900 transition-colors px-2 py-1"
                >
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  className="flex items-center gap-1.5 rounded-xl bg-zinc-900 px-4 py-2 text-xs font-bold text-white shadow-md hover:bg-zinc-800 transition-all hover:scale-[1.02]"
                >
                  Get Started Free
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      {/* ── 2. HERO SECTION ── */}
      <main className="flex-1">
        <section className="relative overflow-hidden pt-20 pb-16 sm:pt-28 sm:pb-24 border-b border-zinc-200/60 bg-gradient-to-b from-[#F8F7F4] via-white to-[#F8F7F4]">
          {/* Subtle Grid Background Overlay */}
          <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: "radial-gradient(#000 1px, transparent 1px)", backgroundSize: "24px 24px" }} />

          <div className="mx-auto max-w-screen-xl px-4 relative z-10">
            <div className="mx-auto max-w-3xl text-center">
              
              {/* Badge */}
              <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-amber-300/60 bg-amber-50 px-3.5 py-1 text-xs font-bold text-amber-900 shadow-2xs">
                <Sparkles className="h-3.5 w-3.5 text-amber-600 animate-pulse" />
                <span>Autonomous Multi-Agent Industrial Brain for MSMEs</span>
              </div>

              {/* Main Headline */}
              <h1 className="text-4xl font-black tracking-tight text-zinc-900 sm:text-6xl leading-[1.1]">
                Turn Manufacturing Ideas into{" "}
                <span className="relative inline-block bg-gradient-to-r from-amber-600 via-orange-600 to-zinc-900 bg-clip-text text-transparent">
                  Execution-Ready Factories
                </span>
              </h1>

              {/* Subtitle */}
              <p className="mx-auto mt-6 max-w-2xl text-base sm:text-lg leading-relaxed text-zinc-600 font-medium">
                From <strong>market research & B2B supplier ranking</strong> to <strong>real-time 3D Digital Twin simulation</strong>, CAPEX/OPEX financial modeling, and <strong>Government scheme eligibility math</strong> — powered by 5 collaborative AI specialist agents.
              </p>

              {/* Primary Action Buttons */}
              <div className="mt-9 flex flex-col sm:flex-row items-center justify-center gap-3.5">
                <Link
                  href={token ? "/planner" : "/signup"}
                  className="flex w-full sm:w-auto items-center justify-center gap-2 rounded-xl bg-zinc-900 px-7 py-3.5 text-sm font-bold text-white shadow-xl hover:bg-zinc-800 hover:scale-[1.02] active:scale-[0.98] transition-all"
                >
                  <Zap className="h-4 w-4 text-amber-400 fill-amber-400" />
                  Launch Copilot App
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  href="/digital-twin"
                  className="flex w-full sm:w-auto items-center justify-center gap-2 rounded-xl border border-zinc-300 bg-white px-6 py-3.5 text-sm font-bold text-zinc-800 shadow-xs hover:border-zinc-400 hover:bg-zinc-100 transition-all"
                >
                  <Building2 className="h-4 w-4 text-zinc-600" />
                  Explore 3D Digital Twin
                </Link>
              </div>

              {/* Trust Features Bar */}
              <div className="mt-8 flex flex-wrap items-center justify-center gap-6 text-xs font-semibold text-zinc-500">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span>No CAD experience required</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span>Verified B2B Suppliers</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span>PMEGP, MSME & PLI Schemes</span>
                </div>
              </div>
            </div>

            {/* Metrics Counter Bar */}
            <div className="mx-auto mt-16 max-w-4xl grid grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                { label: "Modeled Investments", value: "₹500Cr+", sub: "CAPEX & OPEX projections" },
                { label: "Verified Vendors", value: "1,200+", sub: "B2B machinery & raw materials" },
                { label: "Govt Subsidy Schemes", value: "100+", sub: "Central & State schemes" },
                { label: "3D Digital Twin", value: "Real-Time", sub: "Bottleneck & throughput math" },
              ].map((m, idx) => (
                <div key={idx} className="flex flex-col items-center rounded-2xl border border-zinc-200/80 bg-white p-5 text-center shadow-xs transition-all hover:shadow-md">
                  <span className="text-2xl sm:text-3xl font-black text-zinc-900 tracking-tight">{m.value}</span>
                  <span className="mt-1 text-xs font-bold text-zinc-800">{m.label}</span>
                  <span className="text-[10px] text-zinc-500 mt-0.5">{m.sub}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── 3. INTERACTIVE PLATFORM DEMO SHOWCASE ── */}
        <section id="digital-twin" className="py-20 bg-zinc-900 text-white relative overflow-hidden">
          <div className="mx-auto max-w-screen-xl px-4">
            
            <div className="flex flex-col md:flex-row items-center justify-between gap-8 mb-12">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3.5 py-1 text-xs font-bold text-cyan-400 mb-3">
                  <Cpu className="h-3.5 w-3.5" />
                  Real-time Simulation Engine
                </div>
                <h2 className="text-3xl font-black tracking-tight sm:text-4xl text-white">
                  Experience the 3D Factory Digital Twin
                </h2>
                <p className="mt-2 text-sm text-zinc-400 max-w-xl">
                  Simulate monthly throughput, calculate machine utilization, detect line bottlenecks, and visualize your entire shop floor layout in 3D before committing capital.
                </p>
              </div>

              {/* Tab selector */}
              <div className="flex rounded-xl bg-zinc-800/80 p-1 border border-zinc-700/60">
                <button
                  onClick={() => setActiveTab("orchestrator")}
                  className={`rounded-lg px-4 py-2 text-xs font-bold transition-all ${activeTab === "orchestrator" ? "bg-cyan-500 text-black shadow-md" : "text-zinc-400 hover:text-white"}`}
                >
                  Multi-Agent Brain
                </button>
                <button
                  onClick={() => setActiveTab("twin")}
                  className={`rounded-lg px-4 py-2 text-xs font-bold transition-all ${activeTab === "twin" ? "bg-cyan-500 text-black shadow-md" : "text-zinc-400 hover:text-white"}`}
                >
                  3D Viewport & Bottlenecks
                </button>
                <button
                  onClick={() => setActiveTab("schemes")}
                  className={`rounded-lg px-4 py-2 text-xs font-bold transition-all ${activeTab === "schemes" ? "bg-cyan-500 text-black shadow-md" : "text-zinc-400 hover:text-white"}`}
                >
                  Financial & Subsidy Math
                </button>
              </div>
            </div>

            {/* Showcase Display Card */}
            <div className="rounded-3xl border border-zinc-800 bg-[#060b16] p-6 shadow-2xl relative overflow-hidden">
              {activeTab === "orchestrator" && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/5 p-5">
                    <div className="flex items-center gap-2 mb-3 text-cyan-400">
                      <Compass className="h-5 w-5" />
                      <h3 className="text-sm font-bold uppercase tracking-wider">Router Orchestrator</h3>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Deconstructs complex user factory queries (e.g. <i>&quot;50k EV chargers in Pune with ₹10 Cr&quot;</i>) and dynamically routes sub-tasks across specialist agents in parallel.
                    </p>
                  </div>
                  <div className="rounded-2xl border border-purple-500/20 bg-purple-500/5 p-5">
                    <div className="flex items-center gap-2 mb-3 text-purple-400">
                      <Layers3 className="h-5 w-5" />
                      <h3 className="text-sm font-bold uppercase tracking-wider">Parallel Multi-Node Execution</h3>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Executes Planning, Manufacturing, Scheme, and Market Research nodes concurrently, merging technical process parameters with financial ROI modeling.
                    </p>
                  </div>
                  <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-5">
                    <div className="flex items-center gap-2 mb-3 text-emerald-400">
                      <ShieldCheck className="h-5 w-5" />
                      <h3 className="text-sm font-bold uppercase tracking-wider">Judge Verification Node</h3>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Cross-validates throughput targets against bottleneck capacities and energy requirements, ensuring zero mathematical hallucinations before report delivery.
                    </p>
                  </div>
                </div>
              )}

              {activeTab === "twin" && (
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-center">
                  <div className="md:col-span-3 rounded-2xl border border-zinc-800 bg-[#080d1a] h-72 flex flex-col items-center justify-center p-6 relative overflow-hidden">
                    <div className="absolute inset-0 opacity-20" style={{ backgroundImage: "linear-gradient(rgba(6,182,212,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(6,182,212,0.2) 1px, transparent 1px)", backgroundSize: "30px 30px" }} />
                    <Factory className="h-16 w-16 text-cyan-400 animate-pulse mb-3" />
                    <p className="text-sm font-bold text-white">Interactive 3D Shop Floor Scene</p>
                    <p className="text-xs text-zinc-400 text-center max-w-md mt-1">
                      Rendered using Three.js with glowing zones, machine shape indicators, material flow arrows, and instant bottleneck pulse animation.
                    </p>
                    <div className="mt-4 flex gap-3 text-[10px]">
                      <span className="rounded-full bg-cyan-500/20 text-cyan-300 px-3 py-1 border border-cyan-500/30">Warehouse & Assembly</span>
                      <span className="rounded-full bg-red-500/20 text-red-300 px-3 py-1 border border-red-500/30">Testing Bottleneck (94% Util)</span>
                      <span className="rounded-full bg-emerald-500/20 text-emerald-300 px-3 py-1 border border-emerald-500/30">Packaging & Dispatch</span>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div className="rounded-xl border border-zinc-800 bg-zinc-900/90 p-4">
                      <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Effective Throughput</p>
                      <p className="text-xl font-bold text-cyan-400 mt-1">34,300 units/mo</p>
                      <p className="text-[10px] text-zinc-500 mt-0.5">Target: 50,000 units/mo</p>
                    </div>
                    <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4">
                      <div className="flex items-center gap-1.5 text-red-400 mb-1">
                        <AlertTriangle className="h-4 w-4" />
                        <p className="text-[10px] font-bold uppercase tracking-widest">Bottleneck Step</p>
                      </div>
                      <p className="text-sm font-bold text-white">Testing & Quality Control</p>
                      <p className="text-[10px] text-red-300 mt-0.5">Capacity limit: 1,319 units/day</p>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "schemes" && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="rounded-2xl border border-zinc-800 bg-zinc-900/90 p-5">
                    <div className="flex items-center gap-2 mb-3 text-amber-400">
                      <BadgeIndianRupee className="h-5 w-5" />
                      <h3 className="text-sm font-bold">PMEGP Subsidy Match</h3>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Up to <strong>35% subsidy</strong> on project CAPEX for micro-manufacturing units in rural & urban industrial clusters under Khadi & MSME schemes.
                    </p>
                  </div>
                  <div className="rounded-2xl border border-zinc-800 bg-zinc-900/90 p-5">
                    <div className="flex items-center gap-2 mb-3 text-cyan-400">
                      <TrendingUp className="h-5 w-5" />
                      <h3 className="text-sm font-bold">Break-Even & Financial ROI</h3>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Calculates exact payback timeline, gross margin %, monthly OPEX breakdown, and conservative vs aggressive financial scenarios.
                    </p>
                  </div>
                  <div className="rounded-2xl border border-zinc-800 bg-zinc-900/90 p-5">
                    <div className="flex items-center gap-2 mb-3 text-emerald-400">
                      <FileText className="h-5 w-5" />
                      <h3 className="text-sm font-bold">CGTMSE Collateral-Free Loans</h3>
                    </div>
                    <p className="text-xs text-zinc-300 leading-relaxed">
                      Identifies eligible bank lending options up to <strong>₹5 Crore</strong> without third-party collateral guarantee under CGTMSE trust coverage.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ── 4. THE 5 SPECIALIST AI AGENTS ── */}
        <section id="agents" className="py-24 border-b border-zinc-200/60 bg-[#F8F7F4]">
          <div className="mx-auto max-w-screen-xl px-4">
            
            <div className="text-center max-w-2xl mx-auto mb-16">
              <div className="inline-flex items-center gap-2 rounded-full border border-zinc-300 bg-white px-3.5 py-1 text-xs font-bold text-zinc-800 shadow-2xs mb-3">
                <Users className="h-3.5 w-3.5 text-zinc-700" />
                Collaborative Multi-Agent Architecture
              </div>
              <h2 className="text-3xl font-black tracking-tight text-zinc-900 sm:text-4xl">
                Meet Your 5 Autonomous Industrial Specialists
              </h2>
              <p className="mt-3 text-sm text-zinc-600 font-medium">
                Instead of a single generic chatbot, Copilot deploys a team of domain-expert AI agents that collaborate to solve your manufacturing challenge.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              
              {/* Agent 1 */}
              <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs transition-all hover:shadow-md hover:-translate-y-1">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-amber-100 text-amber-900 mb-4 font-bold">
                  <ClipboardCheck className="h-6 w-6 text-amber-800" />
                </div>
                <h3 className="text-base font-bold text-zinc-900">Planning Agent</h3>
                <p className="text-xs text-amber-800 font-semibold mt-0.5">Roadmap & Investment Sizing</p>
                <p className="mt-3 text-xs text-zinc-600 leading-relaxed">
                  Generates business roadmaps, timeline milestones, total investment estimation (CAPEX/OPEX), risk assessment, team headcount, and minimum factory land footprint (sq. ft.).
                </p>
              </div>

              {/* Agent 2 */}
              <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs transition-all hover:shadow-md hover:-translate-y-1">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-100 text-cyan-900 mb-4 font-bold">
                  <Building2 className="h-6 w-6 text-cyan-800" />
                </div>
                <h3 className="text-base font-bold text-zinc-900">Manufacturing Agent</h3>
                <p className="text-xs text-cyan-800 font-semibold mt-0.5">Process & Shop Floor Design</p>
                <p className="mt-3 text-xs text-zinc-600 leading-relaxed">
                  Designs multi-step manufacturing processes, recommends specific machinery, computes Bill of Materials (BOM), power requirements (kW), and compliance standards (BIS / ISO).
                </p>
              </div>

              {/* Agent 3 */}
              <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs transition-all hover:shadow-md hover:-translate-y-1">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-100 text-emerald-900 mb-4 font-bold">
                  <BadgeIndianRupee className="h-6 w-6 text-emerald-800" />
                </div>
                <h3 className="text-base font-bold text-zinc-900">Scheme & Subsidy Agent</h3>
                <p className="text-xs text-emerald-800 font-semibold mt-0.5">Govt & MSME Benefits</p>
                <p className="mt-3 text-xs text-zinc-600 leading-relaxed">
                  Scans Central and State schemes (PMEGP, MSME Champions, PMFME, PLI), calculates subsidy amounts, evaluates eligibility, and lists collateral-free bank loans.
                </p>
              </div>

              {/* Agent 4 */}
              <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs transition-all hover:shadow-md hover:-translate-y-1">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-100 text-purple-900 mb-4 font-bold">
                  <Search className="h-6 w-6 text-purple-800" />
                </div>
                <h3 className="text-base font-bold text-zinc-900">Market Research Agent</h3>
                <p className="text-xs text-purple-800 font-semibold mt-0.5">Suppliers & Competitors</p>
                <p className="mt-3 text-xs text-zinc-600 leading-relaxed">
                  Performs live web intelligence searches for verified B2B machinery suppliers, ranks local manufacturers by relevance, analyzes market competitors, and estimates TAM/SAM/SOM.
                </p>
              </div>

              {/* Agent 5 */}
              <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs transition-all hover:shadow-md hover:-translate-y-1 md:col-span-2">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-zinc-900 text-white mb-4 font-bold">
                  <ShieldCheck className="h-6 w-6 text-white" />
                </div>
                <h3 className="text-base font-bold text-zinc-900">Judge & QA Verification Agent</h3>
                <p className="text-xs text-zinc-500 font-semibold mt-0.5">Quality Control & Cross-Validation</p>
                <p className="mt-3 text-xs text-zinc-600 leading-relaxed">
                  Performs automated audit checks on generated reports to ensure financial numbers, throughput capacities, and process parameters match precisely across all agent outputs without contradictions.
                </p>
              </div>

            </div>
          </div>
        </section>

        {/* ── 5. CORE PLATFORM CAPABILITIES ── */}
        <section id="features" className="py-24 border-b border-zinc-200/60 bg-white">
          <div className="mx-auto max-w-screen-xl px-4">
            
            <div className="text-center max-w-2xl mx-auto mb-16">
              <h2 className="text-3xl font-black tracking-tight text-zinc-900 sm:text-4xl">
                Engineered for Indian Manufacturing Startups
              </h2>
              <p className="mt-3 text-sm text-zinc-600 font-medium">
                Everything you need to evaluate, plan, and execute a new manufacturing facility in India.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              
              <div className="rounded-2xl border border-zinc-200 bg-[#F8F7F4] p-6 space-y-3">
                <div className="h-10 w-10 rounded-xl bg-zinc-900 text-white flex items-center justify-center font-bold">
                  <Search className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-zinc-900">Location-Aware B2B Supplier Search</h3>
                <p className="text-xs text-zinc-600 leading-relaxed">
                  Scans IndiaMART, TradeIndia, and corporate domains. Ranks actual equipment manufacturers in target industrial hubs (e.g. Pune, Rajkot, Chennai) over generic news portals.
                </p>
              </div>

              <div className="rounded-2xl border border-zinc-200 bg-[#F8F7F4] p-6 space-y-3">
                <div className="h-10 w-10 rounded-xl bg-zinc-900 text-white flex items-center justify-center font-bold">
                  <BarChart3 className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-zinc-900">Break-Even & Financial ROI Sizing</h3>
                <p className="text-xs text-zinc-600 leading-relaxed">
                  Generates 3 financial scenarios (Conservative, Balanced, Aggressive) with monthly OPEX, gross margin %, annual ROI %, and exact break-even payback timelines.
                </p>
              </div>

              <div className="rounded-2xl border border-zinc-200 bg-[#F8F7F4] p-6 space-y-3">
                <div className="h-10 w-10 rounded-xl bg-zinc-900 text-white flex items-center justify-center font-bold">
                  <Activity className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-zinc-900">Interactive What-If Simulator</h3>
                <p className="text-xs text-zinc-600 leading-relaxed">
                  Test &quot;what-if&quot; modifications (e.g. <i>&quot;double production capacity&quot;</i> or <i>&quot;reduce budget by 20%&quot;</i>) and instantly observe impact on throughput, bottlenecks, and ROI.
                </p>
              </div>

              <div className="rounded-2xl border border-zinc-200 bg-[#F8F7F4] p-6 space-y-3">
                <div className="h-10 w-10 rounded-xl bg-zinc-900 text-white flex items-center justify-center font-bold">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-zinc-900">Saved History by userId</h3>
                <p className="text-xs text-zinc-600 leading-relaxed">
                  Persists past conversation history, generated workflows, and Digital Twin configurations securely per user, enabling seamless multi-session factory planning.
                </p>
              </div>

            </div>
          </div>
        </section>

        {/* ── 6. HOW IT WORKS ── */}
        <section id="workflow" className="py-24 border-b border-zinc-200/60 bg-[#F8F7F4]">
          <div className="mx-auto max-w-screen-xl px-4">
            
            <div className="text-center max-w-2xl mx-auto mb-16">
              <div className="inline-flex items-center gap-2 rounded-full border border-zinc-300 bg-white px-3.5 py-1 text-xs font-bold text-zinc-800 shadow-2xs mb-3">
                <Compass className="h-3.5 w-3.5 text-zinc-700" />
                Simple 4-Step Journey
              </div>
              <h2 className="text-3xl font-black tracking-tight text-zinc-900 sm:text-4xl">
                From Prompt to Complete Industrial Blueprint
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 relative">
              
              {[
                { step: "01", title: "Describe Your Vision", desc: "Enter your product idea, target monthly volume, preferred city/state, and total investment budget." },
                { step: "02", title: "Agents Collaborate", desc: "Specialist AI nodes execute parallel market research, process design, land sizing, and scheme calculations." },
                { step: "03", title: "Simulate 3D Twin", desc: "Inspect your shop floor layout in 3D, identify bottleneck machines, and run what-if capacity stress tests." },
                { step: "04", title: "Execute & Apply", desc: "Get ranked supplier contact details, downloadable financial blueprints, and ready-to-apply MSME scheme recommendations." },
              ].map((s, idx) => (
                <div key={idx} className="relative rounded-2xl border border-zinc-200 bg-white p-6 shadow-xs flex flex-col justify-between">
                  <div>
                    <span className="text-3xl font-black text-amber-600">{s.step}</span>
                    <h3 className="text-sm font-bold text-zinc-900 mt-2">{s.title}</h3>
                    <p className="mt-2 text-xs text-zinc-600 leading-relaxed">{s.desc}</p>
                  </div>
                </div>
              ))}

            </div>
          </div>
        </section>

        {/* ── 7. SUPPORTED MANUFACTURING SECTORS ── */}
        <section className="py-20 bg-white border-b border-zinc-200/60">
          <div className="mx-auto max-w-screen-xl px-4">
            
            <div className="text-center max-w-2xl mx-auto mb-12">
              <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-zinc-900">
                Pre-Trained Knowledge Across Key MSME Sectors
              </h2>
              <p className="mt-2 text-xs sm:text-sm text-zinc-600">
                Built-in process templates, machinery specs, and cost models for high-growth Indian industries.
              </p>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {[
                "Plastic Injection Molding",
                "EV Charger Assembly",
                "PCB Assembly & SMT",
                "Milk & Food Processing",
                "Solar Module Assembly",
                "Textile & Garments",
              ].map((sector) => (
                <div key={sector} className="flex items-center gap-2 rounded-xl border border-zinc-200 bg-[#F8F7F4] p-3 text-center justify-center">
                  <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                  <span className="text-xs font-bold text-zinc-800">{sector}</span>
                </div>
              ))}
            </div>

          </div>
        </section>

        {/* ── 8. CALL TO ACTION BANNER ── */}
        <section className="py-20 bg-zinc-900 text-white relative overflow-hidden">
          <div className="mx-auto max-w-screen-xl px-4 relative z-10 text-center max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3.5 py-1 text-xs font-bold text-amber-400 mb-4">
              <Sparkles className="h-3.5 w-3.5" />
              Start Planning in Minutes
            </div>
            
            <h2 className="text-3xl sm:text-5xl font-black tracking-tight text-white leading-tight">
              Ready to Build Your Next Manufacturing Unit?
            </h2>
            
            <p className="mt-4 text-sm sm:text-base text-zinc-400 font-medium">
              Join Indian entrepreneurs, factory owners, and MSME planning teams using AI Manufacturing Copilot.
            </p>

            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                href={token ? "/planner" : "/signup"}
                className="flex w-full sm:w-auto items-center justify-center gap-2 rounded-xl bg-white px-8 py-3.5 text-sm font-bold text-zinc-900 shadow-xl hover:bg-zinc-100 transition-all"
              >
                Launch Copilot Now
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/digital-twin"
                className="flex w-full sm:w-auto items-center justify-center gap-2 rounded-xl border border-zinc-700 bg-zinc-800/80 px-6 py-3.5 text-sm font-bold text-white hover:bg-zinc-800 transition-all"
              >
                Launch 3D Digital Twin
              </Link>
            </div>
          </div>
        </section>

      </main>

      {/* ── 9. FOOTER ── */}
      <footer className="border-t border-zinc-200 bg-white py-12 px-4 text-xs text-zinc-500">
        <div className="mx-auto max-w-screen-xl flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-zinc-900 text-white">
              <Factory className="h-3.5 w-3.5" />
            </div>
            <span className="font-bold text-zinc-900">AI Manufacturing Copilot</span>
            <span>© {new Date().getFullYear()} All rights reserved.</span>
          </div>

          <div className="flex items-center gap-6 font-semibold text-zinc-600">
            <Link href="/planner" className="hover:text-zinc-900 transition-colors">Planner</Link>
            <Link href="/chat" className="hover:text-zinc-900 transition-colors">Chatbot</Link>
            <Link href="/digital-twin" className="hover:text-zinc-900 transition-colors">Digital Twin</Link>
            <Link href="/login" className="hover:text-zinc-900 transition-colors">Sign In</Link>
          </div>
        </div>
      </footer>

    </div>
  );
}
