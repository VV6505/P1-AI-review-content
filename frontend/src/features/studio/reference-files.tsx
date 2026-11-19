"use client";
import Image from "next/image";
import { useEffect, useState } from "react";
import { FileText, ImageIcon, X } from "lucide-react";
import type { ReferenceFile } from "./model";
import { readReference } from "./references";
import { usePreferences } from "./preferences";
import { Modal } from "./common";
import { useAuth } from "@/features/auth/provider";

export function ReferenceFiles({ files, remove }: { files: ReferenceFile[]; remove?: (id: string) => void }) {
  const { t } = usePreferences();
  const [selected, setSelected] = useState<ReferenceFile | null>(null);
  if (!files.length) return null;
  return <><div className="reference-chips">{files.map(file => <div className="reference-chip" key={file.id}><button type="button" onClick={() => setSelected(file)} title={file.name}>{file.type.startsWith("image/") ? <ImageIcon size={15} /> : <FileText size={15} />}<span>{file.name}</span></button>{remove && <button type="button" className="remove-reference" aria-label={`${t("Gỡ", "Remove")} ${file.name}`} onClick={() => remove(file.id)}><X size={12} /></button>}</div>)}</div>{selected && <ReferencePreview file={selected} close={() => setSelected(null)} />}</>;
}
function ReferencePreview({ file, close }: { file: ReferenceFile; close: () => void }) {
  const { account } = useAuth();
  const { t, number } = usePreferences();
  const [url, setUrl] = useState(""); const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true; let objectUrl = "";
    readReference(file.id, account?.id).then(blob => {
      if (!alive) return;
      objectUrl = URL.createObjectURL(blob); setUrl(objectUrl);
    }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [file.id, account?.id]);
  return <Modal title={file.name} close={close}><p className="field-hint">{t("Tệp tham khảo", "Reference file")} · {number(Math.ceil(file.size / 1024))} KB</p>{error ? <p role="alert" className="studio-error">{t("Không đọc được tệp trên trình duyệt này. Hãy đính kèm lại.", "This file is unavailable in this browser. Please attach it again.")}</p> : !url ? <p role="status">{t("Đang mở tệp…", "Opening file…")}</p> : <>{file.type.startsWith("image/") ? <div className="reference-image-preview"><Image src={url} alt={file.name} fill unoptimized sizes="600px" style={{ objectFit: "contain" }} /></div> : file.type === "application/pdf" ? <iframe src={url} title={file.name} className="reference-document-preview" /> : <div className="reference-document-placeholder"><FileText size={35} /><p>{file.name}</p></div>}<div className="dialog-actions"><a href={url} download={file.name} className="secondary-button">{t("Tải tệp tham khảo", "Download reference")}</a></div></>}</Modal>;
}
