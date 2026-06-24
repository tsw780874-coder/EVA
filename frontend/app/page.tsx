"use client"
import React from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Star, User, FileBarChart, Settings, ShoppingBag, LogOut } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';

// 基础渐显动效
const fadeInUp = {
  initial: { opacity: 0, y: 60 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: false },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] }
};

export default function FashionHome() {
  const router = useRouter();
  const { isAuthenticated, logout } = useAuthStore();

  const handleCTAClick = () => {
    if (isAuthenticated) {
      router.push('/assistant');
    } else {
      router.push('/login');
    }
  };

  return (
    <div className="bg-[#FFFFFF] text-[#1d1d1f] font-sans selection:bg-indigo-50">

      {/* =========================================================================
          LAYER 0: 全局静态/半动态背景弱光 (极简大气的科技氛围)
          ========================================================================= */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] right-[-10%] w-[60%] h-[60%] bg-[#F3E8FF] blur-[150px] opacity-40 rounded-full" />
        <div className="absolute bottom-[10%] left-[-5%] w-[50%] h-[50%] bg-[#E0F2FE] blur-[130px] opacity-30 rounded-full" />
        <div className="absolute top-[40%] left-[30%] w-[30%] h-[40%] bg-[#FFF7ED] blur-[120px] opacity-50 rounded-full" />
      </div>

      {/* =========================================================================
          HERO: 极简纯净纯视频背景屏
          ========================================================================= */}
      <section className="relative h-screen w-full overflow-hidden bg-black">

        {/* LAYER 1: 核心视频容器 (启用硬件加速，保障 100% 丝滑无缝循环) */}
        <div className="absolute inset-0 z-0 h-full w-full overflow-hidden flex items-center justify-center">
          <video
            autoPlay
            loop
            muted
            playsInline
            controls={false}
            preload="auto"
            className="absolute w-full h-full object-cover brightness-110 contrast-105 transform-gpu translate-z-0 pointer-events-none select-none"
            src="/SuperCar.mp4"
          />
          {/* 顶层极轻微的光影渐变过渡，将天际线与顶部导航平滑融合 */}
          <div className="absolute inset-0 bg-gradient-to-b from-white/10 via-transparent to-transparent pointer-events-none" />
          {/* 底部自然淡出，使全景视频过渡到下方白底内容区时极为自然 */}
          <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-white via-white/40 to-transparent pointer-events-none" />
        </div>

        {/* LAYER 2: 顶部高端导航栏 + 页面 Hero 文本中央视觉区 */}
        <div className="relative z-10 h-full flex flex-col">

          {/* 顶层导航栏 */}
          <nav className="w-full border-b border-black/[0.04] bg-white/10 backdrop-blur-md px-6 md:px-12 py-5 flex justify-between items-center shrink-0">
            <div className="flex items-center gap-10">
              <div className="group cursor-pointer flex items-center gap-2.5" onClick={() => router.push('/')}>
                <div className="w-7 h-7 bg-black rounded-full flex items-center justify-center shadow-sm">
                  <span className="text-white text-[11px] font-black italic tracking-tighter">E</span>
                </div>
                <span className="text-base font-bold tracking-[0.35em] text-black">EVA</span>
              </div>

              <div className="hidden lg:flex gap-8 text-[11px] font-bold tracking-[0.2em] text-gray-500">
                <a href="/assistant" className="hover:text-black transition-colors flex items-center gap-2">
                  <ShoppingBag size={13} className="stroke-[2.5]" /> AI 购物助手
                </a>
                <a href="/favorites" className="hover:text-black transition-colors flex items-center gap-2">
                  <Star size={13} className="stroke-[2.5]" /> 收藏夹
                </a>
                <a href="/reports" className="hover:text-black transition-colors flex items-center gap-2">
                  <FileBarChart size={13} className="stroke-[2.5]" /> 购物报告
                </a>
              </div>
            </div>

            <div className="flex items-center gap-6 text-[11px] font-bold tracking-[0.15em]">
              {isAuthenticated ? (
                <div className="flex items-center gap-6">
                  <a href="/profile" className="flex items-center gap-2 hover:text-black text-gray-600 transition-colors">
                     <User size={14} /> 个人中心
                  </a>
                  <a href="/settings" className="p-2 border border-black/10 rounded-full hover:bg-black hover:text-white transition-all">
                     <Settings size={13} />
                  </a>
                  <button
                    onClick={() => { logout(); router.push('/'); }}
                    className="flex items-center gap-1.5 text-gray-400 hover:text-red-500 transition-colors"
                  >
                    <LogOut size={13} /> 退出
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-6">
                  <Link href="/login" className="text-gray-600 hover:text-black transition-colors">登录</Link>
                  <Link href="/register" className="bg-black text-white px-6 py-2 rounded-full hover:bg-neutral-800 shadow-md hover:shadow-lg transition-all duration-300">
                    注册
                  </Link>
                </div>
              )}
            </div>
          </nav>

          {/* 纯净的主题文本区（配备极软背光，完美穿透跑车视线） */}
          <div className="flex-1 flex flex-col items-center justify-center px-6 text-center select-none mt-[-40px] relative">

            {/* 柔和文字背光：即保障了复杂视频画面下的极高可读性，又不会遮挡周边跑车车身 */}
            <div className="absolute w-[85vw] md:w-[55vw] h-[35vh] bg-white/40 blur-[90px] rounded-full pointer-events-none" />

            <motion.p
              {...fadeInUp}
              className="text-[11px] md:text-[12px] font-bold tracking-[0.5em] text-indigo-700/90 uppercase mb-7 relative z-10"
            >
              Forever passionate, romantic until the very end
            </motion.p>

            <motion.h1
              initial={{ opacity: 0, scale: 0.97 }}
              whileInView={{ opacity: 1, scale: 1 }}
              transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
              className="text-[13vw] lg:text-[9vw] leading-[0.85] tracking-tight text-black flex flex-wrap justify-center items-baseline gap-x-[2vw] relative z-10"
            >
              <span className="font-serif italic font-normal text-neutral-900 drop-shadow-md">EVA</span>
              <span className="font-sans not-italic font-black text-black drop-shadow-md">SYSTEM</span>
            </motion.h1>

            <motion.div
              {...fadeInUp}
              transition={{ delay: 0.5, duration: 0.8 }}
              className="mt-16 flex flex-col items-center relative z-10"
            >
              <div className="h-16 w-[1.5px] bg-gradient-to-b from-black via-black/40 to-transparent relative overflow-hidden">
                <motion.div
                  className="absolute top-0 left-0 w-full h-1/2 bg-gradient-to-b from-transparent to-white"
                  animate={{ y: ['-100%', '200%'] }}
                  transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>
              <p className="mt-5 text-[9px] font-extrabold tracking-[0.35em] uppercase text-black/60 drop-shadow-sm">
                Scroll to Explore
              </p>
            </motion.div>

          </div>
        </div>
      </section>

      {/* =========================================================================
          Section 2: Platform Introduction (The Magazine Layout)
          ========================================================================= */}
      <section className="relative z-10 py-40 px-12 lg:px-40 grid grid-cols-1 lg:grid-cols-12 gap-10 bg-white">
        <div className="lg:col-span-7">
          <motion.h2
            {...fadeInUp}
            className="text-5xl lg:text-7xl font-serif italic mb-10 leading-tight"
          >
            Built with intelligence, <br />
            <span className="font-sans not-italic font-black">driven by imagination.</span>
          </motion.h2>
          <motion.div {...fadeInUp} className="max-w-xl space-y-8">
            <p className="text-xl text-gray-500 leading-relaxed">
              EVA （Enterprise Virtual Assistant）是一款企业级 AI Agent 智能体平台。我们不仅是在构建工具，而是在定义一种全新的 <span className="text-black font-medium">AI 协作范式</span>。
            </p>
            <p className="text-sm text-gray-400 leading-loose">
               作为一个集大模型接入、多 Agent 协作、Workflow 自动化编排、MCP 工具生态、以及长期记忆管理于一体的 AI 应用开发平台，EVA 旨在打破人机边界。
            </p>
          </motion.div>
        </div>
        <div className="lg:col-span-5 flex flex-col">
          <motion.div
            whileHover={{ scale: 1.02 }}
            className="aspect-[3/4] bg-gray-50 border border-black/[0.03] rounded-[40px] overflow-hidden relative group"
          >
            <div className="absolute inset-0 bg-gradient-to-tr from-indigo-50 to-transparent opacity-60 z-10" />
            <img src="/butterfly.jpg" alt="Butterfly" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 p-12 flex flex-col justify-between z-20">
              <span className="text-[10px] font-black uppercase tracking-widest text-white">EVA</span>
              <h3 className="text-3xl font-serif italic text-white drop-shadow-md">支持统一接入多个主流大模型 API</h3>
            </div>
          </motion.div>
        </div>
      </section>

      {/* =========================================================================
          Section 3: AI Shopping Engine (The Grid)
          ========================================================================= */}
      <section className="relative z-10 py-40 bg-[#F5F5F7]/50 px-12 lg:px-40">
        <motion.div {...fadeInUp} className="mb-20 text-center">
          <h2 className="text-sm font-black tracking-[0.4em] uppercase mb-4">AI 商品比价引擎</h2>
          <p className="text-4xl lg:text-6xl font-serif italic">Because of you, EVA can embrace the world.</p>
        </motion.div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            { title: "多平台搜索", desc: "京东，淘宝，拼多多，天猫...", icon: "01" },
            { title: "价格聚合", desc: "全网实时报价一目了然", icon: "02" },
            { title: "优惠信息", desc: "精准捕捉隐藏神券与补贴", icon: "03" },
          ].map((item, i) => (
            <motion.div key={i} whileHover={{ y: -10 }} className="bg-white p-12 rounded-[30px] shadow-sm border border-black/[0.02]">
              <span className="text-4xl font-serif italic text-indigo-100 block mb-6">{item.icon}</span>
              <h4 className="text-xl font-bold mb-4">{item.title}</h4>
              <p className="text-gray-400 text-sm leading-relaxed">{item.desc}</p>
            </motion.div>          ))}
        </div>
      </section>

      {/* =========================================================================
          Section 4: Intelligence Output (The Vertical Layout)
          ========================================================================= */}
      <section className="relative z-10 py-60 px-12 lg:px-40">
        <div className="absolute top-0 right-10 text-[20vw] font-black text-black/[0.02] select-none">REPORTS</div>
        <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 items-center gap-24">
          <motion.div {...fadeInUp}>
            <h2 className="text-5xl font-serif italic mb-8">EVA，浪漫热忱，至死不渝</h2>
            <div className="space-y-6">
              {['商品分析报告', '性价比报告', '购买决策报告'].map((text) => (
                <div key={text} className="flex items-center gap-4 group cursor-pointer border-b border-black/[0.05] pb-4">
                  <div className="w-2 h-2 bg-indigo-400 rounded-full scale-0 group-hover:scale-100 transition-transform" />
                  <span className="text-lg text-gray-500 group-hover:text-black transition-colors">{text}</span>
                  <ArrowRight className="ml-auto opacity-0 group-hover:opacity-100 transition-all" size={16} />
                </div>
              ))}
            </div>
          </motion.div>
          <motion.div {...fadeInUp} whileHover={{ scale: 1.02 }} className="rounded-[40px] shadow-2xl shadow-indigo-100/50 border border-white/20 overflow-hidden relative aspect-[4/3]">
            <img src="/music.jpg" alt="Music visualization" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-br from-white/60 via-white/20 to-white/40" />
            <div className="absolute -inset-1 bg-gradient-to-br from-white/30 via-transparent to-transparent" />
            <div className="absolute top-0 left-0 right-0 h-1/3 bg-gradient-to-b from-white/40 to-transparent" />
            <div className="absolute bottom-0 right-0 w-1/2 h-1/3 bg-gradient-to-tl from-white/30 to-transparent rounded-tl-[40px]" />
            <div className="absolute inset-0 rounded-[40px] ring-1 ring-inset ring-white/50" />
          </motion.div>
        </div>
      </section>

      {/* =========================================================================
          Section 5: Philosophical Quote + CTA
          ========================================================================= */}
      <section className="relative z-10 py-40 px-12 text-center bg-black text-white overflow-hidden">
        <motion.div initial={{ scale: 1.2, opacity: 0 }} whileInView={{ scale: 1, opacity: 1 }} transition={{ duration: 2 }} className="space-y-8">
          <p className="text-[10px] tracking-[0.8em] uppercase opacity-40">Forever curious, forever passionate, forever creating</p>
          <h2 className="text-6xl lg:text-8xl font-serif italic">The future is not waiting.<br /> EVA is building it.</h2>
          <button onClick={handleCTAClick} className="mt-12 px-12 py-5 bg-white text-black rounded-full font-bold text-xs uppercase tracking-widest hover:scale-110 transition-transform">
            {isAuthenticated ? '开启世界之旅 ➣' : '开启 EVA 之旅 ➣'}
          </button>
        </motion.div>
      </section>

      {/* =========================================================================
          Footer
          ========================================================================= */}
      <footer className="relative z-10 py-20 px-12 flex flex-col items-center border-t border-black/[0.03] bg-white">
        <div className="flex gap-12 text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-10">
          <a href="#" className="hover:text-black">Instagram</a>
          <a href="#" className="hover:text-black">Weibo</a>
          <a href="#" className="hover:text-black">Developers</a>
        </div>
        <p className="text-[10px] font-bold tracking-[0.4em] text-gray-300">EVA ENTERPRISE ©</p>
      </footer>
    </div>
  );
}