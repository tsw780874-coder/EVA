"use client"
import { useEffect } from 'react';
import { useAuthStore } from '@/stores/authStore';

/**
 * 客户端 Auth 状态初始化器
 * 在应用挂载后调用 init() 检测真实登录状态，
 * 确保 SSR 首次渲染始终以未登录状态输出（避免 hydration 不匹配），
 * 挂载后再切换到真实状态。
 */
export default function AuthInit({ children }: { children: React.ReactNode }) {
  const init = useAuthStore((s) => s.init);

  useEffect(() => {
    init();
  }, [init]);

  return <>{children}</>;
}
