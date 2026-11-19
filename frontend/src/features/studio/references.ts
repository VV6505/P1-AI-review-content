import type { ReferenceFile } from "./model";

export const referenceAccept = ".png,.jpg,.jpeg,.webp,.gif,.pdf,.doc,.docx,.txt,.md";
const types: Record<string, string> = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp", gif: "image/gif", pdf: "application/pdf", doc: "application/msword", docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", txt: "text/plain", md: "text/markdown" };

function openDatabase(scope?: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const name = scope && !["demo", "admin-demo"].includes(scope) ? `reviewlab.studio.references.${scope}` : "reviewlab.studio.references";
    const request = indexedDB.open(name, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("files");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error("storage"));
    request.onblocked = () => reject(new Error("storage"));
  });
}
export async function saveReferences(files: File[], existingCount: number, scope?: string): Promise<ReferenceFile[]> {
  if (existingCount + files.length > 6) throw new Error("count");
  const references = files.map(file => {
    const type = types[file.name.split(".").at(-1)?.toLowerCase() ?? ""];
    if (!type) throw new Error("type");
    if (file.size <= 0 || file.size > 10 * 1024 * 1024) throw new Error("size");
    return { id: crypto.randomUUID(), name: file.name, type, size: file.size };
  });
  const database = await openDatabase(scope);
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = database.transaction("files", "readwrite");
      references.forEach((reference, index) => tx.objectStore("files").put(new Blob([files[index]], { type: reference.type }), reference.id));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(new Error("storage"));
      tx.onabort = () => reject(new Error("storage"));
    });
    return references;
  } finally { database.close(); }
}
export async function readReference(id: string, scope?: string): Promise<Blob> {
  const database = await openDatabase(scope);
  try {
    return await new Promise<Blob>((resolve, reject) => {
      const request = database.transaction("files", "readonly").objectStore("files").get(id);
      request.onsuccess = () => request.result instanceof Blob ? resolve(request.result) : reject(new Error("missing"));
      request.onerror = () => reject(new Error("storage"));
    });
  } finally { database.close(); }
}
