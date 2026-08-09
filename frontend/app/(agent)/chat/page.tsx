"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  BadgeIndianRupee,
  Bot,
  Building2,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Factory,
  Loader2,
  MessageSquare,
  Search,
  Send,
  Sparkles,
  Trash2,
  User,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";

import { MarkdownRenderer } from "@/components/markdown-renderer";
import { useAuthStore } from "@/store/use-auth-store";
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

export default function ChatPage() {
  const router = useRouter();
  const { token, user, isReady, initializeAuth } = useAuthStore();

  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);

  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [completedAgents, setCompletedAgents] = useState<Record<string, boolean>>({});

  const [interrupt, setInterrupt] = useState<{ action: string; question: string } | null>(null);
  const [interruptAnswer, setInterruptAnswer] = useState("");
  const interruptInputRef = useRef<HTMLInputElement>(null);

  // Tracks which assistant message is currently being streamed
  // While streaming: show raw preview. On final_report: switch to full MarkdownRenderer.
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    initializeAuth();
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

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    if (!overrideQuery) setInputMessage("");

    setIsStreaming(true);
    setActiveAgent(null);
    setActiveTool(null);
    setCompletedAgents({});
    setInterrupt(null);
    setInterruptAnswer("");
    setStreamingMsgId(assistantMsgId); // Mark this message as actively streaming

    let wasInterrupted = false;

    try {
      const res = await fetch(`${API_URL}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ query }),
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
    
    setInterrupt(null);
    setInterruptAnswer("");
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

  if (!isReady || !token) return null;

  return (
    <div className="relative flex h-[calc(100vh-56px)] w-full flex-col bg-slate-50/80 overflow-hidden">
      
      {/* ── Floating Top Header ── */}
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-6 py-4 bg-gradient-to-b from-slate-50/90 to-transparent backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-white shadow-lg shadow-slate-900/20">
            <Bot className="h-4 w-4" />
          </div>
          <div>
            <h2 className="flex items-center gap-2 text-sm font-bold text-slate-900">
              Manufacturing Copilot
              <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-600 border border-emerald-100">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                LIVE
              </span>
            </h2>
            <p className="text-[11px] text-slate-500 font-medium hidden sm:block">Multi-agent system for factory setup & analysis</p>
          </div>
        </div>

        <Button
          onClick={() => router.push("/planner")}
          variant="outline"
          size="sm"
          className="hidden sm:flex items-center gap-2 border-slate-200 bg-white/80 text-xs font-semibold text-slate-600 hover:bg-white hover:text-slate-900 transition-all shadow-sm"
        >
          <ClipboardCheck className="h-3.5 w-3.5" />
          Full Planner
        </Button>
      </div>

      {/* ── Chat Messages Canvas ── */}
      <div className="flex-1 overflow-y-auto pt-20 pb-40 scroll-smooth">
        <div className="mx-auto max-w-3xl px-4 md:px-6 space-y-8">
          
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center min-h-[60vh] text-center animate-in fade-in duration-500">
              <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-xl shadow-violet-500/20">
                <Sparkles className="h-7 w-7" />
              </div>
              <h3 className="text-2xl font-bold tracking-tight text-slate-900 bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600">
                How can I assist your manufacturing setup today?
              </h3>
              <p className="mt-2 max-w-md text-sm text-slate-500">
                Leverage our multi-agent system for factory planning, machinery sourcing, MSME subsidies, and market research.
              </p>

              <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
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
                            <span>Working on your report...</span>
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
                placeholder="Message Manufacturing Copilot..."
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
              <>AI Copilot can make mistakes. Verify critical manufacturing data.</>
            )}
          </p>
        </div>
      </div>
    </div>
  );
}
