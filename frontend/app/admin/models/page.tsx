"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Cpu } from 'lucide-react';
import { api } from '@/lib/api';

interface ModelInfo {
  name: string;
  status: string;
  provider: string;
}

export default function ModelManagement() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [activeModel, setActiveModel] = useState("");

  useEffect(() => {
    api<{ models: ModelInfo[] }>("/api/v1/admin/models")
      .then(d => {
        setModels(d.models);
        if (d.models.length > 0) setActiveModel(d.models[0].name);
      }).catch(() => {});
  }, []);

  const displayModels = models;

  return (
    <div className="space-y-12">
      <header>
        <h1 className="text-6xl font-serif italic tracking-tighter">The <span className="font-sans not-italic font-black">MODELS.</span></h1>
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.5em] mt-4">LLM Traffic Gateway</p>
      </header>

      <div className="space-y-4">
        {displayModels.length === 0 && (
          <div className="text-center py-20 text-gray-400">
            <p className="text-sm font-bold tracking-widest">暂无模型数据</p>
            <p className="text-xs mt-2">请检查 LLM API 密钥配置</p>
          </div>
        )}
        {displayModels.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className={`flex items-center justify-between p-6 rounded-2xl border cursor-pointer transition-all ${
              activeModel === m.name
                ? "bg-black text-white border-black"
                : "bg-white border-black/[0.04] hover:shadow-md"
            }`}
            onClick={() => setActiveModel(m.name)}
          >
            <div className="flex items-center gap-4">
              <Cpu size={20} />
              <div>
                <p className="font-bold text-sm">{m.name}</p>
                <p className="text-[10px] uppercase opacity-50">{m.provider}</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className={`px-3 py-1 rounded-full text-[9px] font-bold ${
                m.status === "available" ? "bg-green-100 text-green-600" : "bg-gray-100 text-gray-400"
              }`}>{m.status.toUpperCase()}</span>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
