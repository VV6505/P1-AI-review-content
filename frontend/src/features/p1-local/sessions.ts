export type P1Session = {
  productId?: string;
  crawlJobId?: string;
  pkbVersion?: number;
  scriptRevision?: number;
  scriptApproved?: boolean;
  videoJobId?: string;
  url?: string;
  ownerContext?: string;
  preferences?: string;
  audience?: string;
  videoGoal?: string;
  loginRequired?: boolean;
  loginUrl?: string;
  loginReason?: string;
  authSessionId?: string;
  revisionFeedback?: string;
  manualLogin?: boolean;
  discoveryMode?: "public" | "authenticated";
  savedAt?: string;
};

export const P1_SESSION_KEY = "reviewlab.p1-local.session.v1";
export const P1_SESSION_HISTORY_KEY = "reviewlab.p1-local.sessions.v1";
export const P1_PENDING_OPEN_KEY = "reviewlab.p1-local.pending-open.v1";
export const P1_OPEN_EVENT = "reviewlab:p1-open";
export const P1_SESSIONS_EVENT = "reviewlab:p1-sessions";

export function readP1Sessions(storage: Pick<Storage, "getItem">): P1Session[] {
  try {
    const value = JSON.parse(storage.getItem(P1_SESSION_HISTORY_KEY) ?? "[]") as unknown;
    return Array.isArray(value)
      ? value.filter((item): item is P1Session => Boolean(item && typeof item === "object" && (item as P1Session).productId))
      : [];
  } catch {
    return [];
  }
}
