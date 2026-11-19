"use client";

import Link from "next/link";
import { usePreferences } from "@/features/studio/preferences";

export function Footer() {
  const { t } = usePreferences();
  return (
    <footer className="factory-footer workspace-footer">
      <span>© {new Date().getFullYear()} Reviewlab. All rights reserved.</span>
      <nav aria-label={t("Liên kết cuối trang", "Footer links")}>
        <a href="https://github.com/PotatoMine725/AI-review-FE" target="_blank" rel="noopener noreferrer">GitHub ↗</a>
        <a href="https://github.com/PotatoMine725/AI-review-BE/tree/dev/docs" target="_blank" rel="noopener noreferrer">{t("Tài liệu", "Documentation")} ↗</a>
        <Link href="/credits">{t("Ghi công / Credits", "Credits")}</Link>
      </nav>
    </footer>
  );
}
