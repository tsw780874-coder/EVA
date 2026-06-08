"use client"
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuthStore } from "@/stores/authStore";
import { onAuthFailureHandler } from "@/lib/api";

interface Props {
  children: React.ReactNode;
  requireAdmin?: boolean;
}

export default function AuthGuard({ children, requireAdmin = false }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, isAuthenticated, isLoading, init, fetchUser } = useAuthStore();

  useEffect(() => {
    onAuthFailureHandler(() => {
      useAuthStore.getState().logout();
      router.push("/login");
    });
  }, [router]);

  useEffect(() => {
    if (isLoading) {
      init();
    }
  }, []);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push(`/login?redirect=${encodeURIComponent(pathname)}`);
    }
  }, [isLoading, isAuthenticated, pathname, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="w-8 h-8 border-2 border-black border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  if (requireAdmin && user?.role !== "admin") {
    router.push("/");
    return null;
  }

  return <>{children}</>;
}
