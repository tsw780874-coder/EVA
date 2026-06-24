"use client"
import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Plus, MessageSquare, LayoutGrid, Settings, Send,
  Layers, Zap, ShieldCheck, Globe2, Loader2,
  Heart, ExternalLink, Star, Menu, X,
  Database, Brain, Globe, Wrench, AlertTriangle
} from 'lucide-react';
import Link from 'next/link';
import { Great_Vibes } from 'next/font/google';
import { useChatStore, type SSEEvent, type ProductData, type HybridSourceInfo } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { api } from '@/lib/api';

const greatVibes = Great_Vibes({
  weight: '400',
  subsets: ['latin'],
  display: 'swap',
});

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
  const [sidebarOpen, setSidebarOpen] = useState(false);    // mobile sidebar toggle

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const user = useAuthStore((s) => s.user);
  const {
    sessions, currentSession,
    isStreaming, useHybrid, hybrid,
    loadSessions, createSession, sendMessage, toggleHybrid,
    selectSession, deleteSession,
    updateHybrid, resetHybrid,
  } = useChatStore();

  useEffect(() => { loadSessions().catch(() => {}); }, []);
  useEffect(() => {
    setSidebarOpen(false);
  }, [currentSession?.id]);
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

  const handleSelectSession = async (session: typeof sessions[0]) => {
    if (currentSession?.id === session.id) return;
    await selectSession(session.id);
    const msgs = useChatStore.getState().messages;
    const displayMsgs: DisplayMessage[] = msgs.map((m) => ({
      role: m.role as DisplayMessage['role'],
      content: m.content,
    }));
    setDisplayMessages(displayMsgs);
    setProducts([]);
    setStreamingText("");
    resetHybrid();
  };

  const handleDeleteSession = async (sessionId: string) => {
    await deleteSession(sessionId);
    if (currentSession?.id === sessionId) {
      setDisplayMessages([]);
      setProducts([]);
      setStreamingText("");
      resetHybrid();
    }
  };

  const handleSend = async (query?: string) => {
    const content = query || inputText;
    if (!content.trim() || isStreaming) return;
    setInputText('');
    setDisplayMessages((prev) => [...prev, { role: 'user', content }]);
    setProducts([]);
    setStreamingText("");
    resetHybrid();

    // --- Instant thinking indicator (don't wait for SSE) ---
    setDisplayMessages((prev) => [
      ...prev,
      { role: 'agent', content: '正在多源分析您的需求...', agentName: 'think' },
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
        setDisplayMessages((prev) => {
          const filtered = prev.filter(m => !(m.role === 'agent' && m.agentName === 'think'));
          return [...filtered, { role: 'agent', content: event.message || '正在多源分析...', agentName: 'think' }];
        });
      }

      if (event.type === 'token') {
        tokenBuffer += (event.text || "");
        setStreamingText(tokenBuffer);
      }

      if (event.type === 'agent_result' && event.agent === 'search_agent' && event.products) {
        setProducts(event.products);
        setStreamingText("");
        tokenBuffer = "";
      }

      if (event.type === 'agent_progress') {
        setDisplayMessages((prev) => {
          const filtered = prev.filter(m =>
            !(m.role === 'agent' && (m.agentName === 'think' || m.agentName === 'streaming'))
          );
          return [...filtered, { role: 'agent', content: event.message || '', agentName: event.agent }];
        });
      }

      // ── Hybrid AI v7 events ──
      if (event.type === 'hybrid_sources' && event.sources) {
        updateHybrid({ sources: event.sources });
      }

      if (event.type === 'hybrid_confidence') {
        updateHybrid({
          confidence: event.confidence || 0,
          confLevel: event.level || "",
          confBreakdown: event.breakdown || {},
        });
      }

      if (event.type === 'hybrid_conflict' && event.conflicts) {
        updateHybrid({ conflicts: event.conflicts });
      }

      if (event.type === 'hybrid_guard') {
        updateHybrid({
          hallucinationPassed: event.passed ?? true,
          warnings: event.warnings || [],
        });
      }

      if (event.type === 'trust') {
        updateHybrid({
          confidence: event.confidence || 0,
          confLevel: event.level || "",
          conflicts: event.conflicts || [],
          hallucinationPassed: event.hallucination_passed ?? true,
        });
      }

      if (event.type === 'verification') {
        updateHybrid({
          verification: {
            passed: !!event.passed,
            action: (event.action as string) || "allow",
            confidence: (event.confidence as number) || 0,
            failedChecks: (event.failed_checks as string[]) || [],
            warnings: (event.warnings as string[]) || [],
          },
        });
      }

      if (event.type === 'perf' && event.timing) {
        updateHybrid({ perfTiming: event.timing });
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

      {/* 移动端侧边栏遮罩 */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* 左侧边栏 — 移动端fixed抽屉 / 桌面端static */}
      <aside className={`
        w-64 border-r border-black/[0.04] bg-[#F9F9FB] flex flex-col shrink-0
        max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-50
        max-lg:transition-transform max-lg:duration-300 max-lg:ease-out
        ${sidebarOpen ? 'max-lg:translate-x-0' : 'max-lg:-translate-x-full'}
      `}>
        {/* 移动端关闭按钮 */}
        <div className="lg:hidden p-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3" onClick={() => setSidebarOpen(false)}>
            <div className="w-8 h-8 bg-black rounded-lg flex items-center justify-center text-white font-black">E</div>
            <span className="font-bold tracking-widest text-sm uppercase">EVA Assistant</span>
          </Link>
          <button onClick={() => setSidebarOpen(false)} className="p-2 hover:bg-black/5 rounded-lg">
            <X size={18} />
          </button>
        </div>

        {/* 桌面端 Logo（移动端已在上方显示） */}
        <Link href="/" className="p-6 hidden lg:flex items-center gap-3 hover:opacity-60 transition-opacity">
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
          {sessions.slice(0, 10).map((s) => {
            const isActive = currentSession?.id === s.id;
            return (
              <div
                key={s.id}
                onClick={() => handleSelectSession(s)}
                className={`flex items-center gap-3 px-4 py-2 text-sm rounded-xl cursor-pointer transition-all group ${
                  isActive
                    ? 'bg-black text-white shadow-sm'
                    : 'text-gray-500 hover:bg-white hover:text-black'
                }`}
              >
                <MessageSquare size={14} className={isActive ? 'opacity-100' : 'opacity-50 group-hover:opacity-100'} />
                <span className="truncate flex-1">{s.title}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(s.id);
                  }}
                  className="ml-auto p-0.5 rounded opacity-0 group-hover:opacity-100 hover:text-red-500 hover:bg-red-50 transition-all"
                  title="删除对话"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
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
        <header className="h-16 border-b border-black/[0.02] flex items-center justify-between px-4 md:px-8 bg-white/80 backdrop-blur-md z-10">
          <div className="flex items-center gap-4">
            {/* 移动端汉堡菜单 */}
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 -ml-2 hover:bg-black/5 rounded-lg"
            >
              <Menu size={20} />
            </button>
            {user && (
              <span className="text-xs text-gray-400">👋 {user.name}</span>
            )}
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-green-50 text-[10px] font-bold text-green-600 border border-green-100">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              AGENT ACTIVE
            </div>
            {/* Hybrid v7 toggle */}
            <button
              onClick={toggleHybrid}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-bold border transition-all ${
                useHybrid
                  ? "bg-indigo-50 text-indigo-600 border-indigo-100"
                  : "bg-gray-50 text-gray-400 border-gray-100"
              }`}
              title={useHybrid ? "Hybrid V7: 多源智能已启用" : "使用经典 V6 模式"}
            >
              <Brain size={10} />
              {useHybrid ? "HYBRID ON" : "V6"}
            </button>
          </div>
          <div className="flex items-center gap-4 text-gray-400">
            {hybrid.sources.length > 0 && (
              <div className="flex items-center gap-1.5">
                {hybrid.sources.map((s) => {
                  const icons: Record<string, React.ReactNode> = {
                    web: <Globe size={10} />,
                    rag: <Database size={10} />,
                    memory: <Brain size={10} />,
                    tool: <Wrench size={10} />,
                    reasoning: <Layers size={10} />,
                  };
                  const colors: Record<string, string> = {
                    web: "bg-blue-50 text-blue-600 border-blue-100",
                    rag: "bg-purple-50 text-purple-600 border-purple-100",
                    memory: "bg-amber-50 text-amber-600 border-amber-100",
                    tool: "bg-emerald-50 text-emerald-600 border-emerald-100",
                    reasoning: "bg-gray-50 text-gray-500 border-gray-100",
                  };
                  return (
                    <span key={s.source} className={`px-1.5 py-0.5 rounded text-[9px] font-bold border flex items-center gap-0.5 ${colors[s.source] || colors.reasoning}`}>
                      {icons[s.source] || <Layers size={10} />}
                      {s.source.toUpperCase()}
                    </span>
                  );
                })}
              </div>
            )}
            <Globe2 size={18} />
            <Layers size={18} />
          </div>
        </header>

        {/* 消息滚动区 */}
        <div className="flex-1 overflow-y-auto px-4 md:px-8 py-8 md:py-12 space-y-8 md:space-y-10">
          {displayMessages.length === 0 && (
            <div className="max-w-3xl mx-auto flex gap-6">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-indigo-500 to-sky-400 flex items-center justify-center text-white shrink-0 shadow-lg shadow-indigo-100">
                <Zap size={20} fill="white" />
              </div>
              <div className="space-y-4">
                <h2 className="text-2xl md:text-3xl font-serif italic text-black">您好，我是 EVA。</h2>
                <p className="text-base md:text-lg text-gray-500 leading-relaxed">
                  我已连接多个主流电商平台。您可以发送商品链接或描述采购需求，我将为您进行深度比价和趋势分析。
                </p>
                <div className="grid grid-cols-1 gap-2 pt-4">
                  {SUGGESTED_QUERIES.map((q, i) => (
                    <button key={i} onClick={() => handleSend(q)} className="text-left px-5 py-3 rounded-2xl border border-black/[0.04] text-sm text-gray-600 hover:bg-black hover:text-white transition-all w-full md:w-fit">
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
                  const hasUrl = p.url && p.url.length > 0;
                  const hasImage = p.image_url && p.image_url.length > 0;
                  const hasPrice = p.price && p.price > 0;

                  const CardContent = (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={`bg-white border border-black/[0.06] rounded-2xl p-4 md:p-5 flex items-start gap-4 hover:shadow-lg hover:border-black/[0.12] transition-all group ${hasUrl ? 'cursor-pointer' : ''}`}
                    >
                      {/* 商品图片 — 真实图片 or 平台徽章回退 */}
                      <div className="w-16 h-16 md:w-20 md:h-20 rounded-xl bg-gray-50 shrink-0 flex items-center justify-center overflow-hidden relative">
                        {hasImage ? (
                          <img
                            src={p.image_url}
                            alt={p.name}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              const el = e.target as HTMLImageElement;
                              el.style.display = 'none';
                              const fallback = el.parentElement?.querySelector('.img-fallback');
                              if (fallback) fallback.classList.remove('hidden');
                            }}
                          />
                        ) : null}
                        <div className={`img-fallback w-full h-full flex flex-col items-center justify-center gap-1 ${hasImage ? 'hidden' : ''}`}>
                          <span className={`text-xs font-bold ${platformColor(p.platform).split(' ')[1] || 'text-gray-500'}`}>
                            {p.platform}
                          </span>
                          {p.rating && (
                            <span className="text-[9px] text-gray-400">⭐{p.rating}</span>
                          )}
                        </div>
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h4 className="font-bold text-sm leading-snug line-clamp-2">{p.name}</h4>
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
                            {hasPrice ? (
                              <>
                                <p className="text-xl font-black tracking-tight text-black">
                                  ¥{p.price?.toLocaleString()}
                                </p>
                                {p.original_price && p.original_price > (p.price || 0) && (
                                  <p className="text-xs text-gray-400 line-through">
                                    ¥{p.original_price?.toLocaleString()}
                                  </p>
                                )}
                              </>
                            ) : (
                              <p className="text-sm font-bold text-gray-400">查看最新价</p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-black/[0.03]">
                          {hasUrl && (
                            <span className="flex items-center gap-1 text-[10px] font-bold text-indigo-500 group-hover:text-indigo-700 transition-colors">
                              <ExternalLink size={12} /> 点击卡片查看详情
                            </span>
                          )}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              e.preventDefault();
                              handleFavorite(p);
                            }}
                            disabled={isFaved || isFaving}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold transition-all ml-auto ${
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

                  // 包装为可点击链接（仅当有 URL 时）
                  if (hasUrl) {
                    return (
                      <a
                        key={p.id}
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block"
                        title={`在 ${p.platform} 查看 ${p.name}`}
                      >
                        {CardContent}
                      </a>
                    );
                  }
                  return CardContent;
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
              <div className={`${msg.role === 'user' ? 'bg-black text-white px-5 py-3 rounded-2xl max-w-[85%] md:max-w-md' : 'space-y-1'}`}>
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
              <p className="text-xs text-gray-400 italic">EVA 正在多源分析中...</p>
            </div>
          )}

          {/* ── Hybrid AI v7 Metadata Bar ── */}
          {hybrid.sources.length > 0 && (
            <div className="max-w-3xl mx-auto space-y-2">
              {/* Conflict alerts */}
              {hybrid.conflicts.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-3">
                  <AlertTriangle size={16} className="text-amber-500 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-amber-700 uppercase tracking-widest">信息冲突</p>
                    {hybrid.conflicts.map((c, i) => (
                      <p key={i} className="text-xs text-amber-600">{c}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* Hallucination guard warnings */}
              {!hybrid.hallucinationPassed && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-3 flex items-start gap-3">
                  <ShieldCheck size={16} className="text-red-500 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-red-700 uppercase tracking-widest">可信度警告</p>
                    {hybrid.warnings.map((w, i) => (
                      <p key={i} className="text-xs text-red-600">{w}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* Source + Confidence compact bar */}
              <div className="flex items-center gap-3 flex-wrap">
                {hybrid.sources.map((s) => {
                  const icons: Record<string, React.ReactNode> = {
                    web: <Globe size={10} />,
                    rag: <Database size={10} />,
                    memory: <Brain size={10} />,
                    tool: <Wrench size={10} />,
                    reasoning: <Layers size={10} />,
                  };
                  const colors: Record<string, string> = {
                    web: "bg-blue-50 text-blue-600 border-blue-100",
                    rag: "bg-purple-50 text-purple-600 border-purple-100",
                    memory: "bg-amber-50 text-amber-600 border-amber-100",
                    tool: "bg-emerald-50 text-emerald-600 border-emerald-100",
                    reasoning: "bg-gray-50 text-gray-500 border-gray-100",
                  };
                  return (
                    <span key={s.source} className={`px-2 py-0.5 rounded-full text-[9px] font-bold border flex items-center gap-1 ${colors[s.source] || colors.reasoning}`}>
                      {icons[s.source] || <Layers size={10} />}
                      {s.label}
                    </span>
                  );
                })}
                {hybrid.confidence > 0 && (
                  <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold border ${
                    hybrid.confidence >= 70
                      ? "bg-green-50 text-green-600 border-green-100"
                      : hybrid.confidence >= 40
                      ? "bg-amber-50 text-amber-600 border-amber-100"
                      : "bg-red-50 text-red-600 border-red-100"
                  }`}>
                    置信度 {hybrid.confidence.toFixed(0)}% {hybrid.confLevel && `(${hybrid.confLevel})`}
                  </span>
                )}
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 底部输入框 */}
        <div className="p-4 md:p-8">
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
          <h3 className="text-xs font-bold uppercase tracking-widest text-black">EVA Intelligence</h3>
          <span className="px-2 py-0.5 rounded bg-gradient-to-r from-indigo-500 to-purple-600 text-[9px] text-white">V7</span>
        </div>

        <section className="space-y-6">
          <div className="group relative bg-white border border-black/[0.04] rounded-3xl p-4 shadow-sm hover:shadow-xl transition-all duration-500 overflow-hidden">
            <div className="absolute top-0 right-0 p-3">
              <ShieldCheck size={16} className="text-indigo-500" />
            </div>
            {/* EVA Logo — Great Vibes */}
            <div className="relative w-20 h-20 mb-4 flex items-center justify-center">
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-indigo-500/20 via-purple-500/10 to-sky-400/20 blur-md group-hover:blur-xl group-hover:scale-150 transition-all duration-700" />
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-700 shadow-lg shadow-indigo-200 group-hover:shadow-indigo-300 group-hover:shadow-xl transition-all duration-500" />
              <div className="absolute top-0 left-0 right-0 h-1/2 rounded-t-2xl bg-gradient-to-b from-white/25 to-transparent" />
              <span className={`${greatVibes.className} relative text-4xl text-white drop-shadow-[0_2px_4px_rgba(0,0,0,0.3)] group-hover:scale-110 transition-transform duration-500`}>
                EV
              </span>
            </div>
            <h4 className="font-bold text-sm mb-1">EVA 工作流</h4>
            <p className="text-xs text-gray-400 leading-relaxed">
              Source Select → RAG + Web + Tool → Resolve → Guard → Report
            </p>
          </div>

          {/* ── Hybrid Source Status ── */}
          {hybrid.sources.length > 0 && (
            <div className="p-4 bg-white rounded-3xl border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-widest">信息源状态</h4>
              <div className="space-y-2">
                {hybrid.sources.map((s) => {
                  const icons: Record<string, React.ReactNode> = {
                    web: <Globe size={12} />,
                    rag: <Database size={12} />,
                    memory: <Brain size={12} />,
                    tool: <Wrench size={12} />,
                    reasoning: <Layers size={12} />,
                  };
                  return (
                    <div key={s.source} className="flex items-center justify-between py-1.5 text-xs text-gray-500">
                      <span className="flex items-center gap-2">
                        {icons[s.source] || <Layers size={12} />}
                        {s.label}
                      </span>
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Confidence Breakdown ── */}
          {hybrid.confidence > 0 && (
            <div className="p-4 bg-white rounded-3xl border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-widest">
                置信度评估
                <span className={`ml-2 px-1.5 py-0.5 rounded text-[9px] ${
                  hybrid.confidence >= 70
                    ? "bg-green-50 text-green-600"
                    : hybrid.confidence >= 40
                    ? "bg-amber-50 text-amber-600"
                    : "bg-red-50 text-red-600"
                }`}>
                  {hybrid.confidence.toFixed(0)}%
                </span>
              </h4>
              {hybrid.confBreakdown && Object.keys(hybrid.confBreakdown).length > 0 && (
                <div className="space-y-1.5">
                  {Object.entries(hybrid.confBreakdown).map(([key, val]) => (
                    <div key={key} className="flex items-center justify-between text-[10px]">
                      <span className="text-gray-400">{
                        key === "sources_score" ? "来源数量" :
                        key === "freshness_score" ? "数据新鲜度" :
                        key === "relevance_score" ? "相关性" :
                        key === "authority_score" ? "权威度" : key
                      }</span>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              val >= 30 ? "bg-green-400" : val >= 15 ? "bg-amber-400" : "bg-red-400"
                            }`}
                            style={{ width: `${Math.min(val, 100)}%` }}
                          />
                        </div>
                        <span className="text-gray-500 w-6 text-right">{val.toFixed(0)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {!hybrid.hallucinationPassed && (
                <div className="mt-3 pt-3 border-t border-red-100 flex items-center gap-2 text-[10px] text-red-500">
                  <AlertTriangle size={12} />
                  幻觉检查未通过
                </div>
              )}
            </div>
          )}

          {/* ── Perf timing ── */}
          {Object.keys(hybrid.perfTiming).length > 0 && (
            <div className="p-4 bg-white rounded-3xl border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-widest">性能时序</h4>
              <div className="space-y-1">
                {Object.entries(hybrid.perfTiming).slice(0, 8).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between text-[10px]">
                    <span className="text-gray-400">{key}</span>
                    <span className="text-gray-600 font-mono">
                      {typeof val === 'number' ? `${val.toFixed(0)}ms` : String(val)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="p-4 bg-white rounded-3xl border border-black/[0.04] shadow-sm">
            <h4 className="font-bold text-xs mb-3 uppercase tracking-widest">多源工具状态</h4>
            {[
              { name: 'RAG 知识库', key: 'rag' },
              { name: 'Web 实时搜索', key: 'web' },
              { name: 'Memory 历史', key: 'memory' },
              { name: 'Tool 数据执行', key: 'tool' },
              { name: '反幻觉检查', key: 'guard' },
            ].map((tool) => (
              <div key={tool.key} className="flex items-center justify-between py-2 text-xs text-gray-500">
                <span>{tool.name}</span>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  hybrid.sources.some(s => s.source === tool.key) || (tool.key === 'guard' && hybrid.hallucinationPassed)
                    ? "bg-green-400"
                    : hybrid.sources.length > 0
                    ? "bg-gray-300"
                    : "bg-green-400"
                }`} />
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
