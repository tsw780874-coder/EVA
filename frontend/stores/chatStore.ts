"use client"
import { create } from "zustand";
import { api, apiSSE } from "@/lib/api";

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ProductData {
  id: string;
  name: string;
  platform: string;
  price: number;
  original_price?: number;
  rating?: number;
  review_count?: number;
  url?: string;
  image_url?: string;
}

export interface SSEEvent {
  type: "agent_start" | "agent_progress" | "agent_result" | "final_report" | "done" | "error" | "token"
        | "hybrid_sources" | "hybrid_confidence" | "hybrid_conflict" | "hybrid_guard" | "trust" | "perf"
        | "verification";  // v8: verification gate result
  agent?: string;
  message?: string;
  markdown?: string;
  text?: string;
  node?: string;
  data?: Record<string, unknown>;
  products?: ProductData[];
  // Hybrid AI fields
  sources?: HybridSourceInfo[];
  confidence?: number;
  level?: string;
  breakdown?: Record<string, number>;
  conflicts?: string[];
  passed?: boolean;
  warnings?: string[];
  search_layers?: string[];
  total_products?: number;
  hallucination_passed?: boolean;
  hybrid_sources?: string[];
  hybrid_latency_ms?: number;
  timing?: Record<string, number>;
  data_source?: string;
  citation?: string;
  confidence_warning?: string;
  // v8 verification fields
  action?: string;
  failed_checks?: string[];
}

export interface HybridSourceInfo {
  source: string;
  label: string;
}

// ═══════════════════════════════════════════════════════════════════════
// v8 Verification status
// ═══════════════════════════════════════════════════════════════════════

export interface VerificationStatus {
  passed: boolean;
  action: string;         // "allow" | "block" | "flag"
  confidence: number;
  failedChecks: string[];
  warnings: string[];
}

// ═══════════════════════════════════════════════════════════════════════
// Hybrid AI state (managed in store, not local useState)
// ═══════════════════════════════════════════════════════════════════════

export interface HybridState {
  sources: HybridSourceInfo[];
  confidence: number;
  confLevel: string;
  confBreakdown: Record<string, number>;
  conflicts: string[];
  warnings: string[];
  hallucinationPassed: boolean;
  perfTiming: Record<string, number>;
  verification: VerificationStatus | null;
}

const EMPTY_HYBRID: HybridState = {
  sources: [],
  confidence: 0,
  confLevel: "",
  confBreakdown: {},
  conflicts: [],
  warnings: [],
  hallucinationPassed: true,
  perfTiming: {},
  verification: null,
};

// ═══════════════════════════════════════════════════════════════════════

interface ChatState {
  sessions: ChatSession[];
  currentSession: ChatSession | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamEvents: Record<string, unknown>[];
  streamTokens: string;
  abortController: AbortController | null;
  useHybrid: boolean;  // v7: enables multi-source intelligence
  hybrid: HybridState;  // v8: hybrid AI state

  // Per-session product cache — survives session switches
  productsBySession: Record<string, ProductData[]>;
  favoritedIds: string[];  // product IDs already favorited in current session view

  loadSessions: () => Promise<void>;
  createSession: (title?: string) => Promise<ChatSession>;
  loadMessages: (sessionId: string) => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  sendMessage: (
    sessionId: string,
    content: string,
    onEvent: (event: SSEEvent) => void,
    onDone: () => void,
  ) => Promise<void>;
  cancelStream: () => void;
  toggleHybrid: () => void;
  updateHybrid: (patch: Partial<HybridState>) => void;  // v8
  resetHybrid: () => void;  // v8
  setProducts: (sessionId: string, products: ProductData[]) => void;
  addFavoritedId: (productId: string) => void;
  clearFavorites: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  isStreaming: false,
  streamEvents: [],
  streamTokens: "",
  abortController: null,
  useHybrid: true,  // v7 hybrid by default, with graceful fallback
  hybrid: { ...EMPTY_HYBRID },  // v8 hybrid state
  productsBySession: {},  // per-session product cache
  favoritedIds: [],

  loadSessions: async () => {
    const data = await api<ChatSession[]>("/api/v1/chat/sessions");
    set({ sessions: data });
  },

  createSession: async (title = "新对话") => {
    const data = await api<ChatSession>("/api/v1/chat/sessions", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
    set((s) => ({ sessions: [data, ...s.sessions], currentSession: data }));
    return data;
  },

  loadMessages: async (sessionId) => {
    const data = await api<{ messages: ChatMessage[] }>(
      `/api/v1/chat/sessions/${sessionId}`
    );
    set({ currentSession: data as unknown as ChatSession, messages: data.messages });
  },

  selectSession: async (sessionId) => {
    const data = await api<{
      id: string; title: string; created_at: string; updated_at: string;
      messages: (ChatMessage & { metadata_?: Record<string, unknown> | null })[];
    }>(
      `/api/v1/chat/sessions/${sessionId}`
    );
    set({
      currentSession: {
        id: data.id,
        title: data.title,
        created_at: data.created_at,
        updated_at: data.updated_at,
        message_count: data.messages.length,
      },
      messages: data.messages,
    });

    // Restore products from the last assistant message's metadata
    const state = get();
    if (!state.productsBySession[sessionId]) {
      // Scan messages in reverse to find the most recent agent_result products
      for (let i = data.messages.length - 1; i >= 0; i--) {
        const meta = data.messages[i]?.metadata_;
        if (meta && Array.isArray((meta as any).products) && (meta as any).products.length > 0) {
          state.setProducts(sessionId, (meta as any).products as ProductData[]);
          break;
        }
      }
    }
  },

  deleteSession: async (sessionId) => {
    await api(`/api/v1/chat/sessions/${sessionId}`, { method: "DELETE" });
    set((s) => ({
      sessions: s.sessions.filter((sess) => sess.id !== sessionId),
      currentSession: s.currentSession?.id === sessionId ? null : s.currentSession,
      messages: s.currentSession?.id === sessionId ? [] : s.messages,
    }));
  },

  sendMessage: async (sessionId, content, onEvent, onDone) => {
    set({ isStreaming: true, streamEvents: [], streamTokens: "" });

    const { useHybrid } = get();
    const streamPath = useHybrid
      ? `/api/v1/chat/sessions/${sessionId}/stream/hybrid`
      : `/api/v1/chat/sessions/${sessionId}/stream`;

    const onFinally = () => {
      set({ isStreaming: false });
      onDone();
    };

    const controller = await apiSSE(
      streamPath,
      { content },
      (event) => {
        // v7: 纯回调 — 不经过 Zustand store，避免每次事件触发全局 rerender
        onEvent(event as unknown as SSEEvent);
      },
      () => {
        set({ isStreaming: false });
        onDone();
      },
      async (err) => {
        if (useHybrid && err.message.includes("404")) {
          set({ useHybrid: false });
          try {
            await get().sendMessage(sessionId, content, onEvent, onDone);
            return;
          } catch {
            // Fallback also failed
          }
        }
        set({ isStreaming: false });
        // 直接通过 onEvent 报告错误，不经过 store
        onEvent({ type: "error", message: err.message } as unknown as SSEEvent);
        onDone();
      },
    );

    set({ abortController: controller });
  },

  cancelStream: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ isStreaming: false, abortController: null, streamTokens: "" });
    }
  },

  toggleHybrid: () => {
    set((s) => ({ useHybrid: !s.useHybrid }));
  },

  updateHybrid: (patch) => {
    set((s) => ({ hybrid: { ...s.hybrid, ...patch } }));
  },

  resetHybrid: () => {
    set({ hybrid: { ...EMPTY_HYBRID } });
  },

  setProducts: (sessionId, products) => {
    set((s) => ({
      productsBySession: { ...s.productsBySession, [sessionId]: products },
    }));
  },

  addFavoritedId: (productId) => {
    set((s) => ({
      favoritedIds: s.favoritedIds.includes(productId)
        ? s.favoritedIds
        : [...s.favoritedIds, productId],
    }));
  },

  clearFavorites: () => {
    set({ favoritedIds: [] });
  },
}));
