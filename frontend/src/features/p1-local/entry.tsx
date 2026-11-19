"use client";

import { useEffect, useState } from "react";
import { CreatorStudio } from "@/features/studio/creator";
import type { Draft } from "@/features/studio/model";
import { LocalP1Flow } from "./flow";
import { P1_PENDING_OPEN_KEY, P1_SESSION_KEY } from "./sessions";

export const P1_INTAKE_KEY = "reviewlab.p1-local.intake.v1";
export const P1_NEW_EVENT = "reviewlab:p1-new";

export function LocalP1Entry() {
  const [flow, setFlow] = useState(false);
  useEffect(() => {
    const active = localStorage.getItem(P1_SESSION_KEY);
    setFlow(Boolean(active && JSON.parse(active)?.productId));
    const begin = () => setFlow(false);
    const open = () => setFlow(true);
    window.addEventListener(P1_NEW_EVENT, begin);
    window.addEventListener("reviewlab:p1-open", open);
    return () => { window.removeEventListener(P1_NEW_EVENT, begin); window.removeEventListener("reviewlab:p1-open", open); };
  }, []);

  function start(draft: Draft) {
    localStorage.setItem(P1_INTAKE_KEY, JSON.stringify({
      url: draft.sourceUrl,
      template: draft.style,
      ratio: draft.ratio,
      resolution: draft.resolution,
      duration: draft.duration,
    }));
    localStorage.removeItem(P1_PENDING_OPEN_KEY);
    setFlow(true);
  }

  return flow ? <LocalP1Flow onReset={() => setFlow(false)} /> : <CreatorStudio localP1Start={start} />;
}
