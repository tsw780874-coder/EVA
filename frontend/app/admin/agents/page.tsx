"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Activity } from 'lucide-react';
import { api } from '@/lib/api';

interface AgentRun {
  id: string;
  user_id: string;
  agent_type: string;
  status: string;
  duration_ms: number | null;
  created_at: string;
}

export default function AgentsMonitor() {
  const [agents, setAgents] = useState<AgentRun[]>([]);

  useEffect(() => {
    api<AgentRun[]>("/api/v1/admin/agents").then(setAgents).catch(() => {});
  }, []);

  const displayAgents = agents.slice(0, 6);

  return (
    <div className="space-y-12">
      <header>
        <h1 className="text-6xl font-serif italic tracking-tighter">The <span className="font-sans not-italic font-black">AGENTS.</span></h1>
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.5em] mt-4">Real-time Autonomous Activity</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {displayAgents.length === 0 && (
          <div className="col-span-full text-center py-20 text-gray-400">
            <p className="text-sm font-bold tracking-widest">暂无 Agent 运行记录</p>
            <p className="text-xs mt-2">启动一次 AI 对话后，Agent 运行记录将在此显示</p>
          </div>
        )}
        {displayAgents.map((a, i) => (
          <motion.div
            key={a.id}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: i * 0.1 }}
            className="bg-white border border-black/[0.04] rounded-[32px] p-8 hover:shadow-2xl transition-all group"
          >
             <div className="flex justify-between items-start mb-8">
                <div className="w-12 h-12 rounded-2xl bg-gray-50 flex items-center justify-center text-black group-hover:bg-black group-hover:text-white transition-colors">
                   <Activity size={20} />
                </div>
                <span className={`px-3 py-1 rounded-full text-[9px] font-bold border ${
                  a.status === "completed" ? "bg-green-50 text-green-600 border-green-100" :
                  a.status === "failed" ? "bg-red-50 text-red-600 border-red-100" :
                  "bg-yellow-50 text-yellow-600 border-yellow-100"
                }`}>
                  {a.status.toUpperCase()}
                </span>
             </div>
             <h3 className="text-xl font-serif italic mb-2">{a.agent_type}</h3>
             <p className="text-xs text-gray-400 mb-6">
               {a.duration_ms ? `耗时 ${a.duration_ms}ms` : "等待执行"}
             </p>
             <div className="space-y-3 pt-6 border-t border-black/[0.02]">
                <div className="flex justify-between text-[10px] font-bold uppercase text-gray-400">
                   <span>User ID</span>
                   <span className="text-black text-xs">{a.user_id.slice(0, 8)}...</span>
                </div>
             </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
