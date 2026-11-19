"use client";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useWorkspace } from "../content-factory/workspace-provider";
import { approvedKnowledge } from "../content-factory/model";
import { DemoNotice } from "./dashboards";
export function Campaigns() {
  const { projects, updateProject, ready } = useWorkspace();
  const [error, setError] = useState("");
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Campaigns</h1>
          <p>
            Tham gia campaign để dùng nội dung và link tracking mẫu.
          </p>
        </div>
      </div>
      <DemoNotice />
      {!ready ? (
        <p role="status">Đang tải…</p>
      ) : (
        <section className="portal-panel">
          {projects
            .filter((p) => p.campaign?.active)
            .map((project) => (
              <article className="task-row" key={project.id}>
                <div>
                  <strong>{project.name}</strong>
                  <p>
                    {project.campaign?.active ? "Đang mở" : "Chưa mở"} ·{" "}
                    {project.campaign?.joined ? "1 Creator demo" : "0 Creator"}{" "}
                    · {project.campaign?.views ?? 0} views /{" "}
                    {project.campaign?.clicks ?? 0} clicks (mock)
                  </p>
                </div>
                <Button
                  disabled={
                    !approvedKnowledge(project) ||
                    project.campaign?.joined
                  }
                  onClick={() => {
                    try {
                      updateProject(project.id, (p) => ({
                        ...p,
                        campaign: {
                          views: 0,
                          clicks: 0,
                          ...p.campaign,
                          active: true,
                          joined: true,
                        },
                      }));
                      setError("");
                    } catch (cause) {
                      setError(
                        cause instanceof Error
                          ? cause.message
                          : "Không thể lưu.",
                      );
                    }
                  }}
                >
                  {project.campaign?.joined ? "Đã tham gia" : "Tham gia campaign"}
                </Button>
              </article>
            ))}
          {!projects.some((p) => p.campaign?.active) && (
            <p>Chưa có campaign đang mở.</p>
          )}
        </section>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <Link
        className="inline-action"
        href="/creator/library"
      >
        Về thư viện ↗
      </Link>
    </>
  );
}
