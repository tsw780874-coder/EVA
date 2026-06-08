"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { api } from '@/lib/api';

interface Connector {
  name: string;
  status: string;
  latency_ms: number;
}

export default function McpMonitor() {
  const [connectors, setConnectors] = useState<Connector[]>([]);

  useEffect(() => {
    api<{ connectors: Connector[]; uptime_seconds: number }>("/api/v1/admin/mcp")
      .then(d => setConnectors(d.connectors)).catch(() => {});
  }, []);

  const displayConnectors = connectors;

  return (
    <div className="space-y-12">
      <header>
        <h1 className="text-6xl font-serif italic tracking-tighter">The <span className="font-sans not-italic font-black">CONNECTORS.</span></h1>
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.5em] mt-4">MCP Protocol Vitals</p>
      </header>

      <div className="grid grid-cols-1 gap-4">
        {displayConnectors.length === 0 && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-sm font-bold tracking-widest">暂无连接器数据</p>
            <p className="text-xs mt-2">启动一次 Agent 对话后，连接器状态将在此显示</p>
          </div>
        )}
        {displayConnectors.map((c, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.1 }}
            className="flex items-center justify-between p-6 bg-white border border-black/[0.04] rounded-2xl"
          >
            <div className="flex items-center gap-4">
              <span className={`w-2 h-2 rounded-full ${
                c.status === "disconnected" ? "bg-red-400" :
                c.status === "degraded" ? "bg-yellow-400" : "bg-green-500"
              }`} />
              <span className="font-bold text-sm">{c.name}</span>
            </div>
            <div className="flex items-center gap-6 text-xs text-gray-400">
              <span className="uppercase font-mono">{c.status.toUpperCase()}</span>
              <span className="font-mono">{c.latency_ms}ms</span>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
