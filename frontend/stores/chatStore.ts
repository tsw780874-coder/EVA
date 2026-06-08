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
  type: "agent_start" | "agent_progress" | "agent_result" | "final_report" | "done" | "error" | "token";
  agent?: string;
  message?: string;
  markdown?: string;
  text?: string;
  node?: string;
  data?: Record<string, unknown>;
  products?: ProductData[];
}

interface ChatState {
  sessions: ChatSession[];
  currentSession: ChatSession | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamEvents: Record<string, unknown>[];
  streamTokens: string;
  abortController: AbortController | null;

  loadSessions: () => Promise<void>;
  createSession: (title?: string) => Promise<ChatSession>;
  loadMessages: (sessionId: string) => Promise<void>;
  sendMessage: (
    sessionId: string,
    content: string,
    onEvent: (event: SSEEvent) => void,
    onDone: () => void,
  ) => Promise<void>;
  cancelStream: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  isStreaming: false,
  streamEvents: [],
  streamTokens: "",
  abortController: null,

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

  sendMessage: async (sessionId, content, onEvent, onDone) => {
    set({ isStreaming: true, streamEvents: [], streamTokens: "" });

    const controller = await apiSSE(
      `/api/v1/chat/sessions/${sessionId}/stream`,
      { content },
      (event) => {
        set((s) => ({
          streamEvents: [...s.streamEvents, event],
          streamTokens: event.type === "token"
            ? s.streamTokens + (event.text || "")
            : s.streamTokens,
        }));
        const sseEvent = event as unknown as SSEEvent;
        onEvent(sseEvent);
      },
      () => {
        set({ isStreaming: false });
        onDone();
      },
      (err) => {
        set({ isStreaming: false });
        set((s) => ({
          streamEvents: [
            ...s.streamEvents,
            { type: "error", message: err.message },
          ],
        }));
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
}));
