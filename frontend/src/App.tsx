import { useEffect, useState, type FormEvent } from "react";
import { UploadDocument } from "./components/UploadDocument";
import { DocumentDetail } from "./components/DocumentDetail";
import {
  fetchDocuments,
  fetchProfile,
  login,
  type ApiUser,
  type DocumentRecord,
} from "./api";

import "./App.css";
import KnowledgeSearch from "./components/KnowledgeSearch";
import RagAssistant from "./components/RagAssistant";
import AgentWorkflows from "./components/AgentWorkflows";
import { DashboardSummary } from "./components/DashboardSummary";

type Session = {
  token: string;
  user: ApiUser;
};

function formatStatus(value: string | null): string {
  if (!value) {
    return "Not started";
  }

  return value.replaceAll("_", " ");
}

function formatDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }

  return date.toLocaleDateString("en-SG", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function App() {
  const [email, setEmail] = useState(
    "operations@demo.local",
  );

  const [password, setPassword] = useState("");
  const [session, setSession] = useState<Session | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [selectedDocumentId, setSelectedDocumentId] =
  useState<string | null>(null);
  const [dashboardRefreshKey, setDashboardRefreshKey] = useState(0);
  const [restoringSession, setRestoringSession] = useState(true);

  useEffect(() => {
  const token = sessionStorage.getItem("opspilot_token");

  if (!token) {
    setRestoringSession(false);
    return;
  }

  async function restoreSession() {
    try {
      const user = await fetchProfile(token!);
      const restoredDocuments = await fetchDocuments(token!);

      setSession({
        token: token!,
        user,
      });

      setDocuments(restoredDocuments);
      setDashboardRefreshKey((current) => current + 1);
    } catch {
      sessionStorage.removeItem("opspilot_token");
      setSession(null);
    } finally {
      setRestoringSession(false);
    }
  }

  restoreSession();
}, []);

  async function loadDocuments(token: string) {
    setDocumentsLoading(true);

    try {
      const result = await fetchDocuments(token);
      setDocuments(result);
      setDashboardRefreshKey((current) => current + 1);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load documents",
      );
    } finally {
      setDocumentsLoading(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setBusy(true);
    setError(null);

    try {
      const auth = await login(email.trim(), password);
      const user = await fetchProfile(auth.access_token);
      
      sessionStorage.setItem(
        "opspilot_token",
        auth.access_token,
      );

      setSession({
        token: auth.access_token,
        user,
      });

      setPassword("");
      await loadDocuments(auth.access_token);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Login failed",
      );
    } finally {
      setBusy(false);
    }
    
  }
  
  function openDocumentFromSearch(documentId: string) {
  const exists = documents.some(
    (item) => item.id === documentId,
  );

  if (!exists) {
    setError(
      "This document is not in the current list. Refresh documents and try again.",
    );
    return;
  }

  setSelectedDocumentId(documentId);

  window.requestAnimationFrame(() => {
    document
      .getElementById("selected-document")
      ?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
  });
}
  function handleLogout() {
    setSession(null);
    setDocuments([]);
    setPassword("");
    setError(null);
    setSelectedDocumentId(null);
    setDashboardRefreshKey(0);
    sessionStorage.removeItem("opspilot_token");
  }
  if (restoringSession) {
    return (
      <main className="login-page">
        <p>Restoring session...</p>
      </main>
    );
  }
  if (!session) {
    return (
      <main className="login-page">
        <section className="login-card">
          <div className="brand-mark">OP</div>

          <div className="eyebrow">
            PROCUREMENT AND OPERATIONS
          </div>

          <h1>Welcome to OpsPilot</h1>

          <p className="muted">
            Your secure workspace for company documents,
            procurement workflows and AI assistance.
          </p>

          <form onSubmit={handleLogin} className="login-form">
            <label htmlFor="email">Work email</label>

            <input
              id="email"
              type="email"
              value={email}
              onChange={(event) =>
                setEmail(event.target.value)
              }
              autoComplete="username"
              required
            />

            <label htmlFor="password">Password</label>

            <input
              id="password"
              type="password"
              value={password}
              onChange={(event) =>
                setPassword(event.target.value)
              }
              autoComplete="current-password"
              required
            />

            {error && (
              <p className="error-message" role="alert">
                {error}
              </p>
            )}

            <button
              type="submit"
              className="primary-button"
              disabled={busy}
            >
              {busy ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <p className="login-footer">
            OpsPilot MVP · Internal operations platform
          </p>
        </section>
      </main>
    );
  }

  const selectedDocument =
  documents.find(
    (document) => document.id === selectedDocumentId,
  ) ?? null;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark small">OP</span>
          <span>OpsPilot</span>
        </div>

        <div className="sidebar-section">WORKSPACE</div>

        <div className="nav-item active">
          Documents
        </div>

        <div className="sidebar-bottom">
          <div className="account-email">
            {session.user.email}
          </div>

          <div className="account-role">
            {session.user.role}
          </div>

          <button
            className="logout-button"
            onClick={handleLogout}
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="page-header">
          <div>
            <div className="eyebrow">OPERATIONS WORKSPACE</div>
            <h1>Document dashboard</h1>
      

            <p className="muted">
              Monitor document workload, approvals, exceptions and AI readiness.
            </p>
          </div>

          <div className="role-badge">
            {session.user.role}
          </div>
        </header>

        <DashboardSummary
          token={session.token}
          refreshKey={dashboardRefreshKey}
        />

        <UploadDocument
          token={session.token}
          onUploaded={() => loadDocuments(session.token)}
        />

        {selectedDocument && (
          <div id="selected-document">
            <DocumentDetail
              key={selectedDocument.id}
              token={session.token}
              user={session.user}
              document={selectedDocument}
              onUpdated={() => loadDocuments(session.token)}
              onClose={() => setSelectedDocumentId(null)}
            />
          </div>
        )}

        <section className="document-panel">
          <div className="panel-heading">
            <div>
              <h2>Company documents</h2>
              <p className="muted">
                Results follow your department permissions.
              </p>
            </div>

            <button
              className="secondary-button"
              onClick={() => loadDocuments(session.token)}
              disabled={documentsLoading}
            >
              {documentsLoading ? "Loading..." : "Refresh"}
            </button>
          </div>

          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}

          {documentsLoading && (
            <p className="muted">Loading documents...</p>
          )}

          {!documentsLoading && documents.length === 0 && (
            <div className="empty-state">
              No documents are available to this account.
            </div>
          )}

          {!documentsLoading && documents.length > 0 && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Status</th>
                    <th>Text extraction</th>
                    <th>Visibility</th>
                    <th>Created</th>
                  </tr>
                </thead>

                <tbody>
                  {documents.map((document) => (
                    <tr key={document.id}>
                      <td>
                        <button
                          type="button"
                          className="document-link"
                          onClick={() => setSelectedDocumentId(document.id)}
                        >
                          {document.title}
                        </button>

                        <div className="document-filename">
                          {document.original_filename}
                        </div>
                      </td>

                      <td>
                        <span className="status-pill">
                          {formatStatus(document.status)}
                        </span>
                      </td>

                      <td>
                        {formatStatus(
                          document.extraction_status,
                        )}
                      </td>

                      <td>{document.visibility}</td>

                      <td>{formatDate(document.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <KnowledgeSearch
          token={session.token}
          onOpenDocument={openDocumentFromSearch}
        />
        <RagAssistant
          token={session.token}
          onOpenDocument={openDocumentFromSearch}
        />
        <AgentWorkflows
          token={session.token}
          documents={documents}
        />
      </main>
    </div>
  );
}

export default App;