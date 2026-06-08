"use client"
import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Plus, MessageSquare, LayoutGrid, Settings, Send,
  Layers, Zap, ShieldCheck, Globe2, Loader2,
  Heart, ExternalLink, Star
} from 'lucide-react';
import Link from 'next/link';
import { useChatStore, type SSEEvent, type ProductData } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { api } from '@/lib/api';

const SUGGESTED_QUERIES = [
  "对比 iPhone 15 Pro Max 全网最低价",
  "寻找得物上的高性价比闪电倒钩",
  "分析近期唯品会美妆优惠趋势"
];

interface DisplayMessage {
  role: 'user' | 'assistant' | 'agent';
  content: string;
  agentName?: string;
}

export default function ChatStudio() {
  const [inputText, setInputText] = useState("");
  const [displayMessages, setDisplayMessages] = useState<DisplayMessage[]>([]);
  const [products, setProducts] = useState<ProductData[]>([]);
  const [favoritedIds, setFavoritedIds] = useState<Set<string>>(new Set());
  const [favoritingId, setFavoritingId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState("");  // token-level streaming
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const user = useAuthStore((s) => s.user);
  const {
    sessions, currentSession,
    isStreaming,
    loadSessions, createSession, sendMessage,
  } = useChatStore();

  useEffect(() => { loadSessions().catch(() => {}); }, []);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayMessages, products, streamingText]);

  const handleFavorite = async (p: ProductData) => {
    setFavoritingId(p.id);
    try {
      await api("/api/v1/favorites", {
        method: "POST",
        body: JSON.stringify({
          product_id: p.id,
          product_name: p.name,
          product_platform: p.platform,
          product_price: p.price,
          product_url: p.url || "",
          product_image_url: p.image_url || "",
        }),
      });
      setFavoritedIds(prev => new Set(prev).add(p.id));
    } catch (err: unknown) {
      if ((err as Error).message?.includes("409") || (err as Error).message?.includes("已收藏")) {
        setFavoritedIds(prev => new Set(prev).add(p.id));
      }
    }
    setFavoritingId(null);
  };

  const handleSend = async (query?: string) => {
    const content = query || inputText;
    if (!content.trim() || isStreaming) return;
    setInputText('');
    setDisplayMessages((prev) => [...prev, { role: 'user', content }]);
    setProducts([]);
    setStreamingText("");

    // --- Instant thinking indicator (don't wait for SSE) ---
    setDisplayMessages((prev) => [
      ...prev,
      { role: 'agent', content: '正在分析您的需求...', agentName: 'think' },
    ]);

    let sessionId = currentSession?.id;
    if (!sessionId) {
      const session = await createSession(content.slice(0, 30));
      sessionId = session.id;
    }

    // Track streaming tokens for progressive display
    let tokenBuffer = "";

    await sendMessage(sessionId, content, (event: SSEEvent) => {
      if (event.type === 'agent_start') {
        // Replace the optimistic "thinking" message
        setDisplayMessages((prev) => {
          const filtered = prev.filter(m => !(m.role === 'agent' && m.agentName === 'think'));
          return [...filtered, { role: 'agent', content: '正在分析您的需求...', agentName: 'think' }];
        });
      }

      if (event.type === 'token') {
        tokenBuffer += (event.text || "");
        setStreamingText(tokenBuffer);
      }

      if (event.type === 'agent_result' && event.agent === 'search_agent' && event.products) {
        setProducts(event.products);
        // Clear token buffer since search is done
        setStreamingText("");
        tokenBuffer = "";
      }

      if (event.type === 'agent_progress') {
        setDisplayMessages((prev) => {
          // Remove previous think + streaming messages
          const filtered = prev.filter(m =>
            !(m.role === 'agent' && (m.agentName === 'think' || m.agentName === 'streaming'))
          );
          return [...filtered, { role: 'agent', content: event.message || '', agentName: event.agent }];
        });
      }

      if (event.type === 'final_report') {
        setStreamingText("");
        tokenBuffer = "";
        setDisplayMessages((prev) => {
          const filtered = prev.filter(m =>
            !(m.role === 'agent' && (m.agentName === 'think' || m.agentName === 'streaming'))
          );
          return [...filtered, { role: 'assistant', content: event.markdown || '' }];
        });
      }
    }, () => {
      loadSessions().catch(() => {});
      setStreamingText("");
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const platformColor = (platform: string) => {
    const map: Record<string, string> = {
      "京东": "bg-red-50 text-red-600 border-red-100",
      "天猫": "bg-red-50 text-red-500 border-red-100",
      "淘宝": "bg-orange-50 text-orange-600 border-orange-100",
      "得物": "bg-indigo-50 text-indigo-600 border-indigo-100",
      "拼多多": "bg-yellow-50 text-yellow-600 border-yellow-100",
    };
    return map[platform] || "bg-gray-50 text-gray-600 border-gray-100";
  };

  return (
    <div className="h-screen bg-[#FDFDFD] text-[#1d1d1f] flex overflow-hidden font-sans">

      {/* 左侧边栏 */}
      <aside className="w-64 border-r border-black/[0.04] bg-[#F9F9FB] flex flex-col">
        <Link href="/" className="p-6 flex items-center gap-3 hover:opacity-60 transition-opacity">
          <div className="w-8 h-8 bg-black rounded-lg flex items-center justify-center text-white font-black">E</div>
          <span className="font-bold tracking-widest text-sm uppercase">EVA Assistant</span>
        </Link>

        <div className="px-4 mb-4">
          <button
            onClick={() => { setDisplayMessages([]); setProducts([]); createSession(); }}
            className="w-full py-2 px-4 rounded-full border border-black/[0.05] bg-white shadow-sm flex items-center justify-center gap-2 text-xs font-bold hover:bg-black hover:text-white transition-all"
          >
            <Plus size={14} /> 新建对话
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-4 space-y-1">
          <p className="px-4 py-2 text-[10px] font-bold text-gray-400 uppercase tracking-widest">最近搜索</p>
          {sessions.slice(0, 10).map((s) => (
            <div key={s.id} className="flex items-center gap-3 px-4 py-2 text-sm text-gray-500 hover:bg-white hover:text-black rounded-xl cursor-pointer transition-all group">
              <MessageSquare size={14} className="opacity-50 group-hover:opacity-100" />
              <span className="truncate">{s.title}</span>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="px-4 py-2 text-xs text-gray-300">暂无对话记录</p>
          )}
        </nav>

        <div className="p-6 border-t border-black/[0.04] space-y-4 text-gray-400">
          <Link href="/reports" className="flex items-center gap-3 text-sm hover:text-black"><LayoutGrid size={16} /> 报告中心</Link>
          <Link href="/settings" className="flex items-center gap-3 text-sm hover:text-black"><Settings size={16} /> 设置</Link>
          <Link href="/favorites" className="flex items-center gap-3 text-sm hover:text-black"><Heart size={16} /> 我的珍藏</Link>
        </div>
      </aside>

      {/* 中间主对话区 */}
      <main className="flex-1 flex flex-col relative bg-white">
        <header className="h-16 border-b border-black/[0.02] flex items-center justify-between px-8 bg-white/80 backdrop-blur-md z-10">
          <div className="flex items-center gap-4">
            {user && (
              <span className="text-xs text-gray-400">👋 {user.name}</span>
            )}
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-50 text-[10px] font-bold text-green-600 border border-green-100">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              AGENT ACTIVE
            </div>
          </div>
          <div className="flex items-center gap-4 text-gray-400">
            <Globe2 size={18} />
            <Layers size={18} />
          </div>
        </header>

        {/* 消息滚动区 */}
        <div className="flex-1 overflow-y-auto px-8 py-12 space-y-10">
          {displayMessages.length === 0 && (
            <div className="max-w-3xl mx-auto flex gap-6">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-500 to-sky-400 flex items-center justify-center text-white shrink-0 shadow-lg shadow-indigo-100">
                <Zap size={20} fill="white" />
              </div>
              <div className="space-y-4">
                <h2 className="text-3xl font-serif italic text-black">您好，我是 EVA。</h2>
                <p className="text-lg text-gray-500 leading-relaxed">
                  我已连接多个主流电商平台。您可以发送商品链接或描述采购需求，我将为您进行深度比价和趋势分析。
                </p>
                <div className="grid grid-cols-1 gap-2 pt-4">
                  {SUGGESTED_QUERIES.map((q, i) => (
                    <button key={i} onClick={() => handleSend(q)} className="text-left px-5 py-3 rounded-2xl border border-black/[0.04] text-sm text-gray-600 hover:bg-black hover:text-white transition-all w-fit">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 商品卡片区 */}
          {products.length > 0 && (
            <div className="max-w-3xl mx-auto">
              <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mb-4">
                搜索到 {products.length} 个商品
              </p>
              <div className="grid grid-cols-1 gap-4">
                {products.map((p) => {
                  const isFaved = favoritedIds.has(p.id);
                  const isFaving = favoritingId === p.id;
                  return (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="bg-white border border-black/[0.06] rounded-2xl p-5 flex items-start gap-4 hover:shadow-lg hover:border-black/[0.12] transition-all group"
                    >
                      <div className="w-16 h-16 rounded-xl bg-gray-50 shrink-0 flex items-center justify-center overflow-hidden">
                        {p.image_url ? (
                          <img
                            src={p.image_url}
                            alt={p.name}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              (e.target as HTMLImageElement).style.display = 'none';
                              (e.target as HTMLImageElement).nextElementSibling?.classList.remove('hidden');
                            }}
                          />
                        ) : null}
                        <span className={`text-[10px] font-bold text-gray-400 ${p.image_url ? 'hidden' : ''}`}>
                          {p.platform.slice(0, 2)}
                        </span>
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h4 className="font-bold text-sm leading-snug">{p.name}</h4>
                            <div className="flex items-center gap-2 mt-1.5">
                              <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold border ${platformColor(p.platform)}`}>
                                {p.platform}
                              </span>
                              {p.rating && (
                                <span className="text-[10px] text-gray-400">⭐ {p.rating}</span>
                              )}
                              {p.review_count && (
                                <span className="text-[10px] text-gray-400">{p.review_count} 评价</span>
                              )}
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <p className="text-xl font-black tracking-tight text-black">
                              ¥{p.price?.toLocaleString()}
                            </p>
                            {p.original_price && p.original_price > p.price && (
                              <p className="text-xs text-gray-400 line-through">
                                ¥{p.original_price?.toLocaleString()}
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-black/[0.03]">
                          {p.url && (
                            <a
                              href={p.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1 text-[10px] font-bold text-gray-400 hover:text-black transition-colors"
                            >
                              <ExternalLink size={12} /> 查看商品
                            </a>
                          )}
                          <button
                            onClick={() => handleFavorite(p)}
                            disabled={isFaved || isFaving}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold transition-all ${
                              isFaved
                                ? "bg-red-50 text-red-500 border border-red-100"
                                : "bg-gray-50 text-gray-500 border border-gray-100 hover:bg-red-50 hover:text-red-500 hover:border-red-100"
                            } disabled:opacity-50`}
                          >
                            {isFaving ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <Heart size={12} fill={isFaved ? "currentColor" : "none"} />
                            )}
                            {isFaved ? "已收藏" : "收藏"}
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          )}

          {displayMessages.map((msg, i) => (
            <div key={i} className={`max-w-3xl mx-auto flex gap-4 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              {msg.role !== 'user' && (
                <div className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${msg.role === 'agent' ? 'bg-indigo-50 text-indigo-500' : 'bg-gradient-to-tr from-indigo-500 to-sky-400 text-white'}`}>
                  {msg.role === 'agent' ? <Zap size={14} /> : <Zap size={14} fill="white" />}
                </div>
              )}
              <div className={`${msg.role === 'user' ? 'bg-black text-white px-5 py-3 rounded-2xl max-w-md' : 'space-y-1'}`}>
                {msg.agentName && (
                  <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">{msg.agentName}</p>
                )}
                {msg.role === 'agent' ? (
                  <p className="text-xs text-gray-400 italic">{msg.content}</p>
                ) : msg.role === 'assistant' ? (
                  <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap font-mono text-xs">{msg.content}</div>
                ) : (
                  <p className="text-sm">{msg.content}</p>
                )}
              </div>
            </div>
          ))}

          {/* Token-level streaming display */}
          {streamingText && (
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0">
                <Loader2 size={14} className="text-indigo-500 animate-spin" />
              </div>
              <div className="space-y-1">
                <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">streaming</p>
                <p className="text-xs text-gray-400 italic font-mono whitespace-pre-wrap">{streamingText}</p>
              </div>
            </div>
          )}

          {isStreaming && !streamingText && (
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="w-8 h-8 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0">
                <Loader2 size={14} className="text-indigo-500 animate-spin" />
              </div>
              <p className="text-xs text-gray-400 italic">EVA Agent 正在分析中...</p>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 底部输入框 */}
        <div className="p-8">
          <div className="max-w-3xl mx-auto relative group">
            <div className="absolute -inset-1 bg-gradient-to-r from-blue-100 to-indigo-100 rounded-[28px] blur-xl opacity-40 group-focus-within:opacity-100 transition-opacity" />
            <div className="relative bg-white border border-black/[0.08] rounded-[24px] shadow-2xl p-2 flex items-end gap-2">
              <textarea
                rows={1}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="在此输入您的购物指令..."
                className="flex-1 bg-transparent border-none outline-none py-4 px-4 text-sm resize-none"
              />
              <button
                onClick={() => handleSend()}
                disabled={isStreaming || !inputText.trim()}
                className="bg-black text-white p-4 rounded-[20px] hover:scale-105 active:scale-95 transition-all shadow-xl shadow-black/20 disabled:opacity-30"
              >
                <Send size={18} />
              </button>
            </div>
            <div className="mt-4 flex justify-center gap-6 text-[10px] font-bold text-gray-300 uppercase tracking-widest">
              <span>Smart Search</span>
              <span>Price Monitor</span>
              <span>Quality Audit</span>
            </div>
          </div>
        </div>
      </main>

      {/* 右侧情报面板 */}
      <aside className="w-[320px] border-l border-black/[0.04] bg-[#F9F9FB] overflow-y-auto hidden xl:block p-8">
        <div className="flex items-center justify-between mb-10">
          <h3 className="text-xs font-bold uppercase tracking-widest text-black">Live Intelligence</h3>
          <span className="px-2 py-0.5 rounded bg-black text-[9px] text-white">PRO</span>
        </div>

        <section className="space-y-6">
          <div className="group relative bg-white border border-black/[0.04] rounded-3xl p-4 shadow-sm hover:shadow-xl transition-all duration-500 overflow-hidden">
            <div className="absolute top-0 right-0 p-3">
              <ShieldCheck size={16} className="text-indigo-500" />
            </div>
            <div className="w-20 h-20 bg-gray-50 rounded-2xl mb-4" />
            <h4 className="font-bold text-sm mb-1">Agent 工作流</h4>
            <p className="text-xs text-gray-400 leading-relaxed">
              Intent → Search → Review → Analysis → Report
            </p>
          </div>

          <div className="p-4 bg-white rounded-3xl border border-black/[0.04] shadow-sm">
            <h4 className="font-bold text-xs mb-3 uppercase tracking-widest">MCP 工具状态</h4>
            {['search_products', 'compare_price', 'analyze_reviews', 'generate_report'].map((tool) => (
              <div key={tool} className="flex items-center justify-between py-2 text-xs text-gray-500">
                <span>{tool}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
              </div>
            ))}
          </div>

          {products.length > 0 && (
            <div className="p-4 bg-white rounded-3xl border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-widest">当前商品</h4>
              <div className="space-y-3">
                {products.map((p) => (
                  <div key={p.id} className="flex items-center justify-between">
                    <span className="text-[10px] text-gray-600 truncate max-w-[140px]">{p.name}</span>
                    <span className="text-[10px] font-bold text-black">¥{p.price}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}
