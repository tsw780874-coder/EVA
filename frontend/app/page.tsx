"use client"
import React from 'react';
import { motion } from 'framer-motion';
import { ChevronRight, ArrowRight, Star, User, FileBarChart, Settings, ShoppingBag, LogOut } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';

// 动效配置
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

      {/* --- 全局动态背景光 --- */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-[-10%] right-[-10%] w-[60%] h-[60%] bg-[#F3E8FF] blur-[150px] opacity-40 rounded-full" />
        <div className="absolute bottom-[10%] left-[-5%] w-[50%] h-[50%] bg-[#E0F2FE] blur-[130px] opacity-30 rounded-full" />
        <div className="absolute top-[40%] left-[30%] w-[30%] h-[40%] bg-[#FFF7ED] blur-[120px] opacity-50 rounded-full" />
      </div>

      {/* --- 顶部导航栏 --- */}
      <nav className="fixed top-0 w-full z-50 border-b border-black/[0.03] bg-white/40 backdrop-blur-xl px-12 py-6 flex justify-between items-center">
        <div className="flex items-center gap-12">
          <div className="group cursor-pointer flex items-center gap-2">
            <div className="w-8 h-8 bg-black rounded-full flex items-center justify-center">
              <span className="text-white text-xs font-black italic">E</span>
            </div>
            <span className="text-lg font-bold tracking-[0.3em] uppercase">EVA</span>
          </div>

          <div className="hidden lg:flex gap-8 text-[10px] font-bold tracking-[0.2em] uppercase text-gray-400">
            <a href="/assistant" className="hover:text-black transition-colors flex items-center gap-2">
              <ShoppingBag size={12} /> AI购物助手
            </a>
            <a href="/favorites" className="hover:text-black transition-colors flex items-center gap-2">
              <Star size={12} /> 收藏夹
            </a>
            <a href="/reports" className="hover:text-black transition-colors flex items-center gap-2">
              <FileBarChart size={12} /> 购物报告
            </a>
          </div>
        </div>

        <div className="flex items-center gap-8 text-[10px] font-bold uppercase tracking-widest">
          {isAuthenticated ? (
            <>
              <a href="/profile" className="flex items-center gap-2 hover:opacity-60 transition-opacity">
                 <User size={14} /> 个人中心
              </a>
              <a href="/settings" className="p-2 border border-black/10 rounded-full hover:bg-black hover:text-white transition-all">
                 <Settings size={14} />
              </a>
              <button
                onClick={() => { logout(); router.push('/'); }}
                className="flex items-center gap-2 text-gray-400 hover:text-red-500 transition-colors"
              >
                <LogOut size={12} /> 退出
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="hover:text-black transition-colors">登录</Link>
              <Link href="/register" className="bg-black text-white px-6 py-2.5 rounded-full hover:bg-[#BF953F] transition-all duration-500">
                注册
              </Link>
            </>
          )}
        </div>
      </nav>

      {/* --- Section 1: Hero (Romantic Branding) --- */}
      <section className="relative h-screen flex flex-col items-center justify-center px-10">
        <motion.p
          {...fadeInUp}
          className="text-[12px] font-bold tracking-[0.6em] text-indigo-400 uppercase mb-8"
        >
          Forever passionate, romantic until the very end
        </motion.p>
        <motion.h1
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1.5 }}
          className="text-[14vw] lg:text-[10vw] font-serif italic leading-[0.8] text-center tracking-tighter"
        >
          EVA <span className="font-sans not-italic font-black text-black">SYSTEM</span>
        </motion.h1>
        <motion.div
          {...fadeInUp}
          transition={{ delay: 0.4 }}
          className="mt-12 flex flex-col items-center"
        >
          <div className="h-20 w-[1px] bg-gradient-to-b from-black to-transparent" />
          <p className="mt-6 text-[10px] font-bold tracking-[0.3em] uppercase opacity-40">Scroll to Explore</p>
        </motion.div>
      </section>

      {/* --- Section 2: Platform Introduction (The Magazine Layout) --- */}
      <section className="py-40 px-12 lg:px-40 grid grid-cols-1 lg:grid-cols-12 gap-10">
        <div className="lg:col-span-7">
          <motion.h2
            {...fadeInUp}
            className="text-5xl lg:text-7xl font-serif italic mb-10 leading-tight"
          >
            Built with intelligence, <br />
            <span className="font-sans not-italic font-black">driven by imagination.</span>
          </motion.h2 >
          <motion.div {...fadeInUp} className="max-w-xl space-y-8">
            <p className="text-xl text-gray-500 leading-relaxed">
              EVA（Enterprise Virtual Assistant）是一款企业级 AI Agent 智能体平台。
              我们不仅是在构建工具，而是在定义一种全新的
              <span className="text-black font-medium"> AI 协作范式</span>。
            </p>
            <p className="text-sm text-gray-400 leading-loose">
              作为一个集大模型接入、多 Agent 协作、Workflow 自动化编排、MCP 工具生态、以及长期记忆管理于一体的 AI 应用开发平台，
              EVA 旨在打破人机边界。
            </p>
          </motion.div>
        </div>
        <div className="lg:col-span-5 flex flex-col">
           {/* 蝴蝶插画卡片 */}
           <motion.div
             whileHover={{ scale: 1.02 }}
             className="aspect-[3/4] bg-gray-50 border border-black/[0.03] rounded-[40px] overflow-hidden relative group"
           >
             <div className="absolute inset-0 bg-gradient-to-tr from-indigo-50 to-transparent opacity-60 z-10" />
             <img
               src="/butterfly.jpg"
               alt="Butterfly"
               className="absolute inset-0 w-full h-full object-cover"
             />
             <div className="absolute inset-0 p-12 flex flex-col justify-between z-20">
                <span className="text-[10px] font-black uppercase tracking-widest text-white">EVA</span>

                <h3 className="text-3xl font-serif italic text-black">支持统一接入多个主流大模型 API</h3>
             </div>
           </motion.div>
        </div>
      </section>

      {/* --- Section 3: AI Shopping Engine (The Grid) --- */}
      <section className="py-40 bg-[#F5F5F7]/50 px-12 lg:px-40">
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
            <motion.div
              key={i}
              whileHover={{ y: -10 }}
              className="bg-white p-12 rounded-[30px] shadow-sm border border-black/[0.02]"
            >
              <span className="text-4xl font-serif italic text-indigo-100 block mb-6">{item.icon}</span>
              <h4 className="text-xl font-bold mb-4">{item.title}</h4>
              <p className="text-gray-400 text-sm leading-relaxed">{item.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* --- Section 4: Intelligence Output (The Vertical Layout) --- */}
      <section className="py-60 px-12 lg:px-40 relative">
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
          <motion.div
            {...fadeInUp}
            whileHover={{ scale: 1.02 }}
            className="rounded-[40px] shadow-2xl shadow-indigo-100/50 border border-white/20 overflow-hidden relative aspect-[4/3]"
          >
            <img
              src="/music.jpg"
              alt="Music visualization"
              className="absolute inset-0 w-full h-full object-cover"
            />
            {/* 雾化层 */}
            <div className="absolute inset-0 bg-gradient-to-br from-white/60 via-white/20 to-white/40" />
            {/* 液态玻璃反射 */}
            <div className="absolute -inset-1 bg-gradient-to-br from-white/30 via-transparent to-transparent" />
            <div className="absolute top-0 left-0 right-0 h-1/3 bg-gradient-to-b from-white/40 to-transparent" />
            <div className="absolute bottom-0 right-0 w-1/2 h-1/3 bg-gradient-to-tl from-white/30 to-transparent rounded-tl-[40px]" />
            {/* 玻璃边框高光 */}
            <div className="absolute inset-0 rounded-[40px] ring-1 ring-inset ring-white/50" />
          </motion.div>
        </div>
      </section>

      {/* --- Section 5: Philosophical Quote --- */}
      <section className="py-40 px-12 text-center bg-black text-white overflow-hidden relative">
        <motion.div
          initial={{ scale: 1.2, opacity: 0 }}
          whileInView={{ scale: 1, opacity: 1 }}
          transition={{ duration: 2 }}
          className="space-y-8"
        >
          <p className="text-[10px] tracking-[0.8em] uppercase opacity-40">Forever curious, forever passionate, forever creating</p>
          <h2 className="text-6xl lg:text-8xl font-serif italic">The future is not waiting. <br /> EVA is building it.</h2>
          <button
            onClick={handleCTAClick}
            className="mt-12 px-12 py-5 bg-white text-black rounded-full font-bold text-xs uppercase tracking-widest hover:scale-110 transition-transform"
          >
            {isAuthenticated ? '开启世界之旅 ➣' : 'Start EVA ➣ '}
          </button>
        </motion.div>
      </section>

      {/* --- Footer --- */}
      <footer className="py-20 px-12 flex flex-col items-center border-t border-black/[0.03]">
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
