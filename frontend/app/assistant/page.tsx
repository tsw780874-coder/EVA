"use client"
import React, { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Plus, MessageSquare, LayoutGrid, Settings, Send,
  Layers, Zap, ShieldCheck, Globe2, Loader2,
  Heart, ExternalLink, Star, Menu, X,
  Database, Brain, Globe, Wrench, AlertTriangle,
  GitCompare, CheckSquare, Square
} from 'lucide-react';
import Link from 'next/link';
import { Great_Vibes } from 'next/font/google';
import { useChatStore, type SSEEvent, type ProductData, type HybridSourceInfo } from '@/stores/chatStore';
import { useAuthStore } from '@/stores/authStore';
import { api } from '@/lib/api';
import { MessageItem, type DisplayMessage } from '@/components/LoevenChat';

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

export default function ChatStudio() {
  const [inputText, setInputText] = useState("");
  const [displayMessages, setDisplayMessages] = useState<DisplayMessage[]>([]);
  const [favoritingId, setFavoritingId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState("");  // token-level streaming
  const [sidebarOpen, setSidebarOpen] = useState(false);    // mobile sidebar toggle
  const [favError, setFavError] = useState<string | null>(null);  // favorite error feedback
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());  // v10: 对比选择
  const [showCompare, setShowCompare] = useState(false);  // v10: 对比面板

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const user = useAuthStore((s) => s.user);
  const {
    sessions, currentSession,
    isStreaming, useHybrid, hybrid,
    loadSessions, createSession, sendMessage, toggleHybrid,
    selectSession, deleteSession,
    updateHybrid, resetHybrid,
    productsBySession, setProducts,
    favoritedIds, addFavoritedId,
  } = useChatStore();

  // Derive products from store (keyed by current session)
  const products = currentSession?.id ? (productsBySession[currentSession.id] || []) : [];

  useEffect(() => { loadSessions().catch(() => {}); }, []);
  useEffect(() => {
    setSidebarOpen(false);
  }, [currentSession?.id]);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayMessages, products, streamingText]);

  const handleFavorite = async (p: ProductData) => {
    setFavoritingId(p.id);
    setFavError(null);
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
      addFavoritedId(p.id);
    } catch (err: unknown) {
      const msg = (err as Error).message || "";
      if (msg.includes("409") || msg.includes("已收藏")) {
        addFavoritedId(p.id);
      } else if (msg.includes("认证已过期")) {
        setFavError("认证已过期，请刷新页面后重试");
      } else {
        setFavError(`收藏失败：${msg || "请检查网络连接后重试"}`);
      }
    }
    setFavoritingId(null);
  };

  const handleSelectSession = async (session: typeof sessions[0]) => {
    if (currentSession?.id === session.id) return;
    await selectSession(session.id);
    const state = useChatStore.getState();
    const msgs = state.messages;
    const displayMsgs: DisplayMessage[] = msgs.map((m) => ({
      role: m.role as DisplayMessage['role'],
      content: m.content,
    }));
    setDisplayMessages(displayMsgs);
    // Products are now per-session in store — they persist across session switches
    // No need to clear products; they're derived from productsBySession[currentSession.id]
    setStreamingText("");
    setFavError(null);
    resetHybrid();
  };

  const handleDeleteSession = async (sessionId: string) => {
    await deleteSession(sessionId);
    if (currentSession?.id === sessionId) {
      setDisplayMessages([]);
      setStreamingText("");
      setFavError(null);
      resetHybrid();
      // Products for this session will be garbage-collected by store
    }
  };

  const handleSend = async (query?: string) => {
    const content = query || inputText;
    if (!content.trim() || isStreaming) return;
    setInputText('');
    setDisplayMessages((prev) => [...prev, { role: 'user', content }]);
    setStreamingText("");
    setFavError(null);
    resetHybrid();

    // ChatGPT-style: 添加 streaming assistant 消息（带初始文案）
    setDisplayMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '正在多源分析您的需求...' },
    ]);

    let finalized = false;  // 防止 final_report 重复渲染

    // Token append helper — 直接不可变更新，每 token 触发一次 setState
    // React 18 自动批处理，不会造成性能问题
    const appendToken = (text: string) => {
      setDisplayMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== 'assistant') return prev;
        return [...prev.slice(0, -1), { ...last, content: (last.content || '') + text }];
      });
    };

    let sessionId = currentSession?.id;
    if (!sessionId) {
      try {
        const session = await createSession(content.slice(0, 30));
        sessionId = session.id;
      } catch (err) {
        // 创建会话失败 - 替换 streaming placeholder 为错误提示
        setDisplayMessages((prev) => {
          const clean = prev.filter(m => m.role !== 'assistant' || m.content !== '');
          return [...clean, { role: 'assistant', content: '⚠️ 无法创建对话会话，请检查网络连接后重试。' }];
        });
        console.error('[handleSend] createSession failed:', err);
        return;
      }
    }

    // ChatGPT-style: 每收到 token 直接追加到 displayMessages 最后一条
    try {
    await sendMessage(sessionId, content, (event: SSEEvent) => {
      // ── Token: 直接不可变追加到 displayMessages 最后一条 assistant ──
      if (event.type === 'token' && event.text) {
        appendToken(event.text);
      }

      // ── Products arrive → persist to store (keyed by session) ──
      if (event.type === 'agent_result' && event.products && !finalized) {
        setProducts(sessionId!, event.products);
      }

      // ── Final report → 替换最后一条消息的 content 为 markdown ──
      if (event.type === 'final_report' && !finalized) {
        finalized = true;
        setDisplayMessages((prev) => {
          const rest = prev.slice(0, -1);
          return [...rest, { role: 'assistant', content: event.markdown || '' }];
        });
        if (event.markdown?.includes('购物决策报告')) {
          updateHybrid({ confLevel: 'final' });
        }
      }

      // ── Error event → replace last message with error ──
      if (event.type === 'error' && !finalized) {
        finalized = true;
        setDisplayMessages((prev) => {
          const rest = prev.slice(0, -1);
          return [...rest, { role: 'assistant', content: `⚠️ 服务异常：${event.message || '未知错误'}，请稍后重试。` }];
        });
      }

      // ── Trust/perf → 静默更新 store（不触发 UI rerender）──
      if (event.type === 'trust') {
        updateHybrid({
          confidence: event.confidence || 0,
          hallucinationPassed: event.hallucination_passed ?? true,
        });
      }
      if (event.type === 'perf' && event.timing) {
        updateHybrid({ perfTiming: event.timing });
      }
    }, () => {
      finalized = false;
      loadSessions().catch(() => {});
    });
    } catch (err) {
      // sendMessage 自身失败 → 替换 streaming placeholder 为错误
      setDisplayMessages((prev) => {
        const clean = prev.filter(m => m.role !== 'assistant' || m.content !== '');
        return [...clean, { role: 'assistant', content: '⚠️ 消息发送失败，请检查网络连接后重试。' }];
      });
      console.error('[handleSend] sendMessage failed:', err);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const platformColor = (platform: string) => {
    const map: Record<string, string> = {
      "京东": "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
      "天猫": "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
      "淘宝": "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
      "得物": "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
      "拼多多": "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
    };
    return map[platform] || "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]";
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
            onClick={() => { setDisplayMessages([]); setFavError(null); createSession(); }}
            className="w-full py-2 px-4 border border-black/10 bg-white flex items-center justify-center gap-2 text-xs font-bold hover:bg-black hover:text-white transition-all"
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
            <div className="flex items-center gap-2 px-3 py-1 bg-[#F9F8F6] text-[10px] font-bold text-[#8C7A6B] border border-[#D4C9BC]">
              <span className="w-1.5 h-1.5 bg-[#8C7A6B]" />
              AGENT ACTIVE
            </div>
            {/* Hybrid toggle with earthy styling */}
            <button
              onClick={toggleHybrid}
              className={`flex items-center gap-1.5 px-2.5 py-1 text-[9px] font-bold border transition-all ${
                useHybrid
                  ? "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
                  : "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
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
                    web: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    rag: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    memory: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    tool: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    reasoning: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
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
              <div className="w-10 h-10 flex items-center justify-center shrink-0 border border-black/10 bg-[#F9F8F6] text-[#8C7A6B]">
                <span className="font-serif italic text-sm">E</span>
              </div>
              <div className="space-y-4">
                <h2 className="text-2xl md:text-3xl font-serif italic text-black">您好，我是 EVA。</h2>
                <p className="text-base md:text-lg text-[#3a3a3a] leading-[1.8] font-light">
                  我已连接多个主流电商平台。您可以发送商品链接或描述采购需求，我将为您进行深度比价和趋势分析。
                </p>
                <div className="grid grid-cols-1 gap-2 pt-4">
                  {SUGGESTED_QUERIES.map((q, i) => (
                    <button key={i} onClick={() => handleSend(q)} className="text-left px-5 py-3 border border-black/10 text-sm text-[#3a3a3a] hover:bg-black hover:text-white transition-all w-full md:w-fit">
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 收藏错误提示 */}
          {favError && (
            <div className="max-w-3xl mx-auto">
              <div className="bg-red-50 border border-red-200 p-3 flex items-center gap-2 text-xs text-red-700">
                <AlertTriangle size={14} />
                {favError}
                <button onClick={() => setFavError(null)} className="ml-auto text-red-400 hover:text-red-700">
                  <X size={14} />
                </button>
              </div>
            </div>
          )}

          {/* 商品卡片区 */}
          {products.length > 0 && (
            <div className="max-w-3xl mx-auto">
              <div className="flex items-center justify-between mb-4">
                <p className="text-[10px] font-bold text-[#8C7A6B] uppercase tracking-[0.2em]">
                  搜索到 {products.length} 个商品
                </p>
                {compareIds.size >= 2 && (
                  <button
                    onClick={() => setShowCompare(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold bg-black text-white hover:bg-neutral-800 transition-all"
                  >
                    <GitCompare size={12} />
                    对比已选 ({compareIds.size})
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 gap-4">
                {products.map((p) => {
                  const isFaved = favoritedIds.includes(p.id);
                  const isFaving = favoritingId === p.id;
                  return (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="bg-white border border-black/[0.06] p-4 md:p-5 flex items-start gap-4 hover:shadow-lg hover:border-black/[0.12] transition-all group"
                    >
                      <div className="w-16 h-16 bg-[#F9F8F6] shrink-0 flex items-center justify-center overflow-hidden">
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
                        <span className={`text-[10px] font-bold text-[#8C7A6B] ${p.image_url ? 'hidden' : ''}`}>
                          {p.platform.slice(0, 2)}
                        </span>
                      </div>

                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h4 className="font-bold text-sm leading-snug">{p.name}</h4>
                            <div className="flex items-center gap-2 mt-1.5">
                              <span className={`px-2 py-0.5 text-[9px] font-bold border ${platformColor(p.platform)}`}>
                                {p.platform}
                              </span>
                              {p.rating && (
                                <span className="text-[10px] text-[#8C7A6B]">⭐ {p.rating}</span>
                              )}
                              {p.review_count && (
                                <span className="text-[10px] text-[#8C7A6B]">{p.review_count} 评价</span>
                              )}
                            </div>
                          </div>
                          <div className="text-right shrink-0">
                            <p className="text-xl font-black tracking-tight text-black">
                              {p.price ? `¥${p.price.toLocaleString()}` : (p as any).price_display || '点击查看'}
                            </p>
                            {p.original_price && p.price && p.original_price > p.price && (
                              <p className="text-xs text-[#8C7A6B] line-through">
                                ¥{p.original_price?.toLocaleString()}
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-3 mt-3 pt-3 border-t border-black/[0.03] flex-wrap">
                          {p.url && (
                            <a
                              href={p.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center gap-1 text-[10px] font-bold text-[#8C7A6B] hover:text-black transition-colors"
                            >
                              <ExternalLink size={12} /> 查看商品
                            </a>
                          )}
                          <button
                            onClick={() => handleFavorite(p)}
                            disabled={isFaved || isFaving}
                            className={`flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-bold transition-all border ${
                              isFaved
                                ? "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
                                : "bg-[#F9F8F6] text-[#8C7A6B] border-black/5 hover:bg-black hover:text-white hover:border-black"
                            } disabled:opacity-50`}
                          >
                            {isFaving ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              <Heart size={12} fill={isFaved ? "currentColor" : "none"} />
                            )}
                            {isFaved ? "已收藏" : "收藏"}
                          </button>
                          {/* v10: 对比选择 */}
                          <button
                            onClick={() => {
                              setCompareIds(prev => {
                                const next = new Set(prev);
                                if (next.has(p.id)) next.delete(p.id);
                                else if (next.size < 4) next.add(p.id);
                                return next;
                              });
                            }}
                            className={`flex items-center gap-1 px-2 py-1 text-[10px] font-bold border transition-all ${
                              compareIds.has(p.id)
                                ? "bg-black text-white border-black"
                                : "bg-[#F9F8F6] text-[#8C7A6B] border-black/5 hover:border-black"
                            }`}
                          >
                            {compareIds.has(p.id) ? <CheckSquare size={12} /> : <Square size={12} />}
                            对比
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
            <MessageItem key={i} msg={msg} />
          ))}

          {/* Stream status — 流式进行中的状态指示器 */}
          {isStreaming && (
            <div className="max-w-4xl mx-auto flex gap-6">
              <div className="w-10 h-10 flex items-center justify-center shrink-0 border border-black/10 bg-[#F9F8F6] text-[#8C7A6B]">
                <Loader2 size={14} className="animate-spin" />
              </div>
              <div className="w-full pt-1">
                <p className="text-[10px] text-[#8C7A6B] uppercase tracking-[0.2em] flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-[#8C7A6B] animate-pulse" />
                  Agent 输出中...
                </p>
              </div>
            </div>
          )}

          {/* ── Hybrid AI v7 Metadata Bar ── */}
          {hybrid.sources.length > 0 && (
            <div className="max-w-3xl mx-auto space-y-2">
              {/* Conflict alerts */}
              {hybrid.conflicts.length > 0 && (
                <div className="bg-[#F9F8F6] border border-[#D4C9BC] p-3 flex items-start gap-3">
                  <AlertTriangle size={16} className="text-[#8C7A6B] shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-[#8C7A6B] uppercase tracking-[0.15em]">信息冲突</p>
                    {hybrid.conflicts.map((c, i) => (
                      <p key={i} className="text-xs text-[#3a3a3a]">{c}</p>
                    ))}
                  </div>
                </div>
              )}

              {!hybrid.hallucinationPassed && (
                <div className="bg-[#F9F8F6] border border-[#D4C9BC] p-3 flex items-start gap-3">
                  <ShieldCheck size={16} className="text-[#8C7A6B] shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-[10px] font-bold text-[#8C7A6B] uppercase tracking-[0.15em]">可信度警告</p>
                    {hybrid.warnings.map((w, i) => (
                      <p key={i} className="text-xs text-[#3a3a3a]">{w}</p>
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
                    web: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    rag: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    memory: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    tool: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                    reasoning: "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]",
                  };
                  return (
                    <span key={s.source} className={`px-2 py-0.5 rounded-full text-[9px] font-bold border flex items-center gap-1 ${colors[s.source] || colors.reasoning}`}>
                      {icons[s.source] || <Layers size={10} />}
                      {s.label}
                    </span>
                  );
                })}
                {hybrid.confidence > 0 && (
                  <span className={`px-2 py-0.5 text-[9px] font-bold border ${
                    hybrid.confidence >= 70
                      ? "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
                      : hybrid.confidence >= 40
                      ? "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
                      : "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
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
          <div className="max-w-3xl mx-auto relative">
            <div className="relative bg-white border border-black/10 p-2 flex items-end gap-2">
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
                className="bg-black text-white p-4 hover:bg-neutral-800 active:scale-95 transition-all disabled:opacity-30"
              >
                <Send size={18} />
              </button>
            </div>
            <div className="mt-4 flex justify-center gap-6 text-[10px] font-bold text-[#8C7A6B] uppercase tracking-[0.15em]">
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
          <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-black">EVA Intelligence</h3>
          <span className="px-2 py-0.5 border border-[#D4C9BC] bg-[#F9F8F6] text-[9px] text-[#8C7A6B]">V7</span>
        </div>

        <section className="space-y-6">
          <div className="group relative bg-white border border-black/[0.04] p-4 shadow-sm hover:shadow-lg transition-all duration-500 overflow-hidden">
            <div className="absolute top-0 right-0 p-3">
              <ShieldCheck size={16} className="text-[#8C7A6B]" />
            </div>
            {/* EVA Logo — refined styling */}
            <div className="relative w-20 h-20 mb-4 flex items-center justify-center">
              <div className="absolute inset-0 bg-[#F9F8F6] shadow-sm group-hover:shadow-md transition-all duration-500" />
              <div className="absolute top-0 left-0 right-0 h-1/2 bg-gradient-to-b from-white/50 to-transparent" />
              <span className={`${greatVibes.className} relative text-4xl text-[#8C7A6B] group-hover:scale-110 transition-transform duration-500`}>
                EV
              </span>
            </div>
            <h4 className="font-bold text-sm mb-1">EVA 工作流</h4>
            <p className="text-xs text-[#3a3a3a] leading-relaxed font-light">
              Source Select → RAG + Web + Tool → Resolve → Guard → Report
            </p>
          </div>

          {/* ── Hybrid Source Status ── */}
          {hybrid.sources.length > 0 && (
            <div className="p-4 bg-white border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-[0.15em]">信息源状态</h4>
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
                      <span className="w-1.5 h-1.5 bg-[#8C7A6B]" />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Confidence Breakdown ── */}
          {hybrid.confidence > 0 && (
            <div className="p-4 bg-white border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-[0.15em]">
                置信度评估
                <span className={`ml-2 px-1.5 py-0.5 text-[9px] border ${
                  hybrid.confidence >= 70
                    ? "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
                    : hybrid.confidence >= 40
                    ? "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
                    : "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
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
                            className={`h-full ${
                              val >= 30 ? "bg-[#8C7A6B]" : val >= 15 ? "bg-[#D4C9BC]" : "bg-[#D4C9BC]"
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
                <div className="mt-3 pt-3 border-t border-[#D4C9BC] flex items-center gap-2 text-[10px] text-[#8C7A6B]">
                  <AlertTriangle size={12} />
                  幻觉检查未通过
                </div>
              )}
            </div>
          )}

          {/* ── Perf timing ── */}
          {Object.keys(hybrid.perfTiming).length > 0 && (
            <div className="p-4 bg-white border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-[0.15em]">性能时序</h4>
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

          <div className="p-4 bg-white border border-black/[0.04] shadow-sm">
            <h4 className="font-bold text-xs mb-3 uppercase tracking-[0.15em]">多源工具状态</h4>
            {[
              { name: 'RAG 知识库', key: 'rag' },
              { name: 'Web 实时搜索', key: 'web' },
              { name: 'Memory 历史', key: 'memory' },
              { name: 'Tool 数据执行', key: 'tool' },
              { name: '反幻觉检查', key: 'guard' },
            ].map((tool) => (
              <div key={tool.key} className="flex items-center justify-between py-2 text-xs text-gray-500">
                <span>{tool.name}</span>
                <span className={`w-1.5 h-1.5 ${
                  hybrid.sources.some(s => s.source === tool.key) || (tool.key === 'guard' && hybrid.hallucinationPassed)
                    ? "bg-[#8C7A6B]"
                    : hybrid.sources.length > 0
                    ? "bg-[#D4C9BC]"
                    : "bg-[#8C7A6B]"
                }`} />
              </div>
            ))}
          </div>

          {products.length > 0 && (
            <div className="p-4 bg-white border border-black/[0.04] shadow-sm">
              <h4 className="font-bold text-xs mb-3 uppercase tracking-[0.15em]">当前商品</h4>
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

      {/* v10: 商品对比弹窗 */}
      {showCompare && compareIds.size >= 2 && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowCompare(false)}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-sm font-bold uppercase tracking-[0.2em]">
                商品对比 ({compareIds.size})
              </h3>
              <button onClick={() => { setShowCompare(false); setCompareIds(new Set()); }} className="p-1 hover:bg-black/5">
                <X size={18} />
              </button>
            </div>
            <div className={`grid gap-4 ${compareIds.size === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
              {products.filter(p => compareIds.has(p.id)).map(p => (
                <div key={p.id} className="border border-black/[0.06] p-4">
                  <div className="w-full aspect-square bg-[#F9F8F6] mb-3 flex items-center justify-center overflow-hidden">
                    {p.image_url ? (
                      <img src={p.image_url} alt={p.name} className="w-full h-full object-cover" />
                    ) : (
                      <span className="text-[10px] text-[#8C7A6B]">{p.platform}</span>
                    )}
                  </div>
                  <h4 className="font-bold text-xs leading-snug mb-2">{p.name}</h4>
                  <span className={`inline-block px-2 py-0.5 text-[9px] font-bold border mb-2 ${
                    p.platform === "京东" ? "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]" : "bg-[#F9F8F6] text-[#8C7A6B] border-[#D4C9BC]"
                  }`}>{p.platform}</span>
                  <p className="text-xl font-black tracking-tight">{p.price ? `¥${p.price.toLocaleString()}` : '--'}</p>
                  {p.original_price && p.price && p.original_price > p.price && (
                    <p className="text-xs text-[#8C7A6B] line-through">¥{p.original_price.toLocaleString()}</p>
                  )}
                  {p.rating && <p className="text-[10px] text-[#8C7A6B] mt-1">⭐ {p.rating}{p.review_count ? ` (${p.review_count}评)` : ''}</p>}
                  {p.url && (
                    <a href={p.url} target="_blank" rel="noopener noreferrer"
                       className="inline-block mt-3 text-[10px] font-bold text-[#8C7A6B] hover:text-black border-b border-[#D4C9BC]">
                      查看商品 →
                    </a>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
