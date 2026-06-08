"use client"
import React, { useState, useEffect } from 'react';
import { Database } from 'lucide-react';
import { api } from '@/lib/api';

interface RagStatus {
  collection: string;
  document_count: number;
  total_chunks: number;
  last_sync: string | null;
  status: string;
}

export default function RagManagement() {
  const [status, setStatus] = useState<RagStatus | null>(null);

  useEffect(() => {
    api<RagStatus>("/api/v1/admin/rag").then(setStatus).catch(() => {});
  }, []);

  const docCount = status?.document_count ?? 0;
  const displayCount = docCount > 1000000 ? `${(docCount/1000000).toFixed(1)}M` : docCount.toLocaleString();

  return (
    <div className="space-y-12">
      <header>
        <h1 className="text-6xl font-serif italic tracking-tighter">The <span className="font-sans not-italic font-black">KNOWLEDGE.</span></h1>
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.5em] mt-4">Vector Index & Retrieval</p>
      </header>

      <div className="bg-black text-white rounded-[40px] p-12 relative overflow-hidden">
        <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 gap-10">
          <div>
            <h2 className="text-4xl font-serif italic mb-4">Knowledge Fabric.</h2>
            <p className="text-gray-400 text-sm leading-relaxed mb-8">
              集合: {status?.collection || "eva_knowledge"} | 状态: {status?.status || "idle"} | 总块数: {status?.total_chunks ?? 0}
            </p>
            <button
              onClick={() => alert("向量索引同步功能需要 Milvus 服务支持。请确保 Milvus 已部署并配置 RAG 数据源。")}
              className="px-10 py-4 bg-white text-black rounded-full font-bold text-[10px] uppercase tracking-widest hover:opacity-80 transition-opacity"
            >
              Update Vector Index
            </button>
          </div>
          <div className="flex items-end justify-end gap-2 h-40">
            {[40, 70, 45, 90, 65, 80, 50, 100].map((h, i) => (
              <div key={i} className="w-4 bg-white/10 rounded-t-sm" style={{ height: `${h}%` }} />
            ))}
          </div>
        </div>
        <div className="absolute top-0 right-0 p-10 opacity-5"><Database size={200} /></div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {[
          { label: "已索引文档", value: displayCount },
          { label: "总数据块", value: (status?.total_chunks ?? 0).toLocaleString() },
          { label: "最近同步", value: status?.last_sync ? new Date(status.last_sync).toLocaleDateString('zh-CN') : "从未" },
        ].map((stat, i) => (
          <div key={i} className="bg-white border border-black/[0.04] rounded-[32px] p-8">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">{stat.label}</p>
            <p className="text-4xl font-serif italic">{stat.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
