"use client";

import Link from "next/link";
import { Menu } from "@base-ui/react/menu";
import { ArrowUpRight, Check } from "lucide-react";
import { usePreferences } from "@/features/studio/preferences";

export function LandingSettings() {
  const { t, language, theme, setLanguage, setTheme } = usePreferences();
  return <Menu.Root modal={false}>
    <Menu.Trigger className="public-settings-trigger">{t("Cài đặt", "Settings")}</Menu.Trigger>
    <Menu.Portal>
      <Menu.Positioner align="end" sideOffset={12} className="public-settings-positioner">
        <Menu.Popup className="public-settings-menu studio-dialog" aria-label={t("Cài đặt", "Settings")}>
          <Menu.Group>
            <Menu.GroupLabel className="public-settings-label">{t("Ngôn ngữ", "Language")}</Menu.GroupLabel>
            <Menu.RadioGroup value={language} onValueChange={value => setLanguage(value)}>
              <Menu.RadioItem className="public-settings-item" value="vi" lang="vi">Tiếng Việt<Menu.RadioItemIndicator><Check size={14} aria-hidden="true" /></Menu.RadioItemIndicator></Menu.RadioItem>
              <Menu.RadioItem className="public-settings-item" value="en" lang="en">English<Menu.RadioItemIndicator><Check size={14} aria-hidden="true" /></Menu.RadioItemIndicator></Menu.RadioItem>
            </Menu.RadioGroup>
          </Menu.Group>
          <Menu.Separator className="public-settings-separator" />
          <Menu.Group>
            <Menu.GroupLabel className="public-settings-label">{t("Giao diện", "Appearance")}</Menu.GroupLabel>
            <Menu.RadioGroup value={theme} onValueChange={value => setTheme(value)}>
              <Menu.RadioItem className="public-settings-item" value="light">{t("Sáng", "Light")}<Menu.RadioItemIndicator><Check size={14} aria-hidden="true" /></Menu.RadioItemIndicator></Menu.RadioItem>
              <Menu.RadioItem className="public-settings-item" value="dark">{t("Tối", "Dark")}<Menu.RadioItemIndicator><Check size={14} aria-hidden="true" /></Menu.RadioItemIndicator></Menu.RadioItem>
            </Menu.RadioGroup>
          </Menu.Group>
        </Menu.Popup>
      </Menu.Positioner>
    </Menu.Portal>
  </Menu.Root>;
}

export function LandingFooter() {
  const { t } = usePreferences();
  return <footer className="landing-footer">
    <div className="public-container">
      <div className="landing-footer-columns">
        <div className="landing-footer-brand">
          <Link className="public-brand" href="/" aria-label={t("Reviewlab — Trang chủ", "Reviewlab — Home")}>reviewlab<span>.</span></Link>
          <p>{t("Hiểu sản phẩm. Tìm góc nhìn.\nKể câu chuyện của bạn.", "Know the product. Find your angle.\nTell your own story.")}</p>
        </div>
        <nav aria-label={t("Liên kết sản phẩm", "Product links")}>
          <h2>{t("Khám phá", "Explore")}</h2>
          <Link href="/">{t("Trang chủ", "Home")}</Link>
          <Link href="/creator/create">{t("Sáng tạo", "Create")}</Link>
          <Link href="/price">{t("Bảng giá", "Price")}</Link>
          <Link href="/about">{t("Giới thiệu", "About")}</Link>
        </nav>
        <nav aria-label={t("Tài nguyên", "Resources")}>
          <h2>{t("Kết nối", "Connect")}</h2>
          <a href="https://github.com/PotatoMine725/AI-review-FE" target="_blank" rel="noopener noreferrer">GitHub<ArrowUpRight size={12} aria-hidden="true" /></a>
          <a href="https://github.com/PotatoMine725/AI-review-FE/issues" target="_blank" rel="noopener noreferrer">{t("Gửi góp ý", "Share feedback")}<ArrowUpRight size={12} aria-hidden="true" /></a>
          <Link href="/credits">{t("Ghi công nguồn mở", "Open source credits")}</Link>
        </nav>
      </div>
      <div className="landing-footer-bottom">
        <span>© {new Date().getFullYear()} Reviewlab</span>
        <span className="footer-crawl">{t("Với sự hỗ trợ của", "Built with")} <a href="https://github.com/unclecode/crawl4ai" target="_blank" rel="noopener noreferrer">Crawl4AI<ArrowUpRight size={12} aria-hidden="true" /></a><span aria-hidden="true">·</span><a href="https://x.com/unclecode" target="_blank" rel="noopener noreferrer">UncleCode</a></span>
      </div>
    </div>
  </footer>;
}
