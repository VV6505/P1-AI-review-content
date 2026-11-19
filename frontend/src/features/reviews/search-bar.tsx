"use client";

import { LoaderCircle, Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function SearchBar({ value, onChange, loading }: { value: string; onChange: (value: string) => void; loading: boolean }) {
  return (
    <div className="review-search">
      <label htmlFor="review-search">Tìm review video</label>
      <div className="search-input">
        <Search size={18} />
        <Input id="review-search" type="search" autoComplete="off" maxLength={200} value={value} placeholder="Tìm theo sản phẩm hoặc tiêu đề…" onChange={(event) => onChange(event.target.value)} aria-controls="review-results" />
        {value && <Button variant="ghost" size="icon-sm" aria-label="Xóa tìm kiếm" onClick={() => onChange("")}><X size={15} /></Button>}
      </div>
      {loading && <span className="search-status" role="status"><LoaderCircle size={15} className="spin" /> Đang tìm review…</span>}
    </div>
  );
}
