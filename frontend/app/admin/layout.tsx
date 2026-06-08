"use client"
import React from 'react';
import {
  Activity, Database, Globe, Cpu, Terminal,
  LayoutDashboard, ShieldCheck, ChevronRight, Home
} from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const menuItems = [
    { name: "概览", icon: <LayoutDashboard size={16}/>, path: "/admin" },
    { name: "Agent 监控", icon: <Activity size={16}/>, path: "/admin/agents" },
    { name: "RAG 管理", icon: <Database size={16}/>, path: "/admin/rag" },
    { name: "MCP 监控", icon: <Globe size={16}/>, path: "/admin/mcp" },
    { name: "模型管理", icon: <Cpu size={16}/>, path: "/admin/models" },
    { name: "日志中心", icon: <Terminal size={16}/>, path: "/admin/logs" },
  ];

  return (
    <div className="min-h-screen bg-[#FDFDFD] text-[#1d1d1f] flex font-sans">
      {/* 垂直命令轨 (Command Rail) */}
      <aside className="w-64 border-r border-black/[0.04] bg-white/50 backdrop-blur-xl fixed h-full z-30">
        <div className="p-8 flex flex-col h-full">
          <Link href="/" className="flex items-center gap-3 mb-12 hover:opacity-60 transition-opacity">
            <div className="w-8 h-8 bg-black rounded-lg flex items-center justify-center text-white font-black italic">E</div>
            <span className="text-[10px] font-black tracking-[0.4em] uppercase">Control</span>
          </Link>

          <nav className="flex-1 space-y-1">
            {menuItems.map((item) => (
              <Link
                key={item.name}
                href={item.path}
                className={`flex items-center justify-between px-4 py-3 rounded-xl transition-all group ${
                  pathname === item.path
                    ? 'bg-black text-white'
                    : 'hover:bg-black hover:text-white'
                }`}
              >
                <div className="flex items-center gap-4">
                  <span className={pathname === item.path ? 'opacity-100' : 'opacity-50 group-hover:opacity-100'}>{item.icon}</span>
                  <span className="text-[11px] font-bold uppercase tracking-widest">{item.name}</span>
                </div>
                <ChevronRight size={12} className={`transition-all ${pathname === item.path ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0'}`} />
              </Link>
            ))}
          </nav>

          <div className="p-6 bg-indigo-50/50 rounded-2xl border border-indigo-100">
             <p className="text-[10px] font-bold text-indigo-500 uppercase tracking-widest mb-1">System Health</p>
             <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                <span className="text-xs font-serif italic text-gray-600">Optimal Performance</span>
             </div>
          </div>
        </div>
      </aside>

      {/* 主工作区 */}
      <main className="flex-1 ml-64 p-12">
        <div className="max-w-[1400px] mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}
