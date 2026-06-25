import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/", "/login", "/register"];

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 允许静态资源和 API 路由通过
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/favicon") ||
    pathname.match(/\.(svg|png|jpg|ico|css|js|mp4|webm|ogg|woff2|ttf|woff)$/)
  ) {
    return NextResponse.next();
  }

  // 公开页面直接放行
  if (PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.next();
  }

  // 已登录用户放行（通过 cookie 判断）
  const hasAuth = request.cookies.get("eva_auth")?.value;
  if (hasAuth === "1") {
    return NextResponse.next();
  }

  // 未登录 → 跳转登录页
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("redirect", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next|api|favicon|.*\\.svg|.*\\.png|.*\\.jpg|.*\\.ico|.*\\.css|.*\\.js|.*\\.mp4|.*\\.webm|.*\\.ogg|.*\\.woff2|.*\\.ttf|.*\\.woff).*)"],
};
