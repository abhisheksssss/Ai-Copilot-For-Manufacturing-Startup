// store/use-copilot-store.ts
import { create } from "zustand";

export type HistoryItem = {
  id: string;
  query: string;
  createdAt: string;
};

type CopilotState = {
  query: string;
  history: HistoryItem[];
  setQuery: (query: string) => void;
  addHistory: (query: string) => void;
  clearHistory: () => void;
};

export const useCopilotStore = create<CopilotState>((set) => ({
  query:
    "I want to start a small food processing unit in Pune with 25 lakh investment. Help me with factory setup, machinery, licenses, schemes, and market strategy.",
  history: [],
  setQuery: (query) => set({ query }),
  addHistory: (query) =>
    set((state) => ({
      history: [
        {
          id: crypto.randomUUID(),
          query,
          createdAt: new Date().toISOString(),
        },
        ...state.history,
      ].slice(0, 8),
    })),
  clearHistory: () => set({ history: [] }),
}));