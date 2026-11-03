import { useEffect, useState, type FormEvent } from "react";
import "./AgentWorkflows.css";

type DocumentOption = {
  id: string;
  title: string;
};

type Workflow = {
  workflow_id: string;
  document_id: string;
  title: string;
  description: string;
  status: string;
  requested_by_id: string;
  reviewed_by_id: string | null;
  review_comment: string | null;
  created_at: string;
  follow_up_id: string | null;
  can_review: boolean;
};

type AuditEvent = {
  event_type: string;
  actor_id: string | null;
  details: string | null;
  created_at: string;
};

type Props = {
  token: string;
  documents: DocumentOption[];
};

async function apiRequest<T>(
  url: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;

    throw new Error(
      body?.detail || `Request failed (${response.status})`,
    );
  }

  return (await response.json()) as T;
}

export default function AgentWorkflows({ token, documents }: Props) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);

  const [documentId, setDocumentId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [reviewComment, setReviewComment] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [expandedWorkflow, setExpandedWorkflow] = useState<string | null>(
    null,
  );
  const [events, setEvents] = useState<AuditEvent[]>([]);

  useEffect(() => {
    let ignore = false;

    apiRequest<Workflow[]>("/api/agent/workflows", token)
      .then((data) => {
        if (!ignore) setWorkflows(data);
      })
      .catch((err: Error) => {
        if (!ignore) setError(err.message);
      });

    return () => {
      ignore = true;
    };
  }, [token]);

  async function refreshWorkflows() {
    const data = await apiRequest<Workflow[]>(
      "/api/agent/workflows",
      token,
    );

    setWorkflows(data);
  }

  async function handlePropose(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setBusy(true);
    setError("");
    setNotice("");

    try {
      const created = await apiRequest<Workflow>(
        "/api/agent/workflows",
        token,
        {
          method: "POST",
          body: JSON.stringify({
            document_id: documentId,
            title,
            description,
          }),
        },
      );

      setNotice(
        `Proposal submitted for approval: ${created.workflow_id}`,
      );

      setTitle("");
      setDescription("");

      await refreshWorkflows();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  async function decide(workflowId: string, approved: boolean) {
    setBusy(true);
    setError("");
    setNotice("");

    try {
      const updated = await apiRequest<Workflow>(
        `/api/agent/workflows/${workflowId}/decision`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            approved,
            comment: reviewComment,
          }),
        },
      );

      setNotice(`Workflow status: ${updated.status}`);
      setReviewComment("");

      await refreshWorkflows();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  async function viewHistory(workflowId: string) {
    if (expandedWorkflow === workflowId) {
      setExpandedWorkflow(null);
      return;
    }

    setError("");

    try {
      const data = await apiRequest<AuditEvent[]>(
        `/api/agent/workflows/${workflowId}/events`,
        token,
      );

      setEvents(data);
      setExpandedWorkflow(workflowId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "History unavailable");
    }
  }

  const pendingApprovals = workflows.filter(
    (workflow) => workflow.status === "pending" && workflow.can_review,
  );

  return (
    <section className="agent-workflows">
      <h2>Procurement Agent Workflows</h2>

      <p>
        Propose procurement follow-ups and track manager approvals.
      </p>

      {error && <p className="agent-workflows__error">{error}</p>}
      {notice && <p className="agent-workflows__notice">{notice}</p>}

      <h3>Propose a follow-up</h3>

      <form className="agent-workflows__form" onSubmit={handlePropose}>
        <label>
          Purchase order document
          <select
            value={documentId}
            onChange={(event) => setDocumentId(event.target.value)}
            required
          >
            <option value="">Select a document</option>

            {documents.map((document) => (
              <option key={document.id} value={document.id}>
                {document.title}
              </option>
            ))}
          </select>
        </label>

        <label>
          Task title
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Confirm Batch A delivery readiness"
            minLength={3}
            maxLength={160}
            required
          />
        </label>

        <label className="agent-workflows__wide">
          Description
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Describe the supplier follow-up required..."
            minLength={3}
            maxLength={2000}
            rows={3}
            required
          />
        </label>

        <button type="submit" disabled={busy || !documentId}>
          Request approval
        </button>
      </form>

      <h3>Manager approval queue</h3>

      {pendingApprovals.length === 0 ? (
        <p>No requests awaiting your approval.</p>
      ) : (
        pendingApprovals.map((workflow) => (
          <article
            className="agent-workflows__item"
            key={workflow.workflow_id}
          >
            <h4>{workflow.title}</h4>

            <p>{workflow.description}</p>

            <label>
              Review comment
              <textarea
                value={reviewComment}
                onChange={(event) =>
                  setReviewComment(event.target.value)
                }
                rows={2}
                maxLength={500}
              />
            </label>

            <div className="agent-workflows__actions">
              <button
                type="button"
                disabled={busy}
                onClick={() => void decide(workflow.workflow_id, true)}
              >
                Approve
              </button>

              <button
                type="button"
                className="agent-workflows__reject"
                disabled={busy}
                onClick={() => void decide(workflow.workflow_id, false)}
              >
                Reject
              </button>
            </div>
          </article>
        ))
      )}

      <h3>Workflow history</h3>

      {workflows.length === 0 ? (
        <p>No workflows found.</p>
      ) : (
        workflows.map((workflow) => (
          <article
            className="agent-workflows__item"
            key={workflow.workflow_id}
          >
            <div className="agent-workflows__heading">
              <h4>{workflow.title}</h4>

              <span className="agent-workflows__status">
                {workflow.status}
              </span>
            </div>

            <p>{workflow.description}</p>

            <small>
              Created: {new Date(workflow.created_at).toLocaleString()}
            </small>

            {workflow.follow_up_id && (
              <p>
                <small>
                  Follow-up ID: {workflow.follow_up_id}
                </small>
              </p>
            )}

            {workflow.review_comment && (
              <p>Review: {workflow.review_comment}</p>
            )}

            <button
              type="button"
              className="agent-workflows__history-button"
              onClick={() => void viewHistory(workflow.workflow_id)}
            >
              {expandedWorkflow === workflow.workflow_id
                ? "Hide audit history"
                : "View audit history"}
            </button>

            {expandedWorkflow === workflow.workflow_id && (
              <ul className="agent-workflows__events">
                {events.map((event, index) => (
                  <li key={`${event.event_type}-${index}`}>
                    <strong>
                      {event.event_type.replace(/_/g, " ")}
                    </strong>

                    {" | "}

                    {new Date(event.created_at).toLocaleString()}

                    {event.details && ` | ${event.details}`}
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))
      )}
    </section>
  );
}