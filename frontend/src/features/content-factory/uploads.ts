import type { MockUpload } from "./model";
function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("reviewlab.uploads", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("files");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error("Không mở được bộ nhớ file trong trình duyệt."));
  });
}
export async function storeUpload(file: File): Promise<MockUpload> {
  if (!["application/pdf", "image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new Error("Chỉ nhận PDF, PNG, JPG hoặc WebP.");
  if (file.size === 0 || file.size > 5 * 1024 * 1024) throw new Error("File phải có dữ liệu và tối đa 5 MB.");
  const db = await database(), id = crypto.randomUUID();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("files", "readwrite"); tx.objectStore("files").put(file, id);
      tx.oncomplete = () => resolve(); tx.onerror = () => reject(new Error("Không lưu được file; kiểm tra dung lượng trình duyệt.")); tx.onabort = tx.onerror;
    });
  } finally { db.close(); }
  return { id, name: file.name, type: file.type, size: file.size };
}
export async function openUpload(upload: MockUpload): Promise<void> {
  const db = await database();
  try {
    const file = await new Promise<Blob>((resolve, reject) => {
      const request = db.transaction("files").objectStore("files").get(upload.id);
      request.onsuccess = () => request.result ? resolve(request.result) : reject(new Error("File không còn trong bộ nhớ trình duyệt. Hãy chọn lại."));
      request.onerror = () => reject(new Error("Không đọc được file."));
    });
    const url = URL.createObjectURL(file), link = document.createElement("a");
    link.href = url; link.download = upload.name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
  } finally { db.close(); }
}
