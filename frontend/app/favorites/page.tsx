"use client"
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Star, ShoppingCart, Trash2, ShieldCheck, ChevronRight, Home } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';

interface FavItem {
  id: string;
  product: { id: string; name: string; platform: string; price: number; image_url: string } | null;
  notes: string | null;
  created_at: string;
}

const fadeInUp = {
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 1, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] }
};

const fadeInUpDelayed = (delay: number) => ({
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 1, ease: [0.22, 1, 0.36, 1] as [number, number, number, number], delay }
});

export default function FavoritesPage() {
  const [filter, setFilter] = useState("全部");
  const [items, setItems] = useState<FavItem[]>([]);

  useEffect(() => {
    api<FavItem[]>("/api/v1/favorites").then(setItems).catch(() => {});
  }, []);

  const handleRemove = async (id: string) => {
    await api(`/api/v1/favorites/${id}`, { method: "DELETE" }).catch(() => {});
    setItems(prev => prev.filter(i => i.id !== id));
  };

  const platforms = ["全部", "京东", "天猫", "得物", "拼多多","淘宝","识货","抖音商城","唯品会"];
  const filteredItems = filter === "全部"
    ? items
    : items.filter(i => i.product?.platform === filter);

  return (
    <div className="min-h-screen bg-[#FDFDFD] text-[#1d1d1f] relative overflow-hidden font-sans">

      {/* 背景金属流光 */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[-20%] right-[-10%] w-[60%] h-[60%] bg-[#FCF6BA]/20 blur-[150px] rounded-full opacity-50" />
        <div className="absolute top-0 left-[15%] w-[1px] h-full bg-gradient-to-b from-transparent via-[#C0C0C0]/20 to-transparent" />
        <div className="absolute top-0 left-[85%] w-[1px] h-full bg-gradient-to-b from-transparent via-[#C0C0C0]/20 to-transparent" />
      </div>

      <div className="relative z-10 max-w-[1600px] mx-auto pt-40 pb-20 px-10">

        <Link href="/" className="fixed top-10 left-10 z-50 flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest text-gray-500 hover:text-[#BF953F] transition-colors">
          <Home size={14} /> 返回首页
        </Link>

        {/* 标题区 */}
        <header className="mb-24 flex flex-col items-center text-center">
          <motion.div {...fadeInUp} className="flex items-center gap-4 mb-8">
             <div className="h-[1px] w-12 bg-gradient-to-r from-transparent to-[#BF953F]" />
             <span className="text-[11px] font-black tracking-[0.6em] text-[#BF953F]">珍藏馆</span>
             <div className="h-[1px] w-12 bg-gradient-to-l from-transparent to-[#BF953F]" />
          </motion.div>
          <motion.h1 {...fadeInUpDelayed(0.2)} className="text-7xl lg:text-9xl font-serif italic tracking-tighter leading-none mb-12">
            我的 <span className="font-sans not-italic font-black text-black">珍藏.</span>
          </motion.h1>

          {/* 筛选器 */}
          <motion.div {...fadeInUpDelayed(0.3)} className="flex gap-8 text-[11px] font-bold tracking-[0.2em] text-gray-500">
            {platforms.map((cat) => (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`pb-2 transition-all relative ${filter === cat ? 'text-black' : 'hover:text-black'}`}
              >
                {cat}
                {filter === cat && (
                  <motion.div layoutId="underline" className="absolute bottom-0 left-0 w-full h-[2px] bg-gradient-to-r from-[#BF953F] to-[#FCF6BA]" />
                )}
              </button>
            ))}
          </motion.div>
        </header>

        {/* 商品画廊 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-16">
          <AnimatePresence mode="popLayout">
            {filteredItems.length === 0 && (
              <motion.div
                initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                className="col-span-full text-center py-20"
              >
                <Star size={48} className="mx-auto mb-6 text-gray-300" />
                <p className="text-xl font-serif italic text-gray-500 mb-2">珍藏馆空无一物</p>
                <p className="text-sm text-gray-500">去 AI 购物助手探索心仪好物，收藏后这里就会出现</p>
                <Link href="/assistant" className="inline-block mt-6 px-8 py-3 bg-black text-white rounded-full text-[11px] font-bold tracking-widest hover:bg-[#BF953F] transition-all">
                  前往 AI 购物助手
                </Link>
              </motion.div>
            )}
            {filteredItems.map((item, i) => {
              const p = item.product;
              if (!p) return null;
              return (
              <motion.div
                key={item.id}
                layout
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number], delay: i * 0.1 }}
                className="group relative"
              >
                <div className="absolute -inset-[1px] bg-gradient-to-tr from-[#C0C0C0] via-[#E8E8E8] to-[#999999] rounded-[40px] opacity-20 group-hover:opacity-100 transition-opacity duration-700" />

                <div className="relative bg-white rounded-[40px] p-6 h-full flex flex-col shadow-sm">
                  <Link href={`/product/${p.id}`} className="aspect-[4/5] rounded-[32px] overflow-hidden bg-gray-50 mb-8 relative block">
                    <img
                      src={p.image_url || "https://images.unsplash.com/photo-1587836374828-4dbaba94ee0e?w=400"}
                      alt={p.name}
                      className="w-full h-full object-cover transition-transform duration-1000 group-hover:scale-110"
                      onError={(e) => {
                        (e.target as HTMLImageElement).src = "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=400";
                      }}
                    />
                    <div className="absolute top-6 left-6 flex flex-col gap-2">
                       <span className="px-4 py-1.5 rounded-full bg-white/90 backdrop-blur-md text-[10px] font-bold tracking-widest border border-black/5 shadow-sm">
                         {p.platform}
                       </span>
                    </div>
                    <button className="absolute top-6 right-6 w-10 h-10 rounded-full bg-white/90 backdrop-blur-md flex items-center justify-center text-[#BF953F] shadow-sm hover:scale-110 transition-transform">
                      <Star size={18} fill="currentColor" />
                    </button>
                  </Link>

                  <div className="flex-1 px-4">
                    <div className="flex justify-between items-start mb-4">
                       <h3 className="text-xl font-serif italic leading-tight max-w-[70%]">{p.name}</h3>
                       <div className="flex flex-col items-end">
                          <span className="text-2xl font-black tracking-tighter text-black">¥{p.price?.toLocaleString() || "--"}</span>
                       </div>
                    </div>
                  </div>

                  <div className="mt-8 pt-8 border-t border-black/[0.03] flex justify-between items-center px-4">
                    <button onClick={() => handleRemove(item.id)} className="text-[11px] font-black tracking-[0.2em] text-gray-500 hover:text-red-500 transition-colors flex items-center gap-2">
                       <Trash2 size={14} /> 移除
                    </button>
                    <button className="bg-black text-white px-8 py-3 rounded-full text-[11px] font-black tracking-[0.2em] flex items-center gap-2 hover:bg-gradient-to-r hover:from-[#BF953F] hover:to-[#B38728] transition-all duration-500 shadow-xl shadow-black/10">
                       <ShoppingCart size={14} /> 立即购买
                    </button>
                  </div>
                </div>
              </motion.div>
              );
            })}
          </AnimatePresence>
        </div>

        {/* 底部装饰 */}
        <motion.div {...fadeInUp} className="mt-40 text-center">
           <div className="inline-block relative">
              <div className="absolute -inset-8 bg-[#FCF6BA] blur-[60px] opacity-20" />
              <div className="relative py-12 px-20 border border-[#BF953F]/20 rounded-[40px] bg-white/40 backdrop-blur-xl">
                 <ShieldCheck className="text-[#BF953F] mx-auto mb-6" size={32} />
                 <h2 className="text-2xl font-serif italic mb-4">EVA 正品审计</h2>
                 <p className="text-sm text-gray-600 max-w-sm mx-auto leading-relaxed">
                   您的每一项珍藏都经过 EVA 智脑的全球比价、正品溯源及市场趋势审计。
                 </p>
                 <button className="mt-8 flex items-center gap-2 mx-auto text-[11px] font-bold tracking-widest text-[#BF953F] hover:gap-4 transition-all">
                    了解审计详情 <ChevronRight size={14} />
                 </button>
              </div>
           </div>
        </motion.div>

      </div>
    </div>
  );
}
