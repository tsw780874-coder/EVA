"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useParams } from 'next/navigation';
import {
  ArrowLeft, Share2, Heart, ShieldCheck,
  TrendingDown, Globe, ShoppingCart, Home
} from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { fadeInUp, fadeInUpDelayed } from '@/lib/animations';

interface PricePoint { day: string; price: number; }
interface PlatformPrice { name: string; price: number; color: string; }
interface Dimension { label: string; score: number; }

interface ProductData {
  id: string;
  name: string;
  platform: string;
  price: number;
  original_price: number | null;
  url: string | null;
  image_url: string | null;
  description: string | null;
  specs: Record<string, string> | null;
  rating: number | null;
  review_count: number | null;
  updated_at: string;
  price_trend?: PricePoint[];
  platform_comparison?: PlatformPrice[];
  dimensions?: Dimension[];
  ai_analysis?: string;
  suggested_price?: number;
  suggested_platform?: string;
}

const fallbackImage = "https://images.unsplash.com/photo-1695663300508-651296765757?auto=format&fit=crop&q=80&w=1200";

export default function ProductDetailPage() {
  const params = useParams();
  const id = params?.id as string;
  const [product, setProduct] = useState<ProductData | null>(null);
  const [favorited, setFavorited] = useState(false);

  useEffect(() => {
    if (!id) return;
    api<ProductData>(`/api/v1/products/${id}`).then(setProduct).catch(() => {});
  }, [id]);

  const handleFavorite = async () => {
    if (!id || !product) return;
    if (favorited) return;
    await api("/api/v1/favorites", {
      method: "POST",
      body: JSON.stringify({ product_id: id }),
    }).then(() => setFavorited(true)).catch(() => {});
  };

  const p = product;
  const imageUrl = p?.image_url || fallbackImage;
  const priceTrend = p?.price_trend || [];
  const historicalHigh = priceTrend.length > 0
    ? Math.max(...priceTrend.map(pt => pt.price))
    : null;
  const historicalAvg = priceTrend.length > 0
    ? Math.round(priceTrend.reduce((a, b) => a + b.price, 0) / priceTrend.length)
    : null;
  const discountAmount = p?.original_price && p?.price
    ? p.original_price - p.price
    : null;
  const dimensions = p?.dimensions || [];
  const displayName = p?.name;
  const displayPrice = p?.price;
  const platform = p?.platform;

  return (
    <div className="min-h-screen bg-[#FDFDFD] text-[#1d1d1f] font-sans selection:bg-indigo-50">

      <div className="fixed top-24 left-10 right-10 flex justify-between items-center text-[10px] font-mono tracking-widest text-gray-400 z-20 pointer-events-none">
        <span>EVA PRODUCT INTELLIGENCE</span>
        <span>{p?.id ? `#${p.id.slice(0, 8).toUpperCase()}` : ""}</span>
      </div>

      <nav className="fixed top-0 w-full z-30 px-10 py-6 flex justify-between items-center bg-white/40 backdrop-blur-md border-b border-black/[0.03]">
        <Link href="/favorites" className="flex items-center gap-2 text-[11px] font-black uppercase tracking-widest hover:opacity-50 transition-opacity">
          <ArrowLeft size={14} /> 返回珍藏馆
        </Link>
        <div className="flex gap-6">
          <Link href="/" className="flex items-center gap-2 text-[11px] font-bold tracking-widest text-gray-500 hover:text-black transition-colors">
            <Home size={14} /> 首页
          </Link>
          <button
            onClick={handleFavorite}
            className={`transition-colors ${favorited ? 'text-red-500' : 'text-gray-500 hover:text-red-500'}`}
            title={favorited ? '已收藏' : '加入收藏'}
          >
            <Heart size={18} fill={favorited ? 'currentColor' : 'none'} />
          </button>
        </div>
      </nav>

      <main className="max-w-[1400px] mx-auto pt-40 pb-20 px-10">

        {/* 第一章：头条展示 */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-16 mb-32">
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 1.2 }}
            className="lg:col-span-7 relative aspect-[4/5] bg-gray-50 rounded-[2px] overflow-hidden group"
          >
            <img
              src={imageUrl}
              alt={displayName}
              className="w-full h-full object-cover transition-transform duration-1000 group-hover:scale-105"
              onError={(e) => {
                (e.target as HTMLImageElement).src = fallbackImage;
              }}
            />
            <div className="absolute bottom-10 left-10 bg-white/90 backdrop-blur-md p-6 border border-[#BF953F]/20">
              <p className="text-[10px] font-black uppercase tracking-widest text-[#BF953F] mb-1">建议入手价</p>
              {p?.suggested_price != null ? (
                <>
                  <p className="text-3xl font-serif italic text-black">¥{p.suggested_price.toLocaleString()}</p>
                  <p className="text-[11px] text-gray-500 mt-1">{p.suggested_platform || p.platform || ""}</p>
                </>
              ) : displayPrice != null ? (
                <>
                  <p className="text-3xl font-serif italic text-black">¥{displayPrice.toLocaleString()}</p>
                  <p className="text-[11px] text-gray-500 mt-1">{p?.platform || ""}</p>
                </>
              ) : (
                <p className="text-sm text-gray-400">暂无价格</p>
              )}
            </div>
          </motion.div>

          <div className="lg:col-span-5 flex flex-col">
            <motion.div {...fadeInUp} className="mb-12">
              <h1 className="text-6xl lg:text-8xl font-serif italic leading-[0.85] tracking-tighter mb-8">
                {displayName || "商品详情"}
              </h1>
              <div className="flex items-center gap-4 py-4 border-y border-black/[0.05]">
                <span className="text-[11px] font-black tracking-widest">平台: {platform || "—"}</span>
                <span className="w-1 h-1 bg-gray-300 rounded-full" />
                <span className="text-[11px] font-black tracking-widest text-green-600">有货</span>
              </div>
            </motion.div>

            <motion.p {...fadeInUpDelayed(0.2)} className="text-xl text-gray-500 leading-relaxed mb-10 italic font-serif">
              {p?.description ? `"${p.description}"` : ""}
            </motion.p>

            <motion.a
              href={p?.url || "#"}
              target="_blank"
              rel="noopener noreferrer"
              {...fadeInUpDelayed(0.3)}
              className="w-full py-5 bg-black text-white rounded-full font-bold text-[11px] tracking-[0.3em] hover:bg-gradient-to-r hover:from-[#BF953F] hover:to-[#B38728] transition-all duration-500 shadow-2xl shadow-black/10 flex items-center justify-center gap-3"
            >
              前往购买 <ShoppingCart size={14} />
            </motion.a>
          </div>
        </section>

        {/* 第二章：价格走势与审计 */}
        <section className="grid grid-cols-1 lg:grid-cols-12 gap-16 mb-32 border-t border-black/[0.05] pt-20">
          <div className="lg:col-span-4">
            <h2 className="text-[11px] font-black tracking-[0.4em] text-gray-600 mb-10 flex items-center gap-2">
              <TrendingDown size={14} className="text-[#BF953F]" /> 市场趋势
            </h2>
            <div className="space-y-8">
              {[
                { label: "历史最高", value: historicalHigh != null ? `¥${historicalHigh.toLocaleString()}` : "暂无数据", color: "text-gray-400" },
                { label: "历史均价", value: historicalAvg != null ? `¥${historicalAvg.toLocaleString()}` : "暂无数据", color: "text-gray-400" },
                { label: "当前优惠", value: discountAmount != null ? `- ¥${discountAmount.toLocaleString()}` : "暂无数据", color: "text-[#BF953F]" },
              ].map((stat, i) => (
                <div key={i} className="flex justify-between items-end border-b border-black/[0.03] pb-4">
                  <span className="text-[11px] font-bold tracking-widest text-gray-500">{stat.label}</span>
                  <span className={`text-2xl font-serif italic ${stat.color}`}>{stat.value}</span>
                </div>
              ))}

              {/* 维度评分 */}
              <div className="pt-8 space-y-5">
                <h3 className="text-[11px] font-black tracking-[0.3em] text-gray-500">维度评分</h3>
                {dimensions.length === 0 && (
                  <p className="text-sm text-gray-400">暂无维度评分数据</p>
                )}
                {dimensions.map((item) => (
                  <div key={item.label}>
                    <div className="flex justify-between text-[11px] font-bold mb-1.5">
                      <span>{item.label}</span>
                      <span>{item.score}%</span>
                    </div>
                    <div className="h-[2px] w-full bg-gray-100 rounded-full overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        whileInView={{ width: `${item.score}%` }}
                        transition={{ duration: 1, delay: 0.3 }}
                        className="h-full bg-black"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="lg:col-span-8">
            <div>
              <h3 className="text-xl font-bold mb-6">EVA 分析建议</h3>
              {p?.ai_analysis ? (
                <p className="text-sm text-gray-600 leading-loose mb-6 text-justify">{p.ai_analysis}</p>
              ) : (
                <p className="text-sm text-gray-400 leading-loose mb-6 text-justify">
                  暂无 AI 分析数据。请通过 AI 购物助手搜索此商品以获取智能分析。
                </p>
              )}
              {p?.description && (
                <div className="p-6 bg-gray-50 rounded-2xl mb-6">
                  <p className="text-xs font-serif italic leading-relaxed text-gray-600">
                    "{p.description}"
                  </p>
                </div>
              )}
            </div>

            {/* 平台价格矩阵 */}
            {p?.platform_comparison && p.platform_comparison.length > 0 && (
              <div className="mt-12 bg-white border border-black/[0.03] rounded-[40px] p-8">
                <h3 className="text-[11px] font-black tracking-widest mb-6">平台价格矩阵</h3>
                <div className="space-y-3">
                  {p.platform_comparison.map((entry, i) => (
                    <div key={i} className="flex justify-between items-center p-3 rounded-xl bg-gray-50/50">
                      <div className="flex items-center gap-3">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: entry.color }} />
                        <span className="text-sm font-bold">{entry.name}</span>
                      </div>
                      <span className="text-sm font-black">¥{entry.price.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* 第三章：技术规格 */}
        <section className="bg-black text-white p-12 lg:p-24 rounded-[2px] relative overflow-hidden">
           <div className="absolute top-0 right-0 p-10 opacity-10">
              <ShieldCheck size={300} />
           </div>
           <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 gap-20">
              <div>
                <h2 className="text-xs font-black uppercase tracking-[0.5em] text-gray-500 mb-12">规格参数</h2>
                <div className="grid grid-cols-2 gap-10">
                  {p?.specs && Object.keys(p.specs).length > 0 ? (
                    Object.entries(p.specs).map(([key, val], i) => (
                      <div key={i} className="border-l border-white/10 pl-6">
                        <p className="text-[11px] text-gray-500 uppercase tracking-widest mb-1">{key}</p>
                        <p className="text-sm font-bold tracking-tight">{val}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-gray-500 text-sm col-span-2">暂无规格数据</p>
                  )}
                </div>
              </div>
              <div className="flex flex-col justify-center">
                 <div className="flex items-center gap-4 mb-8">
                    <div className="w-12 h-12 rounded-full border border-white/20 flex items-center justify-center text-indigo-400">
                       <Globe size={24} />
                    </div>
                    <span className="text-sm font-serif italic">EVA Agent 全球价格同步</span>
                 </div>
                 <p className="text-gray-400 text-sm leading-relaxed mb-8">
                   EVA 已经穿透了全球 120 个节点的比价服务。您看到的价格已经包含了预测的税费、转运成本及可能存在的额外补贴。
                 </p>
                 <Link href="/reports" className="w-fit text-[11px] font-black tracking-widest border-b border-[#BF953F] pb-1 text-[#BF953F] hover:text-white hover:border-white transition-all">
                   查看完整对比报告
                 </Link>
              </div>
           </div>
        </section>

        <footer className="mt-40 pt-20 border-t border-black/[0.05] text-center">
           <p className="text-[11px] font-black tracking-[0.8em] text-gray-500">
             永远热忱，浪漫至死不渝
           </p>
        </footer>

      </main>
    </div>
  );
}
