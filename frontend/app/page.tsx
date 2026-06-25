"use client"
import React, { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowRight, Star, User, FileBarChart, Settings, ShoppingBag, LogOut, Menu, X } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';

export default function FashionHome() {
  const router = useRouter();
  const { isAuthenticated, logout } = useAuthStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastTimeRef = useRef<number>(0);
  const fadeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;

    // 启动播放
    el.play().catch(() => {});

    // 无缝循环：在视频即将结束时快速淡出淡入，掩盖循环跳帧
    const handleTimeUpdate = () => {
      const timeToEnd = el.duration - el.currentTime;

      // 检测循环跳转（currentTime 从接近末尾跳回开头）
      if (el.currentTime < lastTimeRef.current && lastTimeRef.current > 0.1) {
        // 快速闪白掩盖跳帧
        el.style.transition = 'opacity 0.06s ease-out';
        el.style.opacity = '0.7';
        if (fadeTimeoutRef.current) clearTimeout(fadeTimeoutRef.current);
        fadeTimeoutRef.current = setTimeout(() => {
          el.style.transition = 'opacity 0.15s ease-in';
          el.style.opacity = '1';
        }, 30);
      }
      lastTimeRef.current = el.currentTime;

      // 结尾前预淡出（只在非常接近结尾时触发）
      if (timeToEnd < 0.12 && timeToEnd > 0) {
        el.style.transition = 'opacity 0.08s ease-out';
        el.style.opacity = '0.85';
      }
    };

    el.addEventListener('timeupdate', handleTimeUpdate);
    el.style.transition = 'opacity 0.15s ease';
    el.style.opacity = '1';

    return () => {
      el.removeEventListener('timeupdate', handleTimeUpdate);
      if (fadeTimeoutRef.current) clearTimeout(fadeTimeoutRef.current);
    };
  }, []);

  const handleCTAClick = () => {
    if (isAuthenticated) {
      router.push('/assistant');
    } else {
      router.push('/login');
    }
  };

  return (
    <div className="bg-[#FFFFFF] text-[#1d1d1f] font-sans selection:bg-indigo-50" suppressHydrationWarning>

      {/* ── 全局背景光 ── */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] right-[-10%] w-[60%] h-[60%] bg-[#F3E8FF] blur-[150px] opacity-40 rounded-full" />
        <div className="absolute bottom-[10%] left-[-5%] w-[50%] h-[50%] bg-[#E0F2FE] blur-[130px] opacity-30 rounded-full" />
        <div className="absolute top-[40%] left-[30%] w-[30%] h-[40%] bg-[#FFF7ED] blur-[120px] opacity-50 rounded-full" />
      </div>

      {/* ── HERO ── */}
      <section className="relative min-h-dvh w-full overflow-hidden bg-black">

        {/* 背景：PC 视频 / 移动端静态图 */}
        <div className="absolute inset-0 z-0 h-full w-full overflow-hidden pointer-events-none">
          <video
            ref={videoRef}
            autoPlay loop muted playsInline
            controls={false}
            preload="auto"
            className="hero-video-mobile-hidden hero-video-seamless hidden md:block absolute w-full h-full object-cover transform-gpu translate-z-0 pointer-events-none select-none"
            src="/SuperCar.mp4"
          />
          <img
            src="/SuperCar.png"
            alt="EVA Hero"
            fetchPriority="high"
            loading="eager"
            decoding="sync"
            className="hero-img-mobile-visible block md:hidden absolute inset-0 w-full h-full object-cover pointer-events-none select-none"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-white/10 via-transparent to-transparent pointer-events-none" />
          <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-white via-white/40 to-transparent pointer-events-none" />
        </div>

        {/* 导航 + 文字 */}
        <div className="relative z-10 h-full flex flex-col">

          <nav className="w-full border-b border-black/[0.04] bg-white/60 md:bg-white/10 md:backdrop-blur-md px-4 md:px-8 lg:px-12 py-4 md:py-5 flex justify-between items-center shrink-0 pointer-events-auto">
            <div className="flex items-center gap-4 md:gap-10">
              <Link href="/" className="group cursor-pointer flex items-center gap-2 md:gap-2.5 no-underline">
                <div className="w-6 h-6 md:w-7 md:h-7 bg-black rounded-full flex items-center justify-center shadow-sm">
                  <span className="text-white text-[10px] md:text-[11px] font-black italic tracking-tighter">E</span>
                </div>
                <span className="text-sm md:text-base font-bold tracking-[0.25em] md:tracking-[0.35em] text-black">EVA</span>
              </Link>
              {/* 桌面端导航链接 — 使用 Link 实现客户端路由 */}
              <div className="hidden md:flex gap-4 lg:gap-8 text-[10px] md:text-[11px] font-bold tracking-[0.15em] md:tracking-[0.2em] text-gray-500">
                <Link href="/assistant" className="hover:text-black transition-colors flex items-center gap-1.5 md:gap-2 no-underline text-gray-500">
                  <ShoppingBag size={12} className="stroke-[2.5]" /> <span className="hidden lg:inline">AI 购物助手</span><span className="lg:hidden">购物</span>
                </Link>
                <Link href="/favorites" className="hover:text-black transition-colors flex items-center gap-1.5 md:gap-2 no-underline text-gray-500">
                  <Star size={12} className="stroke-[2.5]" /> <span className="hidden lg:inline">收藏夹</span><span className="lg:hidden">收藏</span>
                </Link>
                <Link href="/reports" className="hover:text-black transition-colors flex items-center gap-1.5 md:gap-2 no-underline text-gray-500">
                  <FileBarChart size={12} className="stroke-[2.5]" /> <span className="hidden lg:inline">购物报告</span><span className="lg:hidden">报告</span>
                </Link>
              </div>
            </div>

            {/* 桌面端右侧操作区 — mounted 确保 SSR/客户端首次渲染一致 */}
            <div className="hidden md:flex items-center gap-3 md:gap-6 text-[10px] md:text-[11px] font-bold tracking-[0.1em] md:tracking-[0.15em]">
              {isAuthenticated ? (
                <div className="flex items-center gap-3 md:gap-6">
                  <Link href="/profile" className="flex items-center gap-1 md:gap-2 hover:text-black text-gray-600 transition-colors no-underline">
                    <User size={13} /> <span className="hidden sm:inline">个人中心</span>
                  </Link>
                  <Link href="/settings" className="p-1.5 md:p-2 border border-black/10 rounded-full hover:bg-black hover:text-white transition-all no-underline text-gray-600">
                    <Settings size={12} />
                  </Link>
                  <button onClick={() => { logout(); router.push('/'); }} className="flex items-center gap-1 text-gray-400 hover:text-red-500 transition-colors">
                    <LogOut size={12} /> <span className="hidden sm:inline">退出</span>
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-3 md:gap-6">
                  <Link href="/login" className="text-gray-600 hover:text-black transition-colors text-xs md:text-sm no-underline">登录</Link>
                  <Link href="/register" className="bg-black text-white px-4 md:px-6 py-2 md:py-2.5 rounded-full text-xs md:text-sm hover:bg-neutral-800 shadow-md hover:shadow-lg transition-all duration-300 whitespace-nowrap no-underline">注册</Link>
                </div>
              )}
            </div>

            {/* 移动端汉堡菜单按钮 */}
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="md:hidden p-2 -mr-2 text-black hover:opacity-70 transition-opacity"
              aria-label="打开菜单"
            >
              <Menu size={22} strokeWidth={2} />
            </button>
          </nav>

          {/* 移动端侧滑菜单 */}
          {mobileMenuOpen && (
            <div className="fixed inset-0 z-50 md:hidden">
              <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setMobileMenuOpen(false)} />
              <div className="absolute right-0 top-0 bottom-0 w-72 bg-white shadow-2xl flex flex-col p-6 animate-slide-in-right">
                <div className="flex justify-between items-center mb-10">
                  <span className="text-sm font-bold tracking-[0.3em] text-black">EVA</span>
                  <button onClick={() => setMobileMenuOpen(false)} className="p-1 hover:bg-gray-100 rounded-full transition-colors">
                    <X size={20} />
                  </button>
                </div>

                <nav className="flex flex-col gap-6 text-sm font-bold tracking-[0.15em]">
                  <Link href="/assistant" onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-3 text-gray-700 hover:text-black transition-colors no-underline py-2">
                    <ShoppingBag size={18} strokeWidth={2} /> AI 购物助手
                  </Link>
                  <Link href="/favorites" onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-3 text-gray-700 hover:text-black transition-colors no-underline py-2">
                    <Star size={18} strokeWidth={2} /> 收藏夹
                  </Link>
                  <Link href="/reports" onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-3 text-gray-700 hover:text-black transition-colors no-underline py-2">
                    <FileBarChart size={18} strokeWidth={2} /> 购物报告
                  </Link>
                </nav>

                <div className="mt-auto pt-8 border-t border-gray-100">
                  {isAuthenticated ? (
                    <div className="flex flex-col gap-4">
                      <Link href="/profile" onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-3 text-gray-700 hover:text-black transition-colors no-underline py-2 text-sm font-bold tracking-[0.15em]">
                        <User size={18} strokeWidth={2} /> 个人中心
                      </Link>
                      <Link href="/settings" onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-3 text-gray-700 hover:text-black transition-colors no-underline py-2 text-sm font-bold tracking-[0.15em]">
                        <Settings size={18} strokeWidth={2} /> 设置
                      </Link>
                      <button onClick={() => { logout(); router.push('/'); setMobileMenuOpen(false); }} className="flex items-center gap-3 text-red-500 hover:text-red-600 transition-colors py-2 text-sm font-bold tracking-[0.15em]">
                        <LogOut size={18} strokeWidth={2} /> 退出登录
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-4">
                      <Link href="/login" onClick={() => setMobileMenuOpen(false)} className="block text-center py-3 border border-black/10 rounded-full text-sm font-bold tracking-[0.2em] text-gray-700 hover:bg-gray-50 transition-colors no-underline">
                        登录
                      </Link>
                      <Link href="/register" onClick={() => setMobileMenuOpen(false)} className="block text-center py-3 bg-black text-white rounded-full text-sm font-bold tracking-[0.2em] hover:bg-neutral-800 transition-colors no-underline">
                        注册
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Hero 文字 */}
          <div className="flex-1 flex flex-col items-center justify-center px-6 text-center select-none mt-[-40px] relative">
            <div className="absolute w-[85vw] md:w-[55vw] h-[35vh] bg-white/40 blur-[90px] rounded-full pointer-events-none" />
            <p className="text-[11px] md:text-[12px] font-bold tracking-[0.5em] text-indigo-700/90 uppercase mb-7 relative z-10">
              Forever passionate, romantic until the very end
            </p>
            <h1 className="text-[13vw] lg:text-[9vw] leading-[0.85] tracking-tight text-black flex flex-wrap justify-center items-baseline gap-x-[2vw] relative z-10">
              <span className="font-serif italic font-normal text-neutral-900 drop-shadow-md">EVA</span>
              <span className="font-sans not-italic font-black text-black drop-shadow-md">SYSTEM</span>
            </h1>
            <div className="mt-16 flex flex-col items-center relative z-10">
              <div className="h-16 w-[1.5px] bg-gradient-to-b from-black via-black/40 to-transparent relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-transparent to-white animate-scroll-glow" />
              </div>
              <p className="mt-5 text-[9px] font-extrabold tracking-[0.35em] uppercase text-black/60 drop-shadow-sm">
                Scroll to Explore
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Section 2: Platform Introduction ── */}
      <section className="relative z-10 py-20 md:py-40 px-6 md:px-12 lg:px-40 grid grid-cols-1 lg:grid-cols-12 gap-10 bg-white">
        <div className="lg:col-span-7">
          <h2 className="text-3xl md:text-5xl lg:text-7xl font-serif italic mb-6 md:mb-10 leading-tight">
            Built with intelligence, <br />
            <span className="font-sans not-italic font-black">driven by imagination.</span>
          </h2>
          <div className="max-w-xl space-y-8">
            <p className="text-base md:text-xl text-gray-500 leading-relaxed">
              EVA（Enterprise Virtual Assistant）是一款企业级 AI Agent 智能体平台。我们不仅是在构建工具，而是在定义一种全新的 <span className="text-black font-medium">AI 协作范式</span>。
            </p>
            <p className="text-sm text-gray-400 leading-loose">
              作为一个集大模型接入、多 Agent 协作、Workflow 自动化编排、MCP 工具生态、以及长期记忆管理于一体的 AI 应用开发平台，EVA 旨在打破人机边界。
            </p>
          </div>
        </div>
        <div className="lg:col-span-5 flex flex-col">
          <div className="aspect-[3/4] bg-gray-50 border border-black/[0.03] rounded-[40px] overflow-hidden relative group hover:scale-[1.02] transition-transform duration-500">
            <div className="absolute inset-0 bg-gradient-to-tr from-indigo-50 to-transparent opacity-60 z-10" />
            <img src="/butterfly.jpg" alt="Butterfly" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 p-12 flex flex-col justify-between z-20">
              <span className="text-[10px] font-black uppercase tracking-widest text-white">EVA</span>
              <h3 className="text-3xl font-serif italic text-white drop-shadow-md">支持统一接入多个主流大模型 API</h3>
            </div>
          </div>
        </div>
      </section>

      {/* ── Section 3: AI Shopping Engine ── */}
      <section className="relative z-10 py-20 md:py-40 bg-[#F5F5F7]/50 px-6 md:px-12 lg:px-40">
        <div className="mb-20 text-center">
          <h2 className="text-sm font-black tracking-[0.4em] uppercase mb-4">AI 商品比价引擎</h2>
          <p className="text-2xl md:text-4xl lg:text-6xl font-serif italic">Because of you, EVA can embrace the world.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { title: "多平台搜索", desc: "京东，淘宝，拼多多，天猫...", icon: "01" },
            { title: "价格聚合", desc: "全网实时报价一目了然", icon: "02" },
            { title: "优惠信息", desc: "精准捕捉隐藏神券与补贴", icon: "03" },
          ].map((item, i) => (
            <div key={i} className="bg-white p-12 rounded-[30px] shadow-sm border border-black/[0.02] hover:-translate-y-2 transition-transform duration-300">
              <span className="text-4xl font-serif italic text-indigo-100 block mb-6">{item.icon}</span>
              <h4 className="text-xl font-bold mb-4">{item.title}</h4>
              <p className="text-gray-400 text-sm leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Section 4: Reports ── */}
      <section className="relative z-10 py-20 md:py-40 lg:py-60 px-6 md:px-12 lg:px-40">
        <div className="absolute top-0 right-10 text-[20vw] font-black text-black/[0.02] select-none">REPORTS</div>
        <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 items-center gap-12 md:gap-24">
          <div>
            <h2 className="text-3xl md:text-5xl font-serif italic mb-6 md:mb-8">EVA，浪漫热忱，至死不渝</h2>
            <div className="space-y-6">
              {['商品分析报告', '性价比报告', '购买决策报告'].map((text) => (
                <div key={text} className="flex items-center gap-4 group cursor-pointer border-b border-black/[0.05] pb-4">
                  <div className="w-2 h-2 bg-indigo-400 rounded-full scale-0 group-hover:scale-100 transition-transform" />
                  <span className="text-lg text-gray-500 group-hover:text-black transition-colors">{text}</span>
                  <ArrowRight className="ml-auto opacity-0 group-hover:opacity-100 transition-all" size={16} />
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-[40px] shadow-2xl shadow-indigo-100/50 border border-white/20 overflow-hidden relative aspect-[4/3] hover:scale-[1.02] transition-transform duration-500">
            <img src="/music.jpg" alt="Music visualization" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-br from-white/60 via-white/20 to-white/40" />
            <div className="absolute inset-0 rounded-[40px] ring-1 ring-inset ring-white/50" />
          </div>
        </div>
      </section>

      {/* ── Section 5: CTA ── */}
      <section className="relative z-10 py-20 md:py-40 px-6 md:px-12 text-center bg-black text-white overflow-hidden">
        <div className="space-y-8">
          <p className="text-[10px] tracking-[0.8em] uppercase opacity-40">Forever curious, forever passionate, forever creating</p>
          <h2 className="text-3xl md:text-6xl lg:text-8xl font-serif italic">The future is not waiting.<br />EVA is building it.</h2>
          <button onClick={handleCTAClick} className="mt-12 px-12 py-5 bg-white text-black rounded-full font-bold text-xs uppercase tracking-widest hover:scale-110 transition-transform">
            {isAuthenticated ? '开启世界之旅 ➣' : '开启 EVA 之旅 ➣'}
          </button>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="relative z-10 py-12 md:py-20 px-6 md:px-12 flex flex-col items-center border-t border-black/[0.03] bg-white">
        <div className="flex flex-wrap justify-center gap-6 md:gap-12 text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-6 md:mb-10">
          <a href="#" className="hover:text-black">Instagram</a>
          <a href="#" className="hover:text-black">Weibo</a>
          <a href="#" className="hover:text-black">Developers</a>
        </div>
        <p className="text-[10px] font-bold tracking-[0.4em] text-gray-300">EVA ENTERPRISE ©</p>
      </footer>
    </div>
  );
}
