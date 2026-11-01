// store/use-copilot-store.ts
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type SavedChatMessage = {
  id: string;
  sender: "user" | "assistant";
  content: string;
  timestamp: string;
};

export type HistoryItem = {
  id: string;
  query: string;
  createdAt: string;
  source: "planner" | "chat";
  responsePreview?: string;
  messages?: SavedChatMessage[];
  plannerContext?: { query: string; id?: string };
};

type CopilotState = {
  query: string;
  history: HistoryItem[];
  setQuery: (query: string) => void;
  addHistory: (
    query: string,
    source?: "planner" | "chat",
    responsePreview?: string,
    messages?: SavedChatMessage[],
    customId?: string
  ) => string;
  syncBackendPlans: (
    backendPlans: Array<{
      id: string;
      query: string;
      created_at?: string;
      title?: string;
      plan_data?: any;
    }>
  ) => void;
  updateHistoryItem: (id: string, updates: Partial<HistoryItem>) => void;
  removeHistoryItem: (id: string) => void;
  clearHistory: (source?: "planner" | "chat") => void;
};

export const useCopilotStore = create<CopilotState>()(
  persist(
    (set) => ({
      query:
        "I want to start a small food processing unit in Pune with 25 lakh investment. Help me with factory setup, machinery, licenses, schemes, and market strategy.",
      history: [],
      setQuery: (query) => set({ query }),
      addHistory: (query, source = "planner", responsePreview, messages, customId) => {
        const trimmedQuery = query.trim();
        const id =
          customId ||
          (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
            ? crypto.randomUUID()
            : `hist_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`);
        if (!trimmedQuery) return id;

        set((state) => {
          const filtered = state.history.filter(
            (item) =>
              item.id !== id &&
              !(
                item.query.trim().toLowerCase() === trimmedQuery.toLowerCase() &&
                item.source === source
              )
          );
          const newItem: HistoryItem = {
            id,
            query: trimmedQuery,
            createdAt: new Date().toISOString(),
            source,
            responsePreview: responsePreview ? responsePreview.slice(0, 240) : undefined,
            messages,
          };
          return {
            history: [newItem, ...filtered].slice(0, 50),
          };
        });
        return id;
      },
      syncBackendPlans: (backendPlans) => {
        if (!backendPlans || !backendPlans.length) return;
        set((state) => {
          let updated = false;
          const newHistory = [...state.history];

          for (const bp of backendPlans) {
            const trimmedQuery = bp.query.trim();
            if (!trimmedQuery) continue;

            const existingIndex = newHistory.findIndex(
              (item) =>
                item.id === bp.id ||
                (item.source === "planner" &&
                  item.query.trim().toLowerCase() === trimmedQuery.toLowerCase())
            );

            let preview = "";
            if (bp.plan_data?.final_report) {
              const r = bp.plan_data.final_report;
              const planningText =
                typeof r.planning?.report === "string"
                  ? r.planning.report
                  : typeof r.planning?.report === "object"
                  ? JSON.stringify(r.planning.report)
                  : "";
              preview = planningText.slice(0, 240);
            }
            if (!preview) {
              preview = bp.title || trimmedQuery;
            }

            const itemCreatedAt = bp.created_at || new Date().toISOString();

            if (existingIndex >= 0) {
              const current = newHistory[existingIndex];
              const shouldUpdate =
                current.id !== bp.id ||
                (!current.responsePreview && preview) ||
                (current.createdAt !== itemCreatedAt && bp.created_at);

              if (shouldUpdate) {
                newHistory[existingIndex] = {
                  ...current,
                  id: bp.id,
                  responsePreview: preview || current.responsePreview,
                  createdAt: itemCreatedAt,
                };
                updated = true;
              }
            } else {
              newHistory.push({
                id: bp.id,
                query: trimmedQuery,
                createdAt: itemCreatedAt,
                source: "planner",
                responsePreview: preview,
              });
              updated = true;
            }
          }

          if (!updated) return state;

          newHistory.sort(
            (a, b) =>
              new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
          );

          return {
            history: newHistory.slice(0, 50),
          };
        });
      },
      updateHistoryItem: (id, updates) =>
        set((state) => ({
          history: state.history.map((item) =>
            item.id === id ? { ...item, ...updates } : item
          ),
        })),
      removeHistoryItem: (id) =>
        set((state) => ({
          history: state.history.filter((item) => item.id !== id),
        })),
      clearHistory: (source) =>
        set((state) => ({
          history: source ? state.history.filter((item) => item.source !== source) : [],
        })),
    }),
    {
      name: "manufacturing_copilot_store_v2",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        query: state.query,
        history: state.history,
      }),
    }
  )
);
