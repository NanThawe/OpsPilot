import { useState } from "react";

type DeleteDocumentButtonProps = {
  token: string;
  documentId: string;
  documentTitle: string;
  onDeleted: () => void | Promise<void>;
};

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      detail?: string;
    };

    if (payload.detail) {
      return payload.detail;
    }
  } catch {
    // Fall through to the generic message.
  }

  return `Delete failed (${response.status})`;
}

export function DeleteDocumentButton({
  token,
  documentId,
  documentTitle,
  onDeleted,
}: DeleteDocumentButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    const confirmed = window.confirm(
      `Delete "${documentTitle}"?\n\n` +
        "This removes the document and its processing data. " +
        "Approved purchase orders and documents with workflow " +
        "history are protected.\n\n" +
        "This action cannot be undone.",
    );

    if (!confirmed) {
      return;
    }

    setBusy(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/documents/${encodeURIComponent(documentId)}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        },
      );

      if (!response.ok) {
        throw new Error(await errorMessage(response));
      }

      await onDeleted();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not delete document",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="delete-document-control">
      <button
        type="button"
        className="danger-button"
        onClick={handleDelete}
        disabled={busy}
      >
        {busy ? "Deleting..." : "Delete document"}
      </button>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
