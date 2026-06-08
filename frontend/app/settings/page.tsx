"use client"
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Cpu, Zap, Home, Wifi, WifiOff, AlertTriangle } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';

interface ProfileData {
  id: string;
  email: string;
  name: string;
  role: string;
  avatar_url: string | null;
  created_at: string;
}

interface ModelInfo {
  name: string;
  provider: string;
  desc: string;
  status: string;
  tier: string;
  key: string;
  total_quota: number;
  used_tokens: number;
  remaining_tokens: number;
  latency_ms: number | null;
}

const fadeInUp = {
  initial: { opacity: 0, y: 30 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] }
};

const fadeInUpDelayed = (delay: number) => ({
  initial: { opacity: 0, y: 30 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] as [number, number, number, number], delay }
});

export default function SettingsPage() {
  const [activeModel, setActiveModel] = useState('');
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ current: '', newPw: '' });
  const [saveMsg, setSaveMsg] = useState('');

  useEffect(() => {
    api<ProfileData>("/api/v1/profile").then(setProfile).catch(() => {});
    api<{ models: ModelInfo[] }>("/api/v1/models")
      .then(d => {
        const active = d.models.filter(m => m.status === 'available' || m.status === 'unverified');
        const list = active.length > 0 ? active : d.models;
        setModels(list);
        if (list.length > 0) setActiveModel(list[0].key);
        setModelsLoading(false);
      })
      .catch(() => {
        setModelsError(true);
        setModelsLoading(false);
      });
  }, []);

  const handleModelSelect = async (modelKey: string) => {
    setActiveModel(modelKey);
    const model = models.find(m => m.key === modelKey);
    await api("/api/v1/profile", {
      method: "PUT",
      body: JSON.stringify({ preferred_model: model?.name }),
    }).catch(() => {});
    setSaveMsg('模型偏好已保存');
    setTimeout(() => setSaveMsg(''), 2000);
  };

  const handlePasswordUpdate = async () => {
    if (!passwordForm.current || !passwordForm.newPw) return;
    try {
      await api("/api/v1/profile/password", {
        method: "PUT",
        body: JSON.stringify({ current_password: passwordForm.current, new_password: passwordForm.newPw }),
      });
      setPasswordForm({ current: '', newPw: '' });
      setSaveMsg('密码已更新');
    } catch (err) {
      setSaveMsg('密码修改失败: ' + (err instanceof Error ? err.message : ''));
    }
    setTimeout(() => setSaveMsg(''), 3000);
  };

  const activeModelData = models.find(m => m.key === activeModel);
  const isAdmin = profile?.role === 'admin';

  return (
    <div className="min-h-screen bg-[#FDFDFD] text-[#1d1d1f] font-sans selection:bg-indigo-50">

      {/* 背景装饰 */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-0 left-24 w-[1px] h-full bg-black/[0.03]" />
        <div className="absolute top-0 right-24 w-[1px] h-full bg-black/[0.03]" />
        <div className="absolute top-1/2 left-0 w-full h-[1px] bg-black/[0.03]" />
        <div className="absolute top-24 left-32 text-[10px] font-mono tracking-widest text-gray-400">EVA_系统工坊_V1.0</div>
      </div>

      {/* 左侧导航 */}
      <nav className="fixed left-24 top-1/2 -translate-y-1/2 hidden xl:flex flex-col gap-8 z-20">
        {['智能中枢', '安全设置'].map((item, i) => (
          <a key={item} href={`#${item}`} className="group flex items-center gap-4 text-left">
            <span className="text-[11px] font-black text-gray-400 group-hover:text-black transition-colors tracking-[0.3em]">0{i+1}</span>
            <span className="text-[11px] font-bold text-gray-500 group-hover:text-black transition-colors tracking-[0.2em]">{item}</span>
          </a>
        ))}
      </nav>

      <main className="relative z-10 max-w-5xl mx-auto pt-40 pb-40 px-10">

        <Link href="/" className="fixed top-10 left-10 z-50 flex items-center gap-2 text-[11px] font-bold tracking-widest text-gray-500 hover:text-black transition-colors">
          <Home size={14} /> 返回首页
        </Link>

        {/* 头部 */}
        <header className="mb-32">
          <motion.div {...fadeInUp} className="flex items-center gap-4 mb-6 text-[#BF953F]">
             <span className="w-12 h-[1px] bg-current" />
             <span className="text-[11px] font-black tracking-[0.5em]">偏好设置</span>
          </motion.div>
          <motion.h1 {...fadeInUpDelayed(0.2)} className="text-7xl lg:text-9xl font-serif italic tracking-tighter leading-none">
            The <span className="font-sans not-italic font-black text-black">工坊.</span>
          </motion.h1>
          {profile && (
            <motion.p {...fadeInUpDelayed(0.3)} className="mt-4 text-sm text-gray-600">
              当前账户: {profile.email} · {profile.role === "admin" ? "系统管理员" : "注册会员"}
            </motion.p>
          )}
          {saveMsg && (
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-2 text-sm text-green-600 font-bold">{saveMsg}</motion.p>
          )}
        </header>

        {/* 智能中枢：模型选择 */}
        <section id="智能中枢" className="mb-40">
          <motion.div {...fadeInUp} className="flex justify-between items-end mb-16">
            <h2 className="text-4xl font-serif italic">智能中枢</h2>
            <span className="text-[11px] font-bold text-gray-500 tracking-widest">模型选择</span>
          </motion.div>

          {modelsLoading && (
            <div className="text-center py-16">
              <div className="w-8 h-8 border-2 border-black border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-sm text-gray-500">正在加载模型列表...</p>
            </div>
          )}

          {modelsError && (
            <div className="text-center py-16 bg-red-50/50 rounded-[40px] border border-red-100">
              <AlertTriangle size={32} className="mx-auto mb-4 text-red-400" />
              <p className="text-sm text-red-600 font-bold">无法连接后端服务</p>
              <p className="text-xs text-red-400 mt-1">请确认后端已启动并刷新页面重试</p>
            </div>
          )}

          {!modelsLoading && !modelsError && models.length === 0 && (
            <div className="text-center py-16 bg-gray-50 rounded-[40px]">
              <Cpu size={32} className="mx-auto mb-4 text-gray-300" />
              <p className="text-sm text-gray-500">暂无可用的 AI 模型</p>
              <p className="text-xs text-gray-400 mt-1">请联系管理员配置模型 API Key</p>
            </div>
          )}

          {!modelsLoading && !modelsError && models.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {models.map((model) => (
                <motion.div
                  key={model.key}
                  whileHover={{ y: -5 }}
                  onClick={() => handleModelSelect(model.key)}
                  className={`p-8 rounded-[32px] border transition-all duration-500 cursor-pointer ${
                    activeModel === model.key
                    ? 'bg-black text-white border-black shadow-2xl shadow-black/20'
                    : 'bg-white border-black/[0.05] hover:border-black/20'
                  }`}
                >
                  {/* 头部：图标 + 状态 */}
                  <div className="flex justify-between items-start mb-4">
                    <div className={`p-3 rounded-2xl ${activeModel === model.key ? 'bg-white/10' : 'bg-gray-50'}`}>
                      <Cpu size={20} />
                    </div>
                    <div className="flex items-center gap-2">
                      {/* 验证状态 */}
                      <span className={`flex items-center gap-1 px-2 py-1 rounded-full text-[9px] font-bold ${
                        model.status === 'available' ? 'bg-green-100 text-green-600' :
                        model.status === 'unverified' ? 'bg-yellow-100 text-yellow-600' : 'bg-gray-100 text-gray-500'
                      }`}>
                        {model.status === 'available' ? <Wifi size={10} /> : model.status === 'unverified' ? <AlertTriangle size={10} /> : <WifiOff size={10} />}
                        {model.status === 'available' ? '已验证' : model.status === 'unverified' ? '待验证' : '不可用'}
                      </span>
                      {/* 层级标签 */}
                      {model.tier === 'admin' && (
                        <span className="px-2 py-1 rounded-full text-[9px] font-bold bg-purple-100 text-purple-600">VIP</span>
                      )}
                      {activeModel === model.key && <div className="w-2 h-2 rounded-full bg-indigo-400" />}
                    </div>
                  </div>

                  {/* 模型名称 */}
                  <div className="mb-4">
                    <h3 className="text-xl font-serif italic mb-1">{model.name}</h3>
                    <p className={`text-xs ${activeModel === model.key ? 'text-gray-400' : 'text-gray-600'}`}>
                      {model.provider} · {model.desc}
                    </p>
                  </div>

                  {/* 核心指标：仅展示后端测量的真实数据 */}
                  <div className={`text-xs space-y-2 pt-4 border-t ${activeModel === model.key ? 'border-white/10' : 'border-black/[0.03]'}`}>
                    {/* 延迟：来自 verify_model 的实际测量 */}
                    <div className="flex justify-between">
                      <span className="opacity-60">实测延迟</span>
                      <span className={`font-bold ${model.latency_ms ? '' : 'italic opacity-50'}`}>
                        {model.latency_ms ? `${model.latency_ms}ms` : '未测量'}
                      </span>
                    </div>

                    {/* Token 配额使用 */}
                    <div className="flex justify-between">
                      <span className="opacity-60">已用 / 总额</span>
                      <span className="font-bold">
                        <span className={model.remaining_tokens <= 0 ? 'text-red-500' : ''}>
                          {model.used_tokens.toLocaleString()}
                        </span>
                        <span className="opacity-30"> / {model.total_quota.toLocaleString()}</span>
                      </span>
                    </div>

                    {/* 进度条：已用量相对配额的占比 */}
                    <div className="h-1 w-full bg-gray-200 rounded-full overflow-hidden mt-1">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          model.remaining_tokens <= 0 ? 'bg-red-500' :
                          model.used_tokens > model.total_quota * 0.8 ? 'bg-yellow-500' : 'bg-green-500'
                        }`}
                        style={{ width: `${Math.min((model.used_tokens / model.total_quota) * 100, 100)}%` }}
                      />
                    </div>

                    {/* 状态摘要 */}
                    <div className="flex justify-between pt-1">
                      <span className="opacity-60">
                        {model.status === 'available' ? '就绪' : model.status === 'unverified' ? '点击验证' : '暂不可用'}
                      </span>
                      <span className={`font-bold ${model.remaining_tokens > 0 ? 'text-green-600' : 'text-red-500'}`}>
                        剩余 {model.remaining_tokens.toLocaleString()}
                      </span>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </section>

        {/* 安全设置：密码与验证 */}
        <section id="安全设置" className="mb-40">
          <motion.div {...fadeInUp} className="flex justify-between items-end mb-16">
            <h2 className="text-4xl font-serif italic">安全堡垒</h2>
            <span className="text-[11px] font-bold text-gray-500 tracking-widest">账户安全</span>
          </motion.div>

          <div className="bg-white/40 backdrop-blur-3xl border border-black/[0.03] rounded-[40px] p-12 space-y-12">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
              <div className="space-y-8">
                <div className="group">
                  <label className="text-[11px] font-black tracking-widest text-gray-500 block mb-2 group-focus-within:text-black">当前密码</label>
                  <input
                    type="password"
                    placeholder="••••••••"
                    value={passwordForm.current}
                    onChange={(e) => setPasswordForm(prev => ({ ...prev, current: e.target.value }))}
                    className="w-full bg-transparent border-b border-black/10 py-3 text-sm outline-none focus:border-black transition-colors"
                  />
                </div>
                <div className="group">
                  <label className="text-[11px] font-black tracking-widest text-gray-500 block mb-2 group-focus-within:text-black">新密码</label>
                  <input
                    type="password"
                    placeholder="••••••••"
                    value={passwordForm.newPw}
                    onChange={(e) => setPasswordForm(prev => ({ ...prev, newPw: e.target.value }))}
                    className="w-full bg-transparent border-b border-black/10 py-3 text-sm outline-none focus:border-black transition-colors"
                  />
                </div>
              </div>
              <div className="flex flex-col justify-end">
                <p className="text-xs text-gray-600 mb-6 leading-relaxed">
                  密码必须包含至少 8 个字符，建议结合字母、数字与特殊符号。
                </p>
                <button
                  onClick={handlePasswordUpdate}
                  className="w-fit px-10 py-4 bg-black text-white rounded-full font-bold text-[11px] tracking-[0.2em] shadow-xl shadow-black/10 hover:scale-105 transition-transform"
                >
                  更新密码
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* 底部 */}
        <footer className="text-center">
          <p className="text-[11px] font-black tracking-[0.5em] text-gray-400">
             永远好奇，永远热忱，永远创造
          </p>
        </footer>

      </main>
    </div>
  );
}
