"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, Cpu, Database, Terminal,
  Globe, Server, ArrowUpRight,
  Layers
} from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';

interface DashboardData {
  users: number;
  agent_runs: number;
  products: number;
  reports: number;
  avg_agent_duration_ms: number;
}

interface ModelData {
  models: { name: string; status: string; provider: string }[];
  total_requests_today: number;
  avg_latency_ms: number;
}

interface McpConnector {
  name: string;
  status: string;
  latency_ms: number;
}

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

const containerFade = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { staggerChildren: 0.1 } }
};

const itemFade = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] } }
};

export default function AdminDashboard() {
  const [stats, setStats] = useState<DashboardData | null>(null);
  const [models, setModels] = useState<ModelData | null>(null);
  const [connectors, setConnectors] = useState<McpConnector[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    api<DashboardData>("/api/v1/admin/stats").then(setStats).catch(() => {});
    api<ModelData>("/api/v1/admin/models").then(setModels).catch(() => {});
    api<{ connectors: McpConnector[] }>("/api/v1/admin/mcp").then(d => setConnectors(d.connectors)).catch(() => {});
    api<{ logs: LogEntry[] }>("/api/v1/admin/logs").then(d => setLogs(d.logs)).catch(() => {});
  }, []);

  const statCards = [
    { label: "Agent 活跃数", value: stats?.agent_runs?.toLocaleString() ?? "--", unit: "次", icon: <Activity size={16}/> },
    { label: "注册用户", value: stats?.users?.toLocaleString() ?? "--", unit: "人", icon: <Globe size={16}/> },
    { label: "Agent 平均耗时", value: stats?.avg_agent_duration_ms?.toFixed(1) ?? "--", unit: "ms", icon: <Database size={16}/> },
    { label: "商品数量", value: stats?.products?.toLocaleString() ?? "--", unit: "件", icon: <Cpu size={16}/> },
  ];

  return (
    <>
      <header className="mb-24">
        <motion.div variants={itemFade} initial="initial" animate="animate" className="flex items-center gap-3 mb-6">
          <span className="w-12 h-[1px] bg-black" />
          <span className="text-[10px] font-black tracking-[0.5em] uppercase">Control Center</span>
        </motion.div>
        <motion.h1 variants={itemFade} initial="initial" animate="animate" className="text-7xl lg:text-9xl font-serif italic tracking-tighter leading-none">
          The <span className="font-sans not-italic font-black text-black">ARCHITECT.</span>
        </motion.h1>
      </header>

      {/* Section 1: Stats */}
      <motion.div
        variants={containerFade}
        initial="initial"
        animate="animate"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-px bg-black/[0.05] border border-black/[0.05] mb-24"
      >
        {statCards.map((stat, i) => (
          <motion.div key={i} variants={itemFade} className="bg-white p-10 group hover:bg-black transition-colors duration-500">
            <div className="flex justify-between items-start mb-10">
              <div className="p-3 rounded-full border border-black/5 group-hover:border-white/20 group-hover:text-white transition-colors">
                {stat.icon}
              </div>
              <ArrowUpRight className="text-gray-300 group-hover:text-white transition-colors" size={14} />
            </div>
            <p className="text-[10px] font-black uppercase tracking-widest text-gray-400 group-hover:text-gray-500 mb-2">{stat.label}</p>
            <div className="flex items-baseline gap-2 group-hover:text-white transition-colors">
              <span className="text-5xl font-serif italic">{stat.value}</span>
              <span className="text-xs font-bold opacity-40">{stat.unit}</span>
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* Section 2: Module Gallery */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">

        {/* RAG 管理入口 */}
        <Link href="/admin/rag" className="lg:col-span-8 block">
          <motion.div
            variants={itemFade}
            initial="initial"
            animate="animate"
            className="group relative aspect-[21/9] bg-white border border-black/[0.03] rounded-[40px] overflow-hidden cursor-pointer shadow-sm hover:shadow-2xl transition-all duration-700"
          >
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="absolute inset-0 p-12 flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 mb-4">
                  <Layers className="text-indigo-500" size={20} />
                  <span className="text-[10px] font-black tracking-widest uppercase">Knowledge Base</span>
                </div>
                <h3 className="text-5xl font-serif italic">RAG Management.</h3>
                <p className="mt-4 text-gray-400 max-w-sm">通过向量库驱动 Agent 的精准决策。</p>
              </div>
              <div className="flex gap-4">
                <span className="px-6 py-2 rounded-full border border-black/10 text-[10px] font-bold uppercase hover:bg-black hover:text-white transition-colors">进入知识库</span>
                <span className="px-6 py-2 rounded-full border border-black/10 text-[10px] font-bold uppercase hover:bg-black hover:text-white transition-colors">同步数据</span>
              </div>
            </div>
            <div className="absolute right-[-10%] bottom-[-10%] w-80 h-80 bg-indigo-50 rounded-full blur-[80px] group-hover:bg-indigo-100 transition-colors" />
          </motion.div>
        </Link>

        {/* 模型管理入口 */}
        <Link href="/admin/models" className="lg:col-span-4 block">
          <motion.div
            variants={itemFade}
            initial="initial"
            animate="animate"
            className="bg-black text-white rounded-[40px] p-12 flex flex-col justify-between relative overflow-hidden group h-full"
          >
            <div className="relative z-10">
              <Server className="text-gray-500 mb-8" size={24} />
              <h3 className="text-3xl font-serif italic mb-4">Model Hub.</h3>
              <div className="space-y-4">
                {(models?.models || []).slice(0, 3).map((m) => (
                  <div key={m.name} className="flex justify-between text-[10px] font-bold uppercase tracking-tighter opacity-50">
                    <span>{m.name}</span>
                    <span className="text-green-400">{m.status === "available" ? "Stable" : m.status}</span>
                  </div>
                ))}
              </div>
            </div>
            <span className="relative z-10 w-full py-4 bg-white text-black rounded-full font-bold text-[10px] uppercase tracking-widest text-center hover:scale-105 transition-transform">
              配置管理
            </span>
            <div className="absolute top-[-20%] right-[-20%] w-60 h-60 bg-white/5 blur-[60px] rounded-full" />
          </motion.div>
        </Link>

        {/* MCP 监控 */}
        <Link href="/admin/mcp" className="lg:col-span-6 block">
          <motion.div variants={itemFade} initial="initial" animate="animate" className="bg-white/40 backdrop-blur-3xl border border-white rounded-[40px] p-10 shadow-xl shadow-black/5 hover:shadow-2xl transition-all cursor-pointer h-full">
             <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-2">
                  <Globe className="text-blue-500" size={18} />
                  <span className="text-xs font-bold uppercase tracking-widest">MCP Connector Status</span>
                </div>
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
             </div>
             <div className="space-y-6">
                {connectors.length === 0 && (
                  <p className="text-sm text-gray-400 py-4">暂无连接器数据</p>
                )}
                {connectors.map((mcp) => (
                  <div key={mcp.name} className="flex justify-between items-center py-4 border-b border-black/[0.03]">
                    <span className="text-sm font-medium">{mcp.name}</span>
                    <span className="text-[10px] font-mono text-gray-400">{mcp.status === "active" ? "CONNECTED" : mcp.status.toUpperCase()} / {mcp.latency_ms}ms</span>
                  </div>
                ))}
             </div>
          </motion.div>
        </Link>

        {/* 日志流 */}
        <Link href="/admin/logs" className="lg:col-span-6 block">
          <motion.div variants={itemFade} initial="initial" animate="animate" className="bg-[#111] rounded-[40px] p-10 overflow-hidden relative h-full cursor-pointer hover:shadow-2xl transition-all">
             <div className="flex items-center gap-2 mb-6 text-gray-500">
                <Terminal size={18} />
                <span className="text-xs font-bold uppercase tracking-widest">Real-time Log Stream</span>
             </div>
             <div className="font-mono text-[11px] text-gray-400 space-y-2 leading-relaxed opacity-80">
                {logs.length === 0 && (
                  <p className="text-gray-600">暂无日志记录。启动 Agent 对话后，日志将在此显示。</p>
                )}
                {logs.map((log, i) => {
                  const color = log.level === "ERROR" ? "text-red-400" : log.level === "SUCCESS" ? "text-green-500" : "text-indigo-500";
                  return (
                    <p key={i}>
                      <span className={color}>[{log.timestamp}]</span> {log.level}: {log.message}
                    </p>
                  );
                })}
                <p className="animate-pulse"><span className="text-gray-600">_</span></p>
             </div>
             <div className="mt-10">
                <span className="text-[10px] font-bold uppercase text-white border-b border-white/20 pb-1 hover:border-white transition-all">
                  查看全量日志
                </span>
             </div>
          </motion.div>
        </Link>

      </div>
    </>
  );
}
