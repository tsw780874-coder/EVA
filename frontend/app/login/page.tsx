"use client"
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Mail, Lock, ArrowRight, Home, Loader2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { Suspense } from 'react';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get('redirect') || '/assistant';
  const login = useAuthStore((s) => s.login);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
      router.push(redirect);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请检查账户信息');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center overflow-hidden bg-[#0a0a0a]">

      {/* --- 底片层：你的雅马哈钢琴图片 --- */}
      <div className="absolute inset-0 z-0">
        <motion.img
          initial={{ scale: 1.1, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 2, ease: "easeOut" }}
          // 注意：请确保图片已放在项目的 public 文件夹下
          src="/piano.jpg"
          alt="Yamaha Piano Background"
          className="w-full h-full object-cover"
        />
        {/* 黑色渐变遮罩：确保登录框区域的文字清晰，同时保留钢琴边缘的质感 */}
        <div className="absolute inset-0 bg-gradient-to-tr from-black/80 via-black/20 to-transparent" />
        {/* 轻微的磨砂感，增加高级感 */}
        <div className="absolute inset-0 backdrop-blur-[1px]" />
      </div>

      {/* --- 装饰性边框线 (更暗的色调) --- */}
      <div className="absolute inset-0 pointer-events-none z-10">
        <div className="absolute top-0 left-1/4 w-[1px] h-full bg-white/[0.03]" />
        <div className="absolute top-1/2 left-0 w-full h-[1px] bg-white/[0.03]" />
        <div className="absolute top-12 left-12 text-[9px] font-mono tracking-tighter text-zinc-600">EVA_SYSTEM_SESSION_v1.0</div>
      </div>

      {/* --- 返回首页 --- */}
      <Link href="/" className="absolute top-12 right-12 z-30 flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white transition-colors">
        <Home size={12} /> 返回首页
      </Link>

      {/* --- 登录卡片：黑金/深灰色调 (Pristine Dark Glass) --- */}
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.2, delay: 0.5 }}
        className="relative z-20 w-full max-w-[440px] mx-6"
      >
        <div className="bg-black/60 backdrop-blur-[50px] border border-white/10 rounded-[32px] p-10 lg:p-14 shadow-2xl">

          <div className="text-center mb-10">
            <div className="inline-block w-10 h-10 bg-white rounded-xl mb-6 flex items-center justify-center">
              <span className="text-black font-black text-xl italic">E</span>
            </div>
            <h1 className="text-3xl font-serif italic text-white tracking-tight mb-3">登 录</h1>
            <p className="text-[9px] font-bold text-zinc-500 uppercase tracking-[0.5em]">Atelier of Inspiration</p>
          </div>

          <form className="space-y-8" onSubmit={handleSubmit}>
            {error && <p className="text-red-400 text-xs text-center">{error}</p>}

            <div className="group relative">
              <label className="text-[9px] font-bold uppercase tracking-[0.2em] text-zinc-500 block mb-1 group-focus-within:text-white transition-colors">
                账号 / ACCOUNT
              </label>
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="email@example.com"
                  className="w-full bg-transparent border-b border-white/10 py-3 text-sm text-zinc-200 outline-none focus:border-white transition-all placeholder:text-zinc-800"
                />
                <Mail className="absolute right-0 top-3 text-zinc-700" size={14} />
              </div>
            </div>

            <div className="group relative">
              <div className="flex justify-between items-center mb-1">
                <label className="text-[9px] font-bold uppercase tracking-[0.2em] text-zinc-500 group-focus-within:text-white transition-colors">
                  密码 / PASSWORD
                </label>
              </div>
              <div className="relative">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-transparent border-b border-white/10 py-3 text-sm text-zinc-200 outline-none focus:border-white transition-all placeholder:text-zinc-800"
                />
                <Lock className="absolute right-0 top-3 text-zinc-700" size={14} />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-4 py-4 bg-white text-black rounded-full font-bold text-[10px] uppercase tracking-[0.3em] hover:bg-zinc-200 transition-all duration-300 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <>开启空间 <ArrowRight size={14} /></>}
            </button>
          </form>

          <div className="mt-10 text-center pt-6 border-t border-white/5">
            <p className="text-[11px] text-zinc-500">
              还没有加入？ <Link href="/register" className="text-white font-bold hover:underline ml-1">创建身份</Link>
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="bg-black h-screen" />}>
      <LoginForm />
    </Suspense>
  );
}