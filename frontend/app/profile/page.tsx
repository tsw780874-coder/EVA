"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  User, Shield, CreditCard, Settings2, LogOut,
  ArrowUpRight, CheckCircle2, LayoutDashboard, Home, Edit3, X
} from 'lucide-react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/stores/authStore';

interface ProfileData {
  id: string;
  name: string;
  email: string;
  role: string;
  avatar_url: string | null;
  created_at: string;
  total_savings: number;
  favorites_count: number;
  reports_count: number;
  purchase_count: number;
  preferred_model: string | null;
}

const fadeInUp = {
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] }
};

const fadeInUpDelayed = (delay: number) => ({
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number], delay }
});

export default function ProfilePage() {
  const router = useRouter();
  const { logout } = useAuthStore();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [saveMsg, setSaveMsg] = useState('');

  useEffect(() => {
    api<ProfileData>("/api/v1/profile")
      .then(d => { setProfile(d); setEditName(d.name); })
      .catch(() => {});
  }, []);

  const handleSaveProfile = async () => {
    try {
      const updated = await api<ProfileData>("/api/v1/profile", {
        method: "PUT",
        body: JSON.stringify({ name: editName }),
      });
      setProfile(prev => prev ? { ...prev, name: updated.name } : prev);
      setEditing(false);
      setSaveMsg('个人资料已更新');
      setTimeout(() => setSaveMsg(''), 2000);
    } catch {
      setSaveMsg('更新失败');
      setTimeout(() => setSaveMsg(''), 2000);
    }
  };

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  const createdDate = profile?.created_at
    ? new Date(profile.created_at).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
    : '...';

  return (
    <div className="min-h-screen bg-[#FDFDFD] text-[#1d1d1f] relative overflow-hidden selection:bg-indigo-100">

      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-[20%] w-[1px] h-full bg-black/[0.03]" />
        <div className="absolute top-0 left-[80%] w-[1px] h-full bg-black/[0.03]" />
        <div className="absolute top-[30%] left-0 w-full h-[1px] bg-black/[0.03]" />
        <div className="absolute top-[-10%] right-[-5%] w-[40%] h-[40%] bg-blue-50/50 blur-[120px] rounded-full" />
      </div>

      <div className="relative z-10 max-w-7xl mx-auto pt-32 pb-20 px-8 lg:px-12">

        <Link href="/" className="fixed top-10 left-10 z-50 flex items-center gap-2 text-[11px] font-bold tracking-widest text-gray-500 hover:text-black transition-colors">
          <Home size={14} /> 返回首页
        </Link>

        <header className="mb-20 flex flex-col lg:flex-row items-end justify-between gap-10">
          <motion.div {...fadeInUp}>
            <div className="flex items-center gap-4 mb-4 text-[11px] font-black tracking-[0.4em] text-indigo-500 uppercase">
              <span className="w-8 h-[1px] bg-indigo-500" /> 个人中心
            </div>
            <h1 className="text-7xl lg:text-9xl font-serif italic tracking-tighter">
              The <span className="font-sans not-italic font-black text-black">MEMBER.</span>
            </h1>
          </motion.div>
          <motion.div {...fadeInUpDelayed(0.2)} className="text-right">
            <p className="text-[11px] font-black tracking-widest text-gray-400 mb-2">加入于 {createdDate}</p>
            <p className="text-gray-400 text-sm">UID: {profile?.id?.slice(0, 8) || "..."}</p>
          </motion.div>
        </header>

        {saveMsg && (
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center mb-6 text-sm text-green-600 font-bold">{saveMsg}</motion.p>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">

          {/* 左侧：用户卡片 */}
          <motion.div {...fadeInUp} className="lg:col-span-4 relative group">
            <div className="relative bg-white/40 backdrop-blur-3xl border border-white shadow-2xl rounded-[40px] p-10 overflow-hidden">
              <div className="absolute -top-20 -right-20 w-40 h-40 bg-indigo-100 blur-[60px] opacity-50" />

              <div className="relative z-10 flex flex-col items-center text-center">
                <div className="w-32 h-32 rounded-full border border-black/5 p-2 mb-6">
                  <div className="w-full h-full rounded-full bg-gradient-to-tr from-gray-100 to-gray-300 flex items-center justify-center overflow-hidden">
                    {profile?.avatar_url ? (
                      <img src={profile.avatar_url} alt={profile.name} className="w-full h-full object-cover" />
                    ) : (
                      <User size={60} className="text-white opacity-50" />
                    )}
                  </div>
                </div>
                <h2 className="text-2xl font-bold mb-1">{profile?.name || "..."}</h2>
                <p className="text-xs font-bold text-indigo-500 uppercase tracking-widest mb-2">{profile?.role === "admin" ? "系统管理员" : "注册会员"}</p>
                <p className="text-[11px] text-gray-500 mb-8">{profile?.email || "..."}</p>

                <div className="w-full space-y-4 text-left">
                  <div className="flex justify-between items-center p-4 rounded-2xl bg-white/50 border border-black/[0.02]">
                    <span className="text-[11px] font-bold tracking-widest text-gray-600">累计节省</span>
                    <span className="text-lg font-black italic">¥{(profile?.total_savings ?? 0).toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between items-center p-4 rounded-2xl bg-white/50 border border-black/[0.02]">
                    <span className="text-[11px] font-bold tracking-widest text-gray-600">收藏商品</span>
                    <span className="text-lg font-black italic">{profile?.purchase_count ?? 0}</span>
                  </div>
                  <div className="flex justify-between items-center p-4 rounded-2xl bg-white/50 border border-black/[0.02]">
                    <span className="text-[11px] font-bold tracking-widest text-gray-600">分析报告</span>
                    <span className="text-lg font-black italic">{profile?.reports_count ?? 0}</span>
                  </div>
                </div>

                {editing ? (
                  <div className="w-full mt-8 space-y-4">
                    <input
                      type="text"
                      value={editName}
                      onChange={e => setEditName(e.target.value)}
                      placeholder="输入新昵称"
                      className="w-full px-4 py-3 bg-white border border-black/10 rounded-xl text-sm outline-none focus:border-black"
                    />
                    <div className="flex gap-3">
                      <button onClick={handleSaveProfile} className="flex-1 py-3 bg-black text-white rounded-full font-bold text-[11px] tracking-widest hover:opacity-80 transition-opacity">
                        保存
                      </button>
                      <button onClick={() => setEditing(false)} className="px-4 py-3 bg-gray-100 rounded-full text-gray-600 hover:bg-gray-200 transition-colors">
                        <X size={16} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => setEditing(true)}
                    className="w-full mt-10 py-4 bg-black text-white rounded-full font-bold text-[11px] tracking-widest hover:scale-105 transition-transform flex items-center justify-center gap-2"
                  >
                    编辑个人资料 <Edit3 size={14} />
                  </button>
                )}
              </div>
            </div>
          </motion.div>

          {/* 右侧：设置与管理列表 */}
          <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-6">

            {/* 角色状态面板 */}
            <motion.div {...fadeInUpDelayed(0.1)} className="md:col-span-2 bg-white/60 backdrop-blur-xl border border-black/[0.03] rounded-[40px] p-8 flex flex-col md:flex-row justify-between items-center gap-6">
              <div className="flex items-center gap-6">
                <div className={`w-16 h-16 rounded-3xl flex items-center justify-center text-white shadow-xl ${profile?.role === 'admin' ? 'bg-indigo-600 shadow-indigo-100' : 'bg-gray-800 shadow-gray-200'}`}>
                  <Shield size={28} />
                </div>
                <div>
                  <h3 className="text-lg font-bold">{profile?.role === 'admin' ? '系统管理员' : '注册会员'}</h3>
                  <p className="text-sm text-gray-500">注册时间：{createdDate}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 px-6 py-2 rounded-full bg-green-50 text-green-600 text-[11px] font-bold tracking-widest border border-green-100">
                <CheckCircle2 size={12} /> 已认证
              </div>
            </motion.div>

            {/* 设置项 */}
            {[
              ...(profile?.role === 'admin' ? [{ icon: <LayoutDashboard size={20} />, title: "管理员后台", desc: "系统架构师指挥塔", link: "/admin" }] : []),
              { icon: <Settings2 size={20} />, title: "模型与安全", desc: "AI 模型选择与密码管理", link: "/settings" },
              { icon: <CreditCard size={20} />, title: "我的收藏", desc: "商品收藏与比价追踪", link: "/favorites" },
              { icon: <LogOut size={20} />, title: "退出登录", desc: "清除本地缓存并安全登出", danger: true, action: handleLogout },
            ].map((item: any, i: number) => (
              <motion.div
                key={i}
                {...fadeInUpDelayed(0.2 + i * 0.1)}
                onClick={() => item.link ? router.push(item.link) : item.action?.()}
                className="group p-8 bg-white border border-black/[0.03] rounded-[40px] hover:shadow-2xl hover:shadow-black/5 transition-all cursor-pointer flex flex-col justify-between aspect-square"
              >
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-colors ${item.danger ? 'bg-red-50 text-red-400' : 'bg-gray-50 text-black group-hover:bg-black group-hover:text-white'}`}>
                  {item.icon}
                </div>
                <div>
                  <h4 className="text-xl font-serif italic mb-2">{item.title}</h4>
                  <p className="text-xs text-gray-600">{item.desc}</p>
                </div>
                <div className="self-end overflow-hidden">
                  <ArrowUpRight className="translate-y-8 group-hover:translate-y-0 transition-transform text-indigo-500" />
                </div>
              </motion.div>
            ))}

          </div>
        </div>

        <motion.div {...fadeInUpDelayed(0.6)} className="mt-32 text-center">
          <div className="inline-block px-10 py-4 bg-white/40 backdrop-blur-md border border-black/[0.05] rounded-full">
            <p className="text-[11px] font-black tracking-[0.5em] text-gray-500 uppercase">
              永远热忱，浪漫至死不渝
            </p>
          </div>
        </motion.div>

      </div>
    </div>
  );
}
