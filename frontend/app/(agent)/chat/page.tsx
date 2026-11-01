"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeIndianRupee,
  Bot,
  Building2,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Clock,
  ExternalLink,
  Factory,
  History,
  Loader2,
  MessageSquare,
  Plus,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Trash2,
  User,
  Wrench,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { MarkdownRenderer } from "@/components/markdown-renderer";
import { fetchUserPlans, deleteUserPlan } from "@/lib/api";
import { useAuthStore } from "@/store/use-auth-store";
import { useCopilotStore, type HistoryItem } from "@/store/use-copilot-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SUGGESTED_QUESTIONS = [
  {
    icon: Factory,
    text: "Machinery & factory layout needed for an EV battery pack assembly unit in Pune",
  },
  {
    icon: BadgeIndianRupee,
    text: "Which MSME subsidies & SIDBI loans apply for solar panel manufacturing in Gujarat?",
  },
  {
    icon: Building2,
    text: "Estimate startup CAPEX, OPEX & break-even timeline for a ₹50L packaging unit",
  },
  {
    icon: Search,
    text: "Find top raw material suppliers and market competitors for plastic injection molding",
  },
];

type MessageItem = {
  id: string;
  sender: "user" | "assistant";
  content: string;
  agentName?: string;
  timestamp: Date;
};

function formatHistoryDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export default function ChatPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { token, user, isReady, initializeAuth } = useAuthStore();
  const {
    history,
    addHistory,
    syncBackendPlans,
    updateHistoryItem,
    removeHistoryItem,
    clearHistory,
    setQuery: setPlannerQuery,
  } = useCopilotStore();

  // Fetch plans directly from backend database and synchronize
  const plansQuery = useQuery({
    queryKey: ["userPlans", token],
    queryFn: () => fetchUserPlans(token as string),
    enabled: Boolean(token),
  });

  useEffect(() => {
    if (plansQuery.data && plansQuery.data.length > 0) {
      syncBackendPlans(plansQuery.data);
    }
  }, [plansQuery.data, syncBackendPlans]);

  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  // History Drawer State
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyTab, setHistoryTab] = useState<"all" | "planner" | "chat">("all");
  const [historySearch, setHistorySearch] = useState("");
  const [isMounted, setIsMounted] = useState(false);

  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [completedAgents, setCompletedAgents] = useState<Record<string, boolean>>({});

  const [interrupt, setInterrupt] = useState<{ action: string; question: string } | null>(null);
  const [interruptAnswer, setInterruptAnswer] = useState("");
  const interruptInputRef = useRef<HTMLInputElement>(null);

  // Tracks active history item thread
  const currentChatHistoryIdRef = useRef<string | null>(null);

  // Tracks active planner context if user selected a planner run to discuss
  const [activePlannerContext, setActivePlannerContext] = useState<{ query: string; id?: string } | null>(null);

  // Tracks which assistant message is currently being streamed
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<MessageItem[]>([]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  useEffect(() => {
    initializeAuth();
    setIsMounted(true);
  }, [initializeAuth]);

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming, scrollToBottom]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  function startNewChat() {
    setMessages([]);
    setStreamingMsgId(null);
    currentChatHistoryIdRef.current = null;
    setActivePlannerContext(null);
    setInputMessage("");
    setInterrupt(null);
    toast.success("Started a new conversation");
  }

  // Check URL query parameters (e.g. redirected from /planner?planId=...)
  const hasAutoLoadedParamRef = useRef(false);
  useEffect(() => {
    if (!isMounted || hasAutoLoadedParamRef.current) return;
    if (typeof window === "undefined") return;

    const urlParams = new URLSearchParams(window.location.search);
    const planIdParam = urlParams.get("planId");
    const queryParam = urlParams.get("query");

    if (planIdParam || queryParam) {
      const match =
        history.find(
          (h) =>
            (planIdParam && h.id === planIdParam) ||
            (queryParam && h.query.toLowerCase() === queryParam.toLowerCase())
        ) ||
        (plansQuery.data?.find(
          (p) =>
            (planIdParam && p.id === planIdParam) ||
            (queryParam && p.query.toLowerCase() === queryParam.toLowerCase())
        )
          ? {
              id: planIdParam || "",
              query: queryParam || plansQuery.data?.find((p) => p.id === planIdParam)?.query || "",
              createdAt: new Date().toISOString(),
              source: "planner" as const,
            }
          : null);

      if (match) {
        hasAutoLoadedParamRef.current = true;
        handleSelectHistoryItem(match as HistoryItem);
      }
    }
  }, [isMounted, history, plansQuery.data]);

  function handleSelectHistoryItem(item: HistoryItem) {
    if (item.source === "planner") {
      setActivePlannerContext({ query: item.query, id: item.id });
      currentChatHistoryIdRef.current = null;
      setMessages([
        {
          id: `planner_intro_${Date.now()}`,
          sender: "assistant",
          content: `🏭 **Loaded Factory Plan**: *"${item.query}"*\n\nI have retrieved the details of this manufacturing project from your business planner using semantic memory. What would you like to explore or refine?\n\n- **CAPEX / OPEX**: Ask about machine costs, operational expenses, or budget breakdown\n- **Machinery & BOM**: Ask for specific equipment specs, throughput, or factory layout\n- **Subsidies & Loans**: Inquire about MSME schemes, PMEGP, CGTMSE, or capital subsidies\n- **Market & Suppliers**: Explore raw material sourcing, competitor benchmarks, or pricing strategy`,
          timestamp: new Date(),
        },
      ]);
      setInputMessage("");
      toast.success("Loaded factory plan context via semantic search");
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        setHistoryOpen(false);
      }
      return;
    }

    if (item.messages && item.messages.length > 0) {
      if (item.plannerContext) {
        setActivePlannerContext(item.plannerContext);
      } else {
        setActivePlannerContext(null);
      }
      setMessages(
        item.messages.map((m) => ({
          id: m.id,
          sender: m.sender,
          content: m.content,
          timestamp: new Date(m.timestamp),
        }))
      );
      currentChatHistoryIdRef.current = item.id;
      toast.success("Loaded previous conversation");
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        setHistoryOpen(false);
      }
    } else {
      setActivePlannerContext(null);
      setInputMessage(item.query);
      textareaRef.current?.focus();
      toast.info(`Loaded query into input: "${item.query.slice(0, 45)}..."`);
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        setHistoryOpen(false);
      }
    }
  }

  async function sendMessage(overrideQuery?: string) {
    const query = (overrideQuery || inputMessage).trim();
    if (!query) return;
    if (!token) {
      toast.error("Please log in to chat with the agent.");
      return;
    }

    const userMsgId = Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();

    const userMsg: MessageItem = {
      id: userMsgId,
      sender: "user",
      content: query,
      timestamp: new Date(),
    };

    const assistantMsg: MessageItem = {
      id: assistantMsgId,
      sender: "assistant",
      content: "",
      timestamp: new Date(),
    };

    // Format prior conversation history before adding new messages
    const historyPayload = messagesRef.current
      .filter((m) => m.content && m.content.trim().length > 0)
      .map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.content.trim(),
      }));

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    if (!overrideQuery) setInputMessage("");

    // Add / record in combined history store
    if (!currentChatHistoryIdRef.current) {
      const histId = addHistory(query, "chat");
      currentChatHistoryIdRef.current = histId;
      if (activePlannerContext) {
        updateHistoryItem(histId, { plannerContext: activePlannerContext });
      }
    }

    setIsStreaming(true);
    setActiveAgent(null);
    setActiveTool(null);
    setCompletedAgents({});
    setInterrupt(null);
    setInterruptAnswer("");
    setStreamingMsgId(assistantMsgId);

    let wasInterrupted = false;

    try {
      const res = await fetch(`${API_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          query,
          history: historyPayload,
          planner_query: activePlannerContext ? activePlannerContext.query : undefined,
        }),
      });

      if (!res.ok) throw new Error("Failed to connect to AI Agent Chat endpoint.");
      if (!res.body) throw new Error("No response body received from server.");

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
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: msg.content + data.content }
                      : msg
                  )
                );
              }
            } else if (data.type === "final_report") {
              const finalReport = data.data?.final_report;
              if (finalReport) {
                let formattedReport = "";
                if (typeof finalReport.chatbot_response === "string" && finalReport.chatbot_response.trim()) {
                  formattedReport = finalReport.chatbot_response;
                } else if (finalReport.general?.report) {
                  formattedReport = finalReport.general.report;
                } else {
                  const parts = [];
                  if (finalReport.planning?.report) parts.push(`### 📋 Business & Factory Strategy\n\n${finalReport.planning.report}`);
                  if (finalReport.manufacturing?.report) parts.push(`### 🏭 Manufacturing & Technical Setup\n\n${finalReport.manufacturing.report}`);
                  if (finalReport.schemes?.report) parts.push(`### 💰 Subsidies & Financial Assistance\n\n${finalReport.schemes.report}`);
                  if (finalReport.research?.report) parts.push(`### 🔍 Market Research & Suppliers\n\n${finalReport.research.report}`);
                  formattedReport = parts.join("\n\n---\n\n");
                }

                if (formattedReport) {
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMsgId ? { ...msg, content: formattedReport } : msg
                    )
                  );

                  const histId = currentChatHistoryIdRef.current;
                  if (histId) {
                    const nextMessages = messagesRef.current.map((msg) =>
                      msg.id === assistantMsgId ? { ...msg, content: formattedReport } : msg
                    );
                    setTimeout(() => {
                      updateHistoryItem(histId, {
                        responsePreview: formattedReport.slice(0, 220),
                        plannerContext: activePlannerContext || undefined,
                        messages: nextMessages.map((m) => ({
                          id: m.id,
                          sender: m.sender,
                          content: m.content,
                          timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : String(m.timestamp),
                        })),
                      });
                    }, 0);
                  }
                }
              }
            } else if (data.type === "interrupted") {
              wasInterrupted = true;
              setInterrupt(data.data);
              setTimeout(() => interruptInputRef.current?.focus(), 100);
            }
          } catch {
            // Buffer chunk fragment waiting for complete line
          }
        }
      }
    } catch (err: any) {
      toast.error(err.message || "Failed to communicate with AI Agent.");
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId && !msg.content
            ? { ...msg, content: "⚠️ Sorry, an error occurred while connecting to the manufacturing copilot agent." }
            : msg
        )
      );
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

    const answerMsgId = Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();

    setMessages((prev) => [
      ...prev,
      { id: answerMsgId, sender: "user", content: cleanAnswer, timestamp: new Date() },
      { id: assistantMsgId, sender: "assistant", content: "", timestamp: new Date() },
    ]);
    
    setStreamingMsgId(assistantMsgId);

    let wasInterrupted = false;

    try {
      const res = await fetch(`${API_URL}/api/chat/resume`, {
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
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? { ...msg, content: msg.content + data.content }
                      : msg
                  )
                );
              }
            } else if (data.type === "final_report") {
              setStreamingMsgId(null);
              const finalReport = data.data?.final_report;
              if (finalReport) {
                let formattedReport = "";
                if (typeof finalReport.chatbot_response === "string" && finalReport.chatbot_response.trim()) {
                  formattedReport = finalReport.chatbot_response;
                } else if (finalReport.general?.report) {
                  formattedReport = finalReport.general.report;
                } else {
                  const parts = [];
                  if (finalReport.planning?.report) parts.push(`### 📋 Business & Factory Strategy\n\n${finalReport.planning.report}`);
                  if (finalReport.manufacturing?.report) parts.push(`### 🏭 Manufacturing & Technical Setup\n\n${finalReport.manufacturing.report}`);
                  if (finalReport.schemes?.report) parts.push(`### 💰 Subsidies & Financial Assistance\n\n${finalReport.schemes.report}`);
                  if (finalReport.research?.report) parts.push(`### 🔍 Market Research & Suppliers\n\n${finalReport.research.report}`);
                  formattedReport = parts.join("\n\n---\n\n");
                }

                if (formattedReport) {
                  setMessages((prev) =>
                    prev.map((msg) =>
                      msg.id === assistantMsgId ? { ...msg, content: formattedReport } : msg
                    )
                  );

                  const histId = currentChatHistoryIdRef.current;
                  if (histId) {
                    const nextMessages = messagesRef.current.map((msg) =>
                      msg.id === assistantMsgId ? { ...msg, content: formattedReport } : msg
                    );
                    setTimeout(() => {
                      updateHistoryItem(histId, {
                        responsePreview: formattedReport.slice(0, 220),
                        plannerContext: activePlannerContext || undefined,
                        messages: nextMessages.map((m) => ({
                          id: m.id,
                          sender: m.sender,
                          content: m.content,
                          timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : String(m.timestamp),
                        })),
                      });
                    }, 0);
                  }
                }
              }
            } else if (data.type === "interrupted") {
              wasInterrupted = true;
              setInterrupt(data.data);
              setTimeout(() => interruptInputRef.current?.focus(), 100);
            }
          } catch {
            // Buffer chunk fragment waiting for complete line
          }
        }
      }
    } catch (err: any) {
      toast.error(err.message);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMsgId && !msg.content
            ? { ...msg, content: "⚠️ Sorry, an error occurred while resuming the agent." }
            : msg
        )
      );
    } finally {
      if (!wasInterrupted) {
        setIsStreaming(false);
        setStreamingMsgId(null);
      }
      setActiveTool(null);
      setActiveAgent(null);
    }
  }

  // Filter history by tab and search
  const filteredHistory = history.filter((item) => {
    if (historyTab === "planner" && item.source !== "planner") return false;
    if (historyTab === "chat" && item.source !== "chat") return false;
    if (historySearch.trim()) {
      const q = historySearch.toLowerCase();
      const matchesQuery = item.query.toLowerCase().includes(q);
      const matchesPreview = item.responsePreview?.toLowerCase().includes(q);
      return matchesQuery || matchesPreview;
    }
    return true;
  });

  const plannerCount = history.filter((h) => h.source === "planner").length;
  const chatCount = history.filter((h) => h.source === "chat").length;

  if (!isReady || !token) return null;

  return (
    <div className="relative flex h-[calc(100vh-56px)] w-full overflow-hidden bg-slate-50/80">
      
      {/* ── Main Chat Column ── */}
      <div className="flex flex-1 flex-col h-full overflow-hidden relative">

        {/* ── Top-Right Floating Controls: History & New Chat ── */}
        <div className="absolute top-3.5 right-4 z-20 flex items-center gap-2">
          {messages.length > 0 && (
            <button
              onClick={startNewChat}
              className="flex items-center gap-1.5 rounded-xl border border-slate-200/90 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs backdrop-blur-md transition hover:bg-white hover:border-slate-300 hover:shadow-xs"
              title="Start a fresh conversation"
            >
              <Plus className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">New Chat</span>
            </button>
          )}

          <button
            onClick={() => setHistoryOpen(!historyOpen)}
            className={`flex items-center gap-2 rounded-xl px-3.5 py-1.5 text-xs font-semibold shadow-2xs backdrop-blur-md transition-all ${
              historyOpen
                ? "bg-violet-600 text-white shadow-md shadow-violet-300/40"
                : "border border-slate-200/90 bg-white/90 text-slate-700 hover:bg-white hover:border-slate-300 hover:shadow-xs"
            }`}
            aria-label="Toggle Activity History"
          >
            <History className="h-3.5 w-3.5" />
            <span>History</span>
            {isMounted && history.length > 0 && (
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                  historyOpen
                    ? "bg-violet-500 text-white"
                    : "bg-violet-100 text-violet-700"
                }`}
              >
                {history.length}
              </span>
            )}
          </button>
        </div>

        {/* ── Chat Messages Canvas ── */}
        <div className="flex-1 overflow-y-auto pt-6 pb-36 scroll-smooth">
          <div className="mx-auto max-w-3xl px-4 md:px-6 space-y-8">
            
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center min-h-[60vh] text-center animate-in fade-in duration-500 py-6">
                <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-xl shadow-violet-500/20">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h3 className="text-2xl font-bold tracking-tight text-slate-900 bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600">
                  How can I assist your manufacturing startup today?
                </h3>
                <p className="mt-2 max-w-md text-sm text-slate-500">
                  Ask our multi-agent system about factory setups, machinery sourcing, MSME subsidies, regulatory compliance, or break-even forecasts.
                </p>

                {/* Suggested Starters */}
                <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
                  {SUGGESTED_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => sendMessage(q.text)}
                      className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 text-left transition-all hover:border-violet-300 hover:shadow-lg hover:shadow-violet-100/50 hover:-translate-y-0.5"
                    >
                      <div className="absolute inset-0 bg-gradient-to-br from-violet-50/50 to-transparent opacity-0 transition-opacity group-hover:opacity-100"></div>
                      <div className="relative flex items-start gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-200 transition-colors group-hover:bg-violet-100 group-hover:text-violet-600 group-hover:ring-violet-200">
                          <q.icon className="h-4 w-4" />
                        </div>
                        <span className="flex-1 pt-1.5 text-sm font-medium text-slate-700 group-hover:text-slate-900">{q.text}</span>
                        <ChevronRight className="h-4 w-4 text-slate-300 group-hover:text-violet-500 transition-colors mt-1.5" />
                      </div>
                    </button>
                  ))}
                </div>

                {/* Resume from History Quick Strip */}
                {isMounted && history.length > 0 && (
                  <div className="mt-10 w-full max-w-2xl text-left">
                    <div className="mb-3 flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      <span className="flex items-center gap-1.5">
                        <History className="h-3.5 w-3.5 text-violet-600" />
                        Recent Activity from Planner & Chat
                      </span>
                      <button
                        onClick={() => setHistoryOpen(true)}
                        className="text-[11px] text-violet-600 hover:text-violet-800 lowercase font-medium tracking-normal hover:underline"
                      >
                        view all ({history.length}) &rarr;
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {history.slice(0, 4).map((item) => (
                        <div
                          key={item.id}
                          onClick={() => handleSelectHistoryItem(item)}
                          className="group relative cursor-pointer overflow-hidden rounded-xl border border-slate-200 bg-white p-3 text-left transition hover:border-violet-300 hover:shadow-md hover:-translate-y-0.5"
                        >
                          <div className="flex items-center justify-between gap-1 mb-1.5">
                            <span
                              className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                                item.source === "planner"
                                  ? "bg-amber-100 text-amber-800"
                                  : "bg-violet-100 text-violet-800"
                              }`}
                            >
                              {item.source === "planner" ? <Factory className="h-3 w-3" /> : <MessageSquare className="h-3 w-3" />}
                              {item.source === "planner" ? "Planner" : "Chat"}
                            </span>
                            <span className="text-[10px] text-slate-400 font-medium">
                              {formatHistoryDate(item.createdAt)}
                            </span>
                          </div>
                          <p className="line-clamp-2 text-xs font-semibold text-slate-800 group-hover:text-violet-900">
                            {item.query}
                          </p>
                          {item.responsePreview && (
                            <p className="mt-1 line-clamp-1 text-[11px] text-slate-400">
                              {item.responsePreview}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              messages.map((msg) => (
                <div key={msg.id} className={`flex gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}>
                  
                  {msg.sender === "assistant" && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white shadow-md text-xs font-bold">
                      AI
                    </div>
                  )}

                  <div className={`max-w-[85%] ${msg.sender === "user" ? "bg-slate-900 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 shadow-md" : "flex-1"}`}>
                    {msg.sender === "user" ? (
                      <p className="whitespace-pre-wrap text-sm leading-relaxed font-medium">{msg.content}</p>
                    ) : (
                      <>
                        {msg.content ? (
                          <div className="prose prose-slate prose-sm max-w-none prose-headings:font-bold prose-headings:tracking-tight prose-p:leading-relaxed prose-a:text-violet-600 prose-strong:font-semibold prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-violet-600 prose-code:before:content-none prose-code:after:content-none prose-table:text-xs prose-th:bg-slate-100 prose-td:border prose-th:border">
                            <MarkdownRenderer content={msg.content} />
                          </div>
                        ) : null}

                        {((isStreaming && msg.id === streamingMsgId) || (!msg.content && msg.sender === "assistant")) && (
                          <div className="flex items-center gap-2 py-2 mt-2 border-t border-slate-100 text-xs font-medium text-slate-500">
                            <span className="flex gap-1">
                              <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.3s]"></span>
                              <span className="h-2 w-2 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]"></span>
                              <span className="h-2 w-2 animate-bounce rounded-full bg-violet-500"></span>
                            </span>
                            {activeTool ? (
                              <span className="flex items-center gap-1.5 text-slate-600">
                                Executing <span className="font-mono text-violet-600 bg-violet-50 px-1.5 py-0.5 rounded border border-violet-100 font-semibold">{activeTool.replace(/_/g, " ")}</span>...
                              </span>
                            ) : activeAgent ? (
                              <span className="flex items-center gap-1.5 text-slate-600">
                                Agent <span className="font-mono text-purple-600 bg-purple-50 px-1.5 py-0.5 rounded border border-purple-100 font-semibold">{activeAgent.toUpperCase()}</span> analyzing...
                              </span>
                            ) : (
                              <span>Working on your response...</span>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  {msg.sender === "user" && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-700 shadow-sm">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              ))
            )}

            {/* Clarification Interrupt Box */}
            {interrupt && (
              <div className="flex gap-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-500 text-white shadow-md">
                  <Bot className="h-4 w-4" />
                </div>
                <div className="flex-1 rounded-2xl rounded-tl-sm border border-amber-200 bg-amber-50/50 p-5 shadow-sm">
                  <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-amber-600 flex items-center gap-1.5">
                    <MessageSquare className="h-3 w-3" />
                    Clarification Needed
                  </p>
                  <p className="text-sm font-medium text-amber-900 leading-relaxed">
                    {interrupt.question}
                  </p>
                </div>
              </div>
            )}

            <div ref={scrollRef} />
          </div>
        </div>

        {/* ── Floating Input Dock ── */}
        <div className="absolute bottom-0 left-0 right-0 z-10 bg-gradient-to-t from-slate-50 via-slate-50/90 to-transparent pt-10 pb-6">
          <div className="mx-auto max-w-3xl px-4 md:px-6">
            {/* Active Planner Plan Pill */}
            {activePlannerContext && (
              <div className="mb-2.5 flex items-center justify-between rounded-xl border border-amber-200/90 bg-gradient-to-r from-amber-50 to-orange-50/60 px-3.5 py-2 shadow-xs animate-in fade-in slide-in-from-bottom-1 duration-200">
                <div className="flex items-center gap-2 overflow-hidden">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-amber-500 text-white shadow-xs">
                    <Factory className="h-3 w-3" />
                  </span>
                  <span className="text-xs font-bold text-amber-950 shrink-0">Discussing Plan:</span>
                  <span className="truncate text-xs font-semibold text-amber-800">"{activePlannerContext.query}"</span>
                  <span className="hidden sm:inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-200/80 px-2 py-0.5 text-[10px] font-bold text-amber-900 border border-amber-300/60">
                    <Sparkles className="h-2.5 w-2.5 text-amber-600" />
                    Semantic Memory Active
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setActivePlannerContext(null);
                    toast.info("Cleared loaded factory plan context");
                  }}
                  className="ml-2 shrink-0 rounded-lg p-1 text-amber-700 hover:bg-amber-200/70 hover:text-amber-950 transition"
                  title="Clear loaded plan context"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}

            {interrupt ? (
              <div className="flex items-center gap-2 rounded-2xl border-2 border-amber-300 bg-white p-2 shadow-xl shadow-amber-100/50 transition-all focus-within:ring-4 focus-within:ring-amber-100">
                <span className="pl-2 text-amber-500 shrink-0">
                  <Bot className="h-5 w-5" />
                </span>
                <input
                  ref={interruptInputRef}
                  value={interruptAnswer}
                  onChange={(e) => setInterruptAnswer(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && submitInterruptAnswer()}
                  placeholder="Reply to continue execution..."
                  className="flex-1 bg-transparent py-2.5 text-sm outline-none placeholder:text-amber-400 text-amber-900 font-medium"
                  autoFocus
                />
                <button
                  onClick={submitInterruptAnswer}
                  disabled={!interruptAnswer.trim()}
                  className="mr-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 text-white transition hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-md"
                >
                  <Send className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl shadow-slate-200/50 transition-all focus-within:border-slate-300 focus-within:shadow-lg">
                <Textarea
                  ref={textareaRef}
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Message Manufacturing Copilot or discuss a plan..."
                  className="min-h-12 max-h-40 resize-none border-0 bg-transparent px-3 py-2.5 text-sm focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-slate-400 text-slate-900 font-medium"
                  disabled={isStreaming}
                />
                <button
                  onClick={() => sendMessage()}
                  disabled={isStreaming || !inputMessage.trim()}
                  className="mb-0.5 mr-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-slate-800 to-slate-900 text-white transition-all hover:scale-105 hover:shadow-lg disabled:opacity-30 disabled:scale-100 disabled:cursor-not-allowed disabled:hover:shadow-none shadow-md"
                >
                  {isStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                </button>
              </div>
            )}
            <p className="mt-2 text-center text-[11px] text-slate-400 font-medium">
              {interrupt ? (
                "Agent is waiting — press Enter or click Send to continue"
              ) : (
                <>AI Copilot can make mistakes. Verify critical factory and financial details.</>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* ── Slide-Over Activity History Panel (Right to Left) ── */}
      {historyOpen && (
        <>
          {/* Backdrop for outside click */}
          <div
            className="fixed inset-0 z-50 bg-slate-950/25 backdrop-blur-xs transition-opacity animate-in fade-in duration-200"
            onClick={() => setHistoryOpen(false)}
          />

          <aside className="fixed inset-y-0 right-0 z-50 flex h-screen w-full sm:w-96 md:w-[440px] flex-col border-l border-slate-200 bg-white shadow-2xl animate-in slide-in-from-right duration-300 ease-out">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-100 p-4 shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-100 text-violet-700">
                  <History className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Activity History</h3>
                  <p className="text-[11px] text-slate-500">
                    {history.length} records • Planner runs & Chat conversations
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                {history.length > 0 && (
                  <button
                    onClick={() => {
                      if (confirm("Are you sure you want to clear this activity history?")) {
                        clearHistory(historyTab === "all" ? undefined : historyTab);
                        toast.success("History cleared");
                      }
                    }}
                    className="flex h-8 items-center gap-1 rounded-lg px-2 text-xs font-medium text-slate-400 hover:bg-rose-50 hover:text-rose-600 transition"
                    title="Clear history"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Clear</span>
                  </button>
                )}
                <button
                  onClick={() => setHistoryOpen(false)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition"
                  aria-label="Close history"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Search Input & Filter Tabs */}
            <div className="p-3 border-b border-slate-100 shrink-0 bg-slate-50/50">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  value={historySearch}
                  onChange={(e) => setHistorySearch(e.target.value)}
                  placeholder="Search past queries or topics..."
                  className="w-full rounded-xl border border-slate-200 bg-white py-1.5 pl-8 pr-7 text-xs font-medium text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
                />
                {historySearch && (
                  <button
                    onClick={() => setHistorySearch("")}
                    className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600 text-xs font-bold"
                  >
                    ×
                  </button>
                )}
              </div>

              {/* Tabs: All | Planner | Chat */}
              <div className="mt-2.5 flex gap-1 rounded-xl bg-slate-200/70 p-1">
                <button
                  onClick={() => setHistoryTab("all")}
                  className={`flex-1 rounded-lg py-1 text-center text-xs font-semibold transition ${
                    historyTab === "all"
                      ? "bg-white text-slate-900 shadow-xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  All ({history.length})
                </button>
                <button
                  onClick={() => setHistoryTab("planner")}
                  className={`flex items-center justify-center gap-1 flex-1 rounded-lg py-1 text-center text-xs font-semibold transition ${
                    historyTab === "planner"
                      ? "bg-white text-amber-800 shadow-xs"
                      : "text-slate-600 hover:text-amber-800"
                  }`}
                >
                  <Factory className="h-3 w-3" />
                  <span>Planner ({plannerCount})</span>
                </button>
                <button
                  onClick={() => setHistoryTab("chat")}
                  className={`flex items-center justify-center gap-1 flex-1 rounded-lg py-1 text-center text-xs font-semibold transition ${
                    historyTab === "chat"
                      ? "bg-white text-violet-800 shadow-xs"
                      : "text-slate-600 hover:text-violet-800"
                  }`}
                >
                  <MessageSquare className="h-3 w-3" />
                  <span>Chat ({chatCount})</span>
                </button>
              </div>
            </div>

            {/* Scrollable Items List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
              {filteredHistory.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-64 text-center px-4">
                  <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                    <Clock className="h-5 w-5" />
                  </div>
                  <p className="text-sm font-semibold text-slate-700">No activity records found</p>
                  <p className="mt-1 text-xs text-slate-400 max-w-xs">
                    {historySearch
                      ? `No queries matched "${historySearch}". Try another search term.`
                      : historyTab === "planner"
                      ? "No Planner plans found yet. Generate plans in Business Planner to see them here."
                      : historyTab === "chat"
                      ? "No Chat conversations found yet. Ask a question to start building your history."
                      : "All plans you generate in Business Planner and all messages in Chat will be recorded here."}
                  </p>
                </div>
              ) : (
                filteredHistory.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleSelectHistoryItem(item)}
                    className="group relative cursor-pointer rounded-xl border border-slate-200 bg-white p-3 shadow-2xs transition-all hover:border-violet-300 hover:shadow-md hover:-translate-y-0.5"
                  >
                    <div className="flex items-center justify-between gap-1 mb-1.5">
                      <span
                        className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                          item.source === "planner"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-violet-100 text-violet-800"
                        }`}
                      >
                        {item.source === "planner" ? <Factory className="h-3 w-3" /> : <MessageSquare className="h-3 w-3" />}
                        {item.source === "planner" ? "Factory Plan" : "Chat Session"}
                      </span>

                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-medium text-slate-400">
                          {formatHistoryDate(item.createdAt)}
                        </span>
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            removeHistoryItem(item.id);
                            if (item.source === "planner" && token) {
                              try {
                                await deleteUserPlan(item.id, token);
                                queryClient.invalidateQueries({ queryKey: ["userPlans", token] });
                              } catch {}
                            }
                            toast.success("Removed from history");
                          }}
                          className="opacity-0 group-hover:opacity-100 transition p-1 text-slate-400 hover:text-rose-600 rounded"
                          title="Delete item"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </div>

                    <h4 className="text-xs font-semibold text-slate-900 line-clamp-2 leading-relaxed group-hover:text-violet-950">
                      {item.query}
                    </h4>

                    {item.responsePreview && (
                      <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500 line-clamp-2 border-l-2 border-slate-200 pl-2">
                        {item.responsePreview}
                      </p>
                    )}

                    {/* Card Actions */}
                    <div className="mt-2.5 flex items-center justify-between pt-2 border-t border-slate-100 text-[11px]">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSelectHistoryItem(item);
                        }}
                        className="inline-flex items-center gap-1 font-semibold text-violet-600 hover:text-violet-800"
                      >
                        <MessageSquare className="h-3 w-3" />
                        {item.messages && item.messages.length > 0 ? "Restore Thread" : "Discuss in Chat"}
                      </button>

                      {item.source === "planner" && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setPlannerQuery(item.query);
                            router.push("/planner");
                          }}
                          className="inline-flex items-center gap-1 font-medium text-slate-500 hover:text-slate-800"
                        >
                          <span>Open in Planner</span>
                          <ExternalLink className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </aside>
        </>
      )}

    </div>
  );
}
