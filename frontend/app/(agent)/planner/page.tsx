"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BadgeIndianRupee,
  Bot,
  Building2,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Circle,
  Factory,
  Loader2,
  LogOut,
  MessageSquare,
  Search,
  Send,
  Sparkles,
  Trash2,
  User,
  Wrench,
  Zap,
} from "lucide-react";
import { toast } from "sonner";

import { useRouter } from "next/navigation";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import {
  fetchProfile,
  type AuthResponse,
} from "@/lib/api";
import { useAuthStore } from "@/store/use-auth-store";
import { useCopilotStore } from "@/store/use-copilot-store";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// ─── Constants ────────────────────────────────────────────────────────────────

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const EXAMPLE_PROMPTS = [
  "Plastic packaging factory in Chennai, ₹40L budget, B2B focus",
  "Textile manufacturing unit in Surat with MSME subsidy options",
  "Electric scooter parts unit in Pune for B2B automotive supply",
];

const PIPELINE_STEPS = [
  {
    key: "planning",
    label: "Business strategy",
    icon: ClipboardCheck,
    color: "text-blue-600",
    bgColor: "bg-blue-50",
    borderColor: "border-blue-200",
  },
  {
    key: "manufacturing",
    label: "Factory setup",
    icon: Building2,
    color: "text-amber-600",
    bgColor: "bg-amber-50",
    borderColor: "border-amber-200",
  },
  {
    key: "schemes",
    label: "Subsidies & loans",
    icon: BadgeIndianRupee,
    color: "text-emerald-600",
    bgColor: "bg-emerald-50",
    borderColor: "border-emerald-200",
  },
  {
    key: "research",
    label: "Market & suppliers",
    icon: Search,
    color: "text-purple-600",
    bgColor: "bg-purple-50",
    borderColor: "border-purple-200",
  },
] as const;

// ─── Types ────────────────────────────────────────────────────────────────────

type AgentReport = { report: string };

type PlanResponse = {
  messages?: string[];
  final_report?: {
    planning?: AgentReport;
    manufacturing?: AgentReport;
    schemes?: AgentReport;
    research?: AgentReport;
  };
  [key: string]: unknown;
};

// ─── Root Page ────────────────────────────────────────────────────────────────

export default function PlannerPage() {
  const router = useRouter();
  const { query, setQuery, history, addHistory, clearHistory } = useCopilotStore();
  const { token, user, isReady, initializeAuth, setUser, logout } = useAuthStore();

  const [isStreaming, setIsStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState("");
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [completedAgents, setCompletedAgents] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<PlanResponse | null>(null);
  const [showChatRedirectBanner, setShowChatRedirectBanner] = useState(true);
  const [interrupt, setInterrupt] = useState<{action: string, question: string} | null>(null);
  const [interruptAnswer, setInterruptAnswer] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [streamedText]);

  const profileQuery = useQuery({
    queryKey: ["profile", token],
    queryFn: () => fetchProfile(token as string),
    enabled: Boolean(token),
    retry: false,
  });

  useEffect(() => {
    if (profileQuery.data) setUser(profileQuery.data);
  }, [profileQuery.data, setUser]);

  useEffect(() => {
    if (profileQuery.isError) {
      logout();
      toast.error("Session expired. Please log in again.");
    }
  }, [profileQuery.isError, logout]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        submitPlan();
      }
    },
    [query, token, isStreaming]
  );

  async function submitPlan() {
    const cleanQuery = query.trim();
    if (!token) { toast.error("Log in to use the copilot"); return; }
    if (!cleanQuery) { toast.error("Describe your manufacturing idea first"); return; }

    setIsStreaming(true);
    setStreamedText("");
    setActiveAgent(null);
    setActiveTool(null);
    setCompletedAgents({});
    setResult(null);
    setInterrupt(null);
    addHistory(cleanQuery);

    let wasInterrupted = false;

    try {
      const res = await fetch(`${API_URL}/api/plan/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ query: cleanQuery }),
      });

      if (!res.ok) throw new Error("Could not reach the planning server");
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      let buffer = "";

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        
        if (value) {
          buffer += decoder.decode(value, { stream: !done });
        } else if (done) {
          buffer += decoder.decode();
        }

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const payload = trimmed.slice(6).trim();
          if (!payload) continue;

          try {
            const data = JSON.parse(payload);
            if (data.type === "agent_start") {
              setActiveAgent(data.agent);
            } else if (data.type === "agent_completed") {
              setCompletedAgents((prev) => ({ ...prev, [data.agent]: true }));
              setActiveAgent(null);
            } else if (data.type === "tool_start") {
              setActiveTool(data.tool_name);
            } else if (data.type === "tool_end") {
              setActiveTool(null);
            } else if (data.type === "message_chunk") {
              if (data.content) {
                setStreamedText((prev) => prev + data.content);
              }
            } else if (data.type === "final_report") {
              setResult(data.data as PlanResponse);
              setShowChatRedirectBanner(true);
              toast.success("Workflow plan generated! Redirect to Agent Chat for further discussion?", {
                action: {
                  label: "Go to Chat",
                  onClick: () => router.push("/chat"),
                },
              });
            } else if (data.type === "interrupted") {
              setInterrupt(data.data);
              wasInterrupted = true;
            }
          } catch {
            // Buffer fragment, wait for next chunk
          }
        }
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      if (!wasInterrupted) {
        setIsStreaming(false);
      }
      setActiveTool(null);
      setActiveAgent(null);
    }
  }

  async function submitInterruptAnswer() {
    const cleanAnswer = interruptAnswer.trim();
    if (!cleanAnswer || !token) return;

    setIsStreaming(true);
    setInterrupt(null);
    setInterruptAnswer("");
    setStreamedText((p) => p + `\n\n**You:** ${cleanAnswer}\n\n`);

    let wasInterrupted = false;

    try {
      const res = await fetch(`${API_URL}/api/plan/resume`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ answer: cleanAnswer }),
      });

      if (!res.ok) throw new Error("Could not reach the server to resume");
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      let buffer = "";

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        
        if (value) {
          buffer += decoder.decode(value, { stream: !done });
        } else if (done) {
          buffer += decoder.decode();
        }

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const payload = trimmed.slice(6).trim();
          if (!payload) continue;

          try {
            const data = JSON.parse(payload);
            if (data.type === "agent_start") {
              setActiveAgent(data.agent);
            } else if (data.type === "agent_completed") {
              setCompletedAgents((prev) => ({ ...prev, [data.agent]: true }));
              setActiveAgent(null);
            } else if (data.type === "tool_start") {
              setActiveTool(data.tool_name);
            } else if (data.type === "tool_end") {
              setActiveTool(null);
            } else if (data.type === "message_chunk") {
              if (data.content) {
                setStreamedText((prev) => prev + data.content);
              }
            } else if (data.type === "final_report") {
              setResult(data.data as PlanResponse);
              setShowChatRedirectBanner(true);
              toast.success("Workflow plan generated! Redirect to Agent Chat for further discussion?", {
                action: {
                  label: "Go to Chat",
                  onClick: () => router.push("/chat"),
                },
              });
            } else if (data.type === "interrupted") {
              setInterrupt(data.data);
              wasInterrupted = true;
            }
          } catch {
            // Buffer fragment, wait for next chunk
          }
        }
      }
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      if (!wasInterrupted) {
        setIsStreaming(false);
      }
      setActiveTool(null);
      setActiveAgent(null);
    }
  }

  if (!isReady || !token) return null;

  return (
    <div className="mx-auto grid max-w-screen-xl gap-6 px-4 py-6 lg:grid-cols-[340px_1fr]">
      {/* ── Sidebar ── */}
          <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
            {/* Profile */}
            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                <User className="h-3.5 w-3.5" />
                Your account
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2">
                  <span className="text-zinc-500">Email</span>
                  <span className="max-w-[160px] truncate font-medium">{user?.email ?? "—"}</span>
                </div>
                <div className="flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2">
                  <span className="text-zinc-500">Role</span>
                  <span className="font-medium capitalize">{user?.role ?? "user"}</span>
                </div>
              </div>
            </div>

            {/* Query input */}
            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                <Sparkles className="h-3.5 w-3.5" />
                Describe your idea
              </div>

              <Textarea
                ref={textareaRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Product, location, budget, capacity, target market…"
                className="min-h-40 resize-none rounded-lg border-zinc-200 bg-zinc-50 text-sm placeholder:text-zinc-400 focus:bg-white"
                disabled={isStreaming}
              />

              <button
                onClick={submitPlan}
                disabled={isStreaming || !query.trim()}
                className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isStreaming ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Generating plan…</>
                ) : (
                  <><Send className="h-4 w-4" /> Generate plan <span className="ml-auto opacity-50">⌘↵</span></>
                )}
              </button>

              <div className="mt-4">
                <p className="mb-2 text-xs font-medium text-zinc-400">Try an example</p>
                <div className="space-y-1.5">
                  {EXAMPLE_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      onClick={() => { setQuery(prompt); textareaRef.current?.focus(); }}
                      disabled={isStreaming}
                      className="group flex w-full items-start gap-2 rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-2 text-left text-xs text-zinc-600 transition hover:border-zinc-200 hover:bg-white disabled:opacity-40"
                    >
                      <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-300 transition group-hover:text-zinc-500" />
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* History */}
            <div className="rounded-xl border border-zinc-200 bg-white p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                  Recent queries
                </div>
                {history.length > 0 && (
                  <button
                    onClick={clearHistory}
                    className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-600"
                  >
                    <Trash2 className="h-3 w-3" />
                    Clear
                  </button>
                )}
              </div>

              {history.length === 0 ? (
                <p className="py-2 text-center text-xs text-zinc-400">Plans you generate will appear here</p>
              ) : (
                <div className="space-y-1.5">
                  {history.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setQuery(item.query)}
                      className="w-full truncate rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-2 text-left text-xs text-zinc-600 transition hover:bg-white"
                    >
                      {item.query}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </aside>

          {/* ── Main content ── */}
          <main className="min-w-0 space-y-4">
            {/* Agent pipeline tracker */}
            {(isStreaming || result) && (
              <AgentPipeline
                result={result}
                isStreaming={isStreaming}
                activeAgent={activeAgent}
                activeTool={activeTool}
                completedAgents={completedAgents}
              />
            )}

            {/* Output panel */}
            <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white">
              {/* Panel header */}
              <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3.5">
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-zinc-400" />
                  <span className="text-sm font-medium text-zinc-700">
                    {isStreaming ? "Agent working…" : result ? "Plan complete" : "Copilot output"}
                  </span>
                  {isStreaming && (
                    <span className="flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
                      Live
                    </span>
                  )}
                </div>
                {activeTool && (
                  <div className="flex items-center gap-1.5 rounded-lg border border-blue-100 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                    <Wrench className="h-3 w-3 animate-spin" />
                    {formatToolLabel(activeTool)}
                  </div>
                )}
              </div>

              {/* Panel body */}
              <div className="p-5">
                {!streamedText && !isStreaming && !result && !interrupt ? (
                  <EmptyState />
                ) : isStreaming || interrupt ? (
                  <div className="space-y-4">
                    <StreamingOutput text={streamedText} scrollRef={scrollRef} isStreaming={isStreaming} activeTool={activeTool} />
                    {interrupt && (
                      <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 shadow-sm">
                        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-zinc-700">
                          <Bot className="h-4 w-4 text-blue-600" />
                          Agent needs clarification:
                        </div>
                        <p className="mb-4 text-sm text-zinc-600">{interrupt.question}</p>
                        <div className="flex gap-2">
                          <Input 
                            value={interruptAnswer}
                            onChange={(e) => setInterruptAnswer(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && submitInterruptAnswer()}
                            placeholder="Type your answer..."
                            className="bg-white"
                          />
                          <Button onClick={submitInterruptAnswer} className="bg-blue-600 hover:bg-blue-700">
                            Reply
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ) : result ? (
                  <div className="space-y-4">
                    {showChatRedirectBanner && (
                      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-xl border border-blue-200 bg-gradient-to-r from-blue-50 via-indigo-50 to-purple-50 p-4 shadow-xs">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
                            <MessageSquare className="h-5 w-5" />
                          </div>
                          <div>
                            <h4 className="text-sm font-semibold text-zinc-900">
                              Workflow Plan Generation Complete!
                            </h4>
                            <p className="text-xs text-zinc-600">
                              Would you like to redirect to Agent Chat for further discussion?
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                          <Button
                            onClick={() => router.push("/chat")}
                            className="flex items-center gap-2 bg-blue-600 font-medium text-white hover:bg-blue-700 shadow-xs"
                            size="sm"
                          >
                            <span>Go to Agent Chat</span>
                            <ArrowRight className="h-4 w-4" />
                          </Button>
                          <Button
                            onClick={() => setShowChatRedirectBanner(false)}
                            variant="ghost"
                            size="sm"
                            className="text-zinc-500 hover:bg-white/60 hover:text-zinc-700"
                          >
                            Dismiss
                          </Button>
                        </div>
                      </div>
                    )}
                    <ResultTabs result={result} />
                  </div>
                ) : (
                  <EmptyState />
                )}
              </div>
            </div>
          </main>
        </div>
  );
}

// ─── Agent Pipeline ───────────────────────────────────────────────────────────

function AgentPipeline({
  result,
  isStreaming,
  activeAgent,
  activeTool,
  completedAgents,
}: {
  result: PlanResponse | null;
  isStreaming: boolean;
  activeAgent: string | null;
  activeTool: string | null;
  completedAgents: Record<string, boolean>;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white px-5 py-4">
      <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">
        Agent pipeline
      </div>
      <div className="flex items-center gap-1">
        {PIPELINE_STEPS.map((step, i) => {
          const Icon = step.icon;
          const isDone =
            !!completedAgents[step.key] ||
            !!result?.final_report?.[step.key as keyof typeof result.final_report];

          const isActive =
            isStreaming &&
            !isDone &&
            (activeAgent === step.key ||
              (activeTool &&
                (activeTool.toLowerCase().includes(step.key) ||
                  (step.key === "research" && activeTool.toLowerCase().includes("search")))));

          return (
            <div key={step.key} className="flex flex-1 items-center gap-1">
              <div
                className={[
                  "flex flex-1 items-center gap-2 rounded-lg border px-3 py-2.5 transition-all duration-300",
                  isDone
                    ? `${step.bgColor} ${step.borderColor}`
                    : isActive
                    ? "border-zinc-300 bg-zinc-50 shadow-sm"
                    : "border-zinc-100 bg-zinc-50/50",
                ].join(" ")}
              >
                {isDone ? (
                  <CheckCircle2 className={`h-4 w-4 shrink-0 ${step.color}`} />
                ) : isActive ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-zinc-500" />
                ) : (
                  <Icon className="h-4 w-4 shrink-0 text-zinc-300" />
                )}
                <span
                  className={[
                    "hidden truncate text-xs font-medium sm:block",
                    isDone ? step.color : isActive ? "text-zinc-700" : "text-zinc-400",
                  ].join(" ")}
                >
                  {step.label}
                </span>
              </div>
              {i < PIPELINE_STEPS.length - 1 && (
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-300" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Streaming Output ─────────────────────────────────────────────────────────

function StreamingOutput({
  text,
  scrollRef,
  isStreaming,
  activeTool,
}: {
  text: string;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  isStreaming?: boolean;
  activeTool?: string | null;
}) {
  return (
    <div className="max-h-[520px] overflow-y-auto rounded-lg border border-zinc-100 bg-zinc-50 p-5 space-y-3">
      {text ? (
        <MarkdownRenderer content={text} />
      ) : (
        <div className="flex items-center gap-2 text-sm text-zinc-400">
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          Analyzing request & gathering data…
        </div>
      )}
      {isStreaming && (
        <div className="flex items-center gap-2 pt-3 border-t border-zinc-200/60 text-xs font-medium text-zinc-500">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
          {activeTool ? (
            <span>Executing <strong className="font-mono text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-100">{activeTool.replace(/_/g, " ")}</strong>...</span>
          ) : (
            <span>Agent working on your workflow plan...</span>
          )}
        </div>
      )}
      <div ref={scrollRef} />
    </div>
  );
}

// ─── Result Tabs ──────────────────────────────────────────────────────────────

function ResultTabs({ result }: { result: PlanResponse }) {
  const availableSteps = PIPELINE_STEPS.filter(
    (s) => result.final_report?.[s.key as keyof typeof result.final_report]
  );
  const defaultTab = availableSteps[0]?.key ?? PIPELINE_STEPS[0].key;

  return (
    <Tabs defaultValue={defaultTab} className="w-full">
      <TabsList className="mb-4 flex h-auto gap-1 rounded-lg border border-zinc-100 bg-zinc-50 p-1">
        {PIPELINE_STEPS.map((step) => {
          const Icon = step.icon;
          const hasData = !!result.final_report?.[step.key as keyof typeof result.final_report];
          return (
            <TabsTrigger
              key={step.key}
              value={step.key}
              disabled={!hasData}
              className={[
                "flex flex-1 items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition-all",
                "data-[state=active]:bg-white data-[state=active]:shadow-sm",
                !hasData && "opacity-40",
              ].join(" ")}
            >
              <Icon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{step.label}</span>
            </TabsTrigger>
          );
        })}
      </TabsList>

      {PIPELINE_STEPS.map((step) => {
        const reportObj = result.final_report?.[step.key as keyof typeof result.final_report];
        const content = reportObj?.report ?? "No content generated for this section.";
        return (
          <TabsContent key={step.key} value={step.key} className="m-0">
            <div className="max-h-[520px] overflow-y-auto rounded-lg border border-zinc-100 bg-white p-6">
              <MarkdownRenderer content={content} />
            </div>
          </TabsContent>
        );
      })}
    </Tabs>
  );
}

// ─── Empty State ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex min-h-[440px] flex-col items-center justify-center rounded-lg border border-dashed border-zinc-200 bg-zinc-50/50 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-white shadow-sm ring-1 ring-zinc-200">
        <Zap className="h-6 w-6 text-zinc-400" />
      </div>
      <p className="text-sm font-medium text-zinc-600">Ready to plan your factory</p>
      <p className="mt-1.5 max-w-xs text-xs leading-relaxed text-zinc-400">
        Describe your manufacturing idea on the left — the AI will run multiple specialist agents and return a full plan.
      </p>
    </div>
  );
}

// ─── Loading Screen ───────────────────────────────────────────────────────────

function AppLoading() {
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

// ─── Utilities ────────────────────────────────────────────────────────────────

function formatToolLabel(toolName: string): string {
  const name = toolName.toLowerCase();
  if (name.includes("duckduckgo") || name.includes("search")) return "Web search";
  if (name.includes("plan")) return "Business strategy";
  if (name.includes("manufactur")) return "Factory design";
  if (name.includes("scheme")) return "Subsidy lookup";
  if (name.includes("research")) return "Market analysis";
  return toolName.replace(/_/g, " ");
}
