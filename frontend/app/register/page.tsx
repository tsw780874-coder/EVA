"use client"
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { User, Mail, Lock, ArrowRight, ShieldCheck, Home, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';

export default function RegisterPage() {
  const router = useRouter();
  const register = useAuthStore((s) => s.register);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await register(email, name, password);
      router.push('/assistant');
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center overflow-hidden bg-[#F9F9F9]">

      {/* --- 底片层：雪景景深 (Snow Scene DOF) --- */}
      <div className="absolute inset-0 z-0">
        <motion.img
          initial={{ scale: 1.2, opacity: 0 }}
          animate={{ scale: 1, opacity: 0.6 }}
          transition={{ duration: 2.5 }}
          src="https://images.unsplash.com/photo-1491002052546-bf38f186af56?q=80&w=2000&auto=format&fit=crop"
          alt="White Snow"
          className="w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-white/40 backdrop-blur-[4px]" />
      </div>

      {/* --- 装饰线条：银色网格 --- */}
      <div className="absolute inset-0 pointer-events-none z-10">
        <div className="absolute top-0 right-1/4 w-[1px] h-full bg-black/[0.02]" />
        <div className="absolute bottom-[30%] left-0 w-full h-[1px] bg-black/[0.02]" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] border border-black/[0.01] rounded-full" />
      </div>

      {/* --- 返回首页 --- */}
      <Link href="/" className="absolute top-12 right-12 z-30 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-gray-400 hover:text-black transition-colors">
        <Home size={12} /> 返回首页
      </Link>

      {/* --- 玻璃视窗：极简白 (Essential Glass) --- */}
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.5 }}
        className="relative z-20 w-full max-w-[500px] mx-6"
      >
        <div className="bg-white/50 backdrop-blur-[60px] border border-white rounded-[48px] p-12 lg:p-16 shadow-[0_40px_120px_rgba(0,0,0,0.03)]">

          <div className="text-center mb-12">
            <div className="inline-block w-10 h-10 bg-[#BF953F] rounded-full mb-8 flex items-center justify-center shadow-lg">
               <span className="text-white font-black text-xl italic">E</span>
            </div>
            <h1 className="text-4xl font-serif italic text-black tracking-tighter mb-4">创建身份</h1>
            <p className="text-[10px] font-black text-gray-400 uppercase tracking-[0.5em]">纯净探索，无限可能</p>
          </div>

          <form className="space-y-8" onSubmit={handleSubmit}>
            {error && (
              <p className="text-red-500 text-xs text-center -mb-4">{error}</p>
            )}
            <div className="group relative">
              <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-400 block mb-2 group-focus-within:text-black transition-colors">
                您的姓名 / NAME
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="如何称呼您"
                  className="w-full bg-transparent border-b border-black/[0.08] py-3 text-sm text-black outline-none focus:border-black transition-all placeholder:text-gray-300"
                />
                <User className="absolute right-0 top-3 text-gray-300" size={16} />
              </div>
            </div>

            <div className="group relative">
              <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-400 block mb-2 group-focus-within:text-black transition-colors">
                注册邮箱 / EMAIL
              </label>
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="identity@eva.com"
                  className="w-full bg-transparent border-b border-black/[0.08] py-3 text-sm text-black outline-none focus:border-black transition-all placeholder:text-gray-300"
                />
                <Mail className="absolute right-0 top-3 text-gray-300" size={16} />
              </div>
            </div>

            <div className="group relative">
              <label className="text-[10px] font-black uppercase tracking-[0.3em] text-gray-400 block mb-2 group-focus-within:text-black transition-colors">
                安全密码 / PASSWORD
              </label>
              <div className="relative">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-transparent border-b border-black/[0.08] py-3 text-sm text-black outline-none focus:border-black transition-all placeholder:text-gray-300"
                />
                <Lock className="absolute right-0 top-3 text-gray-300" size={16} />
              </div>
            </div>

            <div className="pt-6">
              <button
                type="submit"
                disabled={loading}
                className="w-full py-5 bg-black text-white rounded-full font-bold text-[11px] uppercase tracking-[0.4em] hover:bg-[#BF953F] transition-all duration-700 shadow-2xl flex items-center justify-center gap-3 group disabled:opacity-50"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <>开启体验 <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" /></>}
              </button>
            </div>
          </form>

          <div className="mt-12 text-center pt-8 border-t border-black/[0.03]">
            <div className="flex items-center justify-center gap-2 mb-6 text-[9px] font-bold text-gray-300 uppercase tracking-widest">
               <ShieldCheck size={12} /> 您的隐私已由 EVA 加密
            </div>
            <p className="text-xs text-gray-400">
              已有身份？ <Link href="/login" className="text-black font-bold border-b border-black pb-0.5 ml-2 hover:opacity-50 transition-opacity">立即登录</Link>
            </p>
          </div>
        </div>
      </motion.div>

      <div className="absolute bottom-10 text-[9px] font-black tracking-[0.8em] text-gray-300 uppercase z-20">
        The future is not waiting. EVA is building it.
      </div>
    </div>
  );
}
