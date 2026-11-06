import { useEffect, useState } from "react";
import "./DashboardSummary.css";

type DashboardSummaryData = {
  visible_documents: number;
  pending_reviews: number;
  flagged_purchase_orders: number;
  pending_approvals: number;
  ai_searchable_documents: number;
  processing_issues: number;
};

type Props = {
  token: string;
  refreshKey: number;
};

type Metric = {
  label: string;
  value: number;
  note: string;
  tone: "neutral" | "warning" | "danger" | "info" | "success";
};

async function fetchDashboardSummary(
  token: string,
): Promise<DashboardSummaryData> {
  const response = await fetch(
    "/api/dashboard/summary",
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );

  if (!response.ok) {
    let detail = "Could not load dashboard metrics";

    try {
      const payload = (await response.json()) as {
        detail?: string;
      };

      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Use the fallback message.
    }

    throw new Error(detail);
  }

  return response.json() as Promise<DashboardSummaryData>;
}

export function DashboardSummary({
  token,
  refreshKey,
}: Props) {
  const [summary, setSummary] =
    useState<DashboardSummaryData | null>(null);
  const [error, setError] =
    useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadSummary() {
      try {
        const result =
          await fetchDashboardSummary(token);

        if (active) {
          setSummary(result);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load dashboard metrics",
          );
        }
      }
    }

    void loadSummary();

    return () => {
      active = false;
    };
  }, [token, refreshKey]);

  if (error) {
    return (
      <section className="dashboard-summary-error">
        {error}
      </section>
    );
  }

  const metrics: Metric[] = [
    {
      label: "Visible documents",
      value: summary?.visible_documents ?? 0,
      note: "Available to your account",
      tone: "neutral",
    },
    {
      label: "Pending review",
      value: summary?.pending_reviews ?? 0,
      note: "Classification decisions needed",
      tone: "warning",
    },
    {
      label: "Flagged POs",
      value:
        summary?.flagged_purchase_orders ?? 0,
      note: "Validation needs attention",
      tone: "danger",
    },
    {
      label: "Pending approvals",
      value: summary?.pending_approvals ?? 0,
      note: "Agent workflows awaiting action",
      tone: "warning",
    },
    {
      label: "AI searchable",
      value:
        summary?.ai_searchable_documents ?? 0,
      note: "Trusted documents indexed",
      tone: "success",
    },
    {
      label: "Processing issues",
      value: summary?.processing_issues ?? 0,
      note: "Failed document operations",
      tone: "info",
    },
  ];

  return (
    <section
      className="dashboard-metrics"
      aria-label="Operational summary"
    >
      {metrics.map((metric) => (
        <article
          className={`dashboard-metric-card dashboard-metric-${metric.tone}`}
          key={metric.label}
        >
          <div className="dashboard-metric-label">
            {metric.label}
          </div>

          <div className="dashboard-metric-value">
            {summary ? metric.value : "—"}
          </div>

          <div className="dashboard-metric-note">
            {metric.note}
          </div>
        </article>
      ))}
    </section>
  );
}
