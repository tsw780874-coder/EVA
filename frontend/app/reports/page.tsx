"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell
} from 'recharts';
import { Download, Share2, ShieldCheck, Zap, ArrowDownRight, Info, Home, FileText } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';

interface ReportListItem {
  id: string;
  title: string;
  type: string;
  summary: string | null;
  created_at: string;
}

interface ReportDetail {
  id: string;
  title: string;
  type: string;
  content: {
    price_trend?: { day: string; price: number }[];
    platform_comparison?: { name: string; price: number; color: string }[];
    dimensions?: { label: string; score: number }[];
    recommendation?: string;
    suggested_price?: number;
    suggested_platform?: string;
    confidence?: string;
  } | null;
  products: { name: string; platform: string; price: number }[] | null;
  summary: string | null;
  created_at: string;
}

const fadeInUp = {
  initial: { opacity: 0, y: 30 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] }
};

const fadeInUpDelayed = (delay: number) => ({
  initial: { opacity: 0, y: 30 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number], delay }
});


export default function ShoppingReport() {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [activeReport, setActiveReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<ReportListItem[]>("/api/v1/reports")
      .then(async (list) => {
        setReports(list);
        if (list.length > 0) {
          const detail = await api<ReportDetail>(`/api/v1/reports/${list[0].id}`);
          setActiveReport(detail);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSelectReport = async (id: string) => {
    const detail = await api<ReportDetail>(`/api/v1/reports/${id}`).catch(() => null);
    if (detail) setActiveReport(detail);
  };

  const content = activeReport?.content;
  const priceData = content?.price_trend || [];
  const platformData = content?.platform_comparison || [];
  const dimensions = content?.dimensions || [];
  const suggestedPrice = content?.suggested_price ?? activeReport?.products?.[0]?.price ?? null;
  const suggestedPlatform = content?.suggested_platform ?? activeReport?.products?.[0]?.platform ?? null;
  const confidence = content?.recommendation ?? (activeReport?.summary || null);
  const reportTitle = activeReport?.title || null;
  const reportId = activeReport?.id ? `#EVA-${activeReport.id.slice(0, 8).toUpperCase()}` : null;
  const reportDate = activeReport?.created_at
    ? new Date(activeReport.created_at).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    : null;

  const typeLabels: Record<string, string> = {
    price_analysis: "价格分析",
    product_report: "商品报告",
    decision_report: "决策报告",
  };

  return (
    <div className="min-h-screen bg-[#FDFDFD] text-[#1d1d1f] pt-32 pb-20 px-8 lg:px-24">

      {/* 报告头部 */}
      <header className="max-w-7xl mx-auto mb-24 flex flex-col lg:flex-row justify-between items-end gap-10">
        <Link href="/" className="fixed top-10 left-10 z-50 flex items-center gap-2 text-[11px] font-bold tracking-widest text-gray-500 hover:text-black transition-colors">
          <Home size={14} /> 返回首页
        </Link>
        <motion.div {...fadeInUp} className="max-w-2xl">
          <div className="flex items-center gap-3 mb-6 text-indigo-500 font-bold tracking-[0.3em] text-[11px]">
            <Zap size={14} fill="currentColor" /> EVA 智能分析报告
          </div>
          <h1 className="text-6xl lg:text-8xl font-serif italic leading-none mb-8">
            深度分析 <br />
            <span className="font-sans not-italic font-black tracking-tighter text-black">{reportTitle || "购物分析报告"}</span>
          </h1>
          <p className="text-gray-600 text-lg">
            {reportId && <>报告编号：{reportId} &nbsp;|&nbsp;</>}
            类型：{activeReport?.type ? (typeLabels[activeReport.type] || activeReport.type) : "分析报告"} &nbsp;|&nbsp;
            生成时间：{reportDate || "—"}
          </p>
        </motion.div>

        <motion.div {...fadeInUpDelayed(0.2)} className="flex gap-4">
          <button className="flex items-center gap-2 px-6 py-3 rounded-full border border-black/5 hover:bg-black hover:text-white transition-all text-xs font-bold tracking-widest">
            <Download size={14} /> 导出 PDF
          </button>
          <button className="flex items-center gap-2 px-6 py-3 rounded-full bg-black text-white hover:opacity-80 transition-all text-xs font-bold tracking-widest">
            <Share2 size={14} /> 分享见解
          </button>
        </motion.div>
      </header>

      {/* 报告列表选择器 */}
      {reports.length > 1 && (
        <div className="max-w-7xl mx-auto mb-16 flex gap-4 overflow-x-auto pb-4">
          {reports.map((r) => (
            <button
              key={r.id}
              onClick={() => handleSelectReport(r.id)}
              className={`shrink-0 px-6 py-3 rounded-full text-[11px] font-bold tracking-widest transition-all ${
                activeReport?.id === r.id
                  ? "bg-black text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              <FileText size={14} className="inline mr-2" />
              {r.title}
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="max-w-7xl mx-auto text-center py-20">
          <p className="text-xl font-serif italic text-gray-500">正在加载分析报告...</p>
        </div>
      )}

      {!loading && !activeReport && (
        <div className="max-w-7xl mx-auto text-center py-20">
          <FileText size={48} className="mx-auto mb-6 text-gray-300" />
          <p className="text-xl font-serif italic text-gray-500 mb-2">暂无报告</p>
          <p className="text-sm text-gray-500">去 AI 购物助手发起一次分析，生成报告后将在此展示</p>
          <Link href="/assistant" className="inline-block mt-6 px-8 py-3 bg-black text-white rounded-full text-[11px] font-bold tracking-widest hover:bg-indigo-600 transition-all">
            前往 AI 购物助手
          </Link>
        </div>
      )}

      {activeReport && (
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-16">

        {/* 左侧核心指标 */}
        <div className="lg:col-span-4 space-y-12">
          <motion.div {...fadeInUp} className="p-10 bg-indigo-50/30 rounded-[40px] border border-indigo-100/50">
            <h3 className="text-xs font-black tracking-[0.2em] text-indigo-500 mb-8 flex items-center gap-2">
              <ArrowDownRight size={16} /> 核心结论
            </h3>
            <div className="space-y-6">
              {suggestedPrice != null ? (
              <div>
                <span className="text-5xl font-black italic">¥{suggestedPrice.toLocaleString()}</span>
                <p className="text-sm text-gray-600 mt-2">EVA 建议下单价（{suggestedPlatform || "—"}）</p>
              </div>
              ) : (
              <div>
                <span className="text-xl font-serif italic text-gray-400">暂无价格数据</span>
              </div>
              )}
              <div className="pt-6 border-t border-indigo-200/30">
                <p className="text-sm leading-relaxed text-indigo-900/70">
                  {confidence || "暂无分析结论。请通过 AI 购物助手生成完整的商品分析报告。"}
                </p>
              </div>
            </div>
          </motion.div>

          <motion.div {...fadeInUpDelayed(0.2)} className="space-y-6 px-4">
            <h4 className="text-[11px] font-black tracking-[0.3em] text-gray-500">维度评分</h4>
            {dimensions.length === 0 && (
              <p className="text-sm text-gray-400">暂无维度评分数据</p>
            )}
            {dimensions.map((item) => (
              <div key={item.label}>
                <div className="flex justify-between text-xs font-bold mb-2">
                  <span>{item.label}</span>
                  <span>{item.score}%</span>
                </div>
                <div className="h-[2px] w-full bg-gray-100 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    whileInView={{ width: `${item.score}%` }}
                    transition={{ duration: 1, delay: 0.5 }}
                    className="h-full bg-black"
                  />
                </div>
              </div>
            ))}
          </motion.div>
        </div>

        {/* 右侧图表区 */}
        <div className="lg:col-span-8 space-y-16">

          {/* 价格走势图 */}
          <motion.div {...fadeInUp} className="bg-white p-10 rounded-[40px] shadow-sm border border-black/[0.02]">
            <div className="flex justify-between items-center mb-10">
              <h3 className="text-sm font-black tracking-widest">7天价格趋势</h3>
              <div className="flex items-center gap-2 text-[11px] text-gray-500 font-bold">
                <Info size={12} /> {priceData.length > 0 ? "来自历史搜索记录" : "暂无历史价格数据"}
              </div>
            </div>
            {priceData.length === 0 ? (
              <div className="h-[300px] w-full flex items-center justify-center text-gray-400">
                <p className="text-sm">暂无价格趋势数据。通过 AI 购物助手搜索商品后，价格走势将在此展示。</p>
              </div>
            ) : (
            <div className="h-[300px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={priceData}>
                  <defs>
                    <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366F1" stopOpacity={0.1}/>
                      <stop offset="95%" stopColor="#6366F1" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis
                    dataKey="day"
                    axisLine={false}
                    tickLine={false}
                    tick={{fontSize: 11, fontWeight: 'bold', fill: '#666'}}
                    dy={10}
                  />
                  <YAxis hide domain={['dataMin - 500', 'dataMax + 500']} />
                  <Tooltip
                    contentStyle={{ borderRadius: '20px', border: 'none', boxShadow: '0 20px 50px rgba(0,0,0,0.05)', fontSize: '12px', fontWeight: 'bold' }}
                    cursor={{ stroke: '#6366F1', strokeWidth: 1, strokeDasharray: '5 5' }}
                    formatter={(value) => [`¥${Number(value).toLocaleString()}`, '价格']}
                  />
                  <Line
                    type="monotone"
                    dataKey="price"
                    stroke="#6366F1"
                    strokeWidth={4}
                    dot={{ r: 4, fill: '#6366F1', strokeWidth: 2, stroke: '#fff' }}
                    activeDot={{ r: 8, strokeWidth: 0 }}
                    animationDuration={2000}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            )}
          </motion.div>

          {/* 平台横向对比 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <motion.div {...fadeInUp} className="bg-white p-10 rounded-[40px] border border-black/[0.02]">
              <h3 className="text-sm font-black tracking-widest mb-8">平台价格矩阵</h3>
              {platformData.length === 0 ? (
                <div className="h-[200px] w-full flex items-center justify-center text-gray-400">
                  <p className="text-sm">暂无平台对比数据</p>
                </div>
              ) : (
              <div className="h-[200px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={platformData} layout="vertical">
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{fontSize: 12, fontWeight: 'bold'}} />
                    <Tooltip cursor={{fill: 'transparent'}} formatter={(value) => [`¥${Number(value).toLocaleString()}`, '价格']} />
                    <Bar dataKey="price" radius={[0, 10, 10, 0]} barSize={20}>
                      {platformData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} opacity={0.6} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              )}
            </motion.div>

            <motion.div {...fadeInUpDelayed(0.2)} className="bg-black text-white p-10 rounded-[40px] relative overflow-hidden">
               <div className="absolute top-[-10%] right-[-10%] w-40 h-40 bg-indigo-500 blur-[80px] opacity-30" />
               <h3 className="text-xs font-black tracking-widest mb-6 opacity-60">EVA 深度建议</h3>
               <p className="text-lg font-serif italic leading-relaxed">
                 {activeReport?.summary || "暂无深度分析数据。请通过 AI 购物助手生成完整的分析报告。"}
               </p>
               <div className="mt-8 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full border border-white/20 flex items-center justify-center">
                    <ShieldCheck size={18} className="text-indigo-400" />
                  </div>
                  <span className="text-[11px] font-bold tracking-widest">已通过正品链路审计</span>
               </div>
            </motion.div>
          </div>
        </div>
      </div>
      )}

      {/* 装饰性页脚 */}
      <motion.div {...fadeInUp} className="max-w-7xl mx-auto mt-32 text-center border-t border-black/[0.03] pt-20">
         <p className="text-[11px] font-black tracking-[0.5em] text-gray-500 mb-4">永远热忱，浪漫至死不渝</p>
         <div className="text-2xl font-serif italic text-gray-600">购物不仅是消费，更是决策的艺术。</div>
      </motion.div>
    </div>
  );
}
