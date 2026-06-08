"use client"
import React, { useState, useEffect } from 'react';
import { Terminal } from 'lucide-react';
import { api } from '@/lib/api';

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

export default function LogCenter() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState("ALL");

  useEffect(() => {
    api<{ logs: LogEntry[] }>("/api/v1/admin/logs").then(d => setLogs(d.logs)).catch(() => {});
  }, []);

  const displayLogs = logs;

  const filtered = filter === "ALL" ? displayLogs : displayLogs.filter(l => l.level === filter);
  const levels = ["ALL", "INFO", "SUCCESS", "WARN", "ERROR"];

  const levelColor = (level: string) => {
    switch (level) {
      case "ERROR": return "text-red-400";
      case "SUCCESS": return "text-green-400";
      case "WARN": return "text-yellow-400";
      default: return "text-blue-400";
    }
  };

  return (
    <div className="space-y-12">
      <header>
        <h1 className="text-6xl font-serif italic tracking-tighter">The <span className="font-sans not-italic font-black">LOGS.</span></h1>
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.5em] mt-4">Real-time System Stream</p>
      </header>

      <div className="flex gap-3 mb-6">
        {levels.map(l => (
          <button
            key={l}
            onClick={() => setFilter(l)}
            className={`px-4 py-2 rounded-full text-[10px] font-bold uppercase tracking-widest transition-all ${
              filter === l ? "bg-black text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"
            }`}
          >{l}</button>
        ))}
      </div>

      <div className="bg-[#111] rounded-[40px] p-10 font-mono text-xs space-y-1 max-h-[600px] overflow-y-auto">
        {filtered.length === 0 && (
          <p className="text-gray-600 py-10 text-center">暂无日志记录。启动 Agent 对话后，系统日志将在此显示。</p>
        )}
        {filtered.map((log, i) => (
          <p key={i} className="text-gray-400 leading-relaxed">
            <span className={levelColor(log.level)}>[{log.timestamp}]</span>{" "}
            <span className="text-gray-500">{log.level}:</span>{" "}
            <span className="text-gray-300">{log.message}</span>
          </p>
        ))}
        <p className="animate-pulse mt-4"><span className="text-gray-600">_</span></p>
      </div>

      <div className="flex items-center gap-2 text-[10px] font-bold text-gray-300 uppercase tracking-widest">
        <Terminal size={12} />
        {filtered.length} entries
      </div>
    </div>
  );
}
