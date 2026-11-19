"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { usePreferences } from "@/features/studio/preferences";
import { LandingFooter, LandingSettings } from "./landing-chrome";
import "./public.css";

export function PublicLayout({ children }: { children: ReactNode }) {
  const { t } = usePreferences();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setMenuOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [menuOpen]);

  return <>
    <a className="public-skip" href="#main-content">{t("Đến nội dung chính", "Skip to content")}</a>
    <header className={`public-header${pathname === "/" ? " is-overlay" : ""}`}>
      <div className="public-container public-header-inner">
        <Link className="public-brand" href="/" onClick={() => setMenuOpen(false)} aria-label={t("Reviewlab — Trang chủ", "Reviewlab — Home")}>reviewlab<span>.</span></Link>
        <nav className="public-nav" aria-label={t("Điều hướng chính", "Main navigation")}>
          <Link href="/" aria-current={pathname === "/" ? "page" : undefined}>{t("Trang chủ", "Home")}</Link>
          <Link href="/creator/create">{t("Sáng tạo", "Create")}</Link>
          <Link href="/price" aria-current={pathname === "/price" ? "page" : undefined}>{t("Bảng giá", "Price")}</Link>
          <Link href="/about" aria-current={pathname === "/about" ? "page" : undefined}>{t("Giới thiệu", "About")}</Link>
        </nav>
        <div className="public-account">
          <LandingSettings />
          <Link className="public-login" href="/login" aria-current={pathname === "/login" ? "page" : undefined}>{t("Đăng nhập", "Sign in")}</Link>
          <Link className="primary-button nav-start" href="/signup">{t("Bắt đầu", "Get started")}<ArrowUpRight size={15} aria-hidden="true" /></Link>
          <button className="public-menu-toggle" type="button" aria-expanded={menuOpen} aria-controls="public-mobile-menu" aria-label={t(menuOpen ? "Đóng menu" : "Mở menu", menuOpen ? "Close menu" : "Open menu")} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={21} /> : <Menu size={21} />}</button>
        </div>
      </div>
      {menuOpen && <nav id="public-mobile-menu" className="public-mobile-menu public-container" aria-label={t("Điều hướng di động", "Mobile navigation")} onClick={() => setMenuOpen(false)}>
        <Link href="/" aria-current={pathname === "/" ? "page" : undefined}>{t("Trang chủ", "Home")}</Link>
        <Link href="/creator/create">{t("Sáng tạo", "Create")}</Link>
        <Link href="/price" aria-current={pathname === "/price" ? "page" : undefined}>{t("Bảng giá", "Price")}</Link>
        <Link href="/about" aria-current={pathname === "/about" ? "page" : undefined}>{t("Giới thiệu", "About")}</Link>
        <Link href="/login">{t("Đăng nhập", "Sign in")}</Link>
        <Link href="/signup" className="primary-button">{t("Bắt đầu sáng tạo", "Start creating")}<ArrowUpRight size={16} aria-hidden="true" /></Link>
      </nav>}
    </header>
    {children}
    <LandingFooter />
  </>;
}
