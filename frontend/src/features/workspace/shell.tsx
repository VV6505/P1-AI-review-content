"use client";
import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Header } from "./header";
import { StorageNotice } from "@/features/studio/common";
import { usePreferences } from "@/features/studio/preferences";
import { StudioProvider } from "@/features/studio/provider";
import { WorkspaceProvider } from "@/features/content-factory/workspace-provider";
import { useAuth } from "@/features/auth/provider";
export function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { account, ready } = useAuth();
  const { t } = usePreferences();
  const authPage = pathname === "/login" || pathname === "/signup";
  const publicPage = ["/", "/credits", "/price", "/about"].includes(pathname);
  useEffect(() => {
    if (ready && !account && !authPage && !publicPage) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [account, ready, authPage, publicPage, pathname, router]);
  if (publicPage) return <div className="studio-app public-app">{children}</div>;
  if (authPage) return <div className="studio-app auth-route">{children}</div>;
  if (!ready || !account) return <div className="studio-app auth-app"><p role="status" className="auth-loading">{t("Đang mở không gian làm việc…", "Opening your workspace…")}</p></div>;
  if (pathname.startsWith("/admin") && account.role !== "admin") return <div className="studio-app auth-app"><main className="auth-card"><h1>{t("Dành cho Admin", "Admin workspace")}</h1><p>{t("Tài khoản mẫu này là Creator.", "This demo account is a Creator.")}</p><Link className="secondary-button" href="/creator/create">{t("Về dự án", "Back to workspace")}</Link></main></div>;
  return <StudioProvider key={account.id}><WorkspaceProvider storageScope={account.id}><WorkspaceContent>{children}</WorkspaceContent></WorkspaceProvider></StudioProvider>;
}

function WorkspaceContent({ children }: { children: ReactNode }) {
  const creator = usePathname().startsWith("/creator");
  const { sidebarCollapsed } = usePreferences();
  return <div className={`studio-app ${creator ? "creator-app" : "admin-app"} ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}><Header /><main id="main-content" className="studio-main" tabIndex={-1}><StorageNotice />{children}</main></div>;
}
