import { useRef, useState, type FormEvent } from "react";

import {
  registerDocument,
  uploadDocumentPdf,
} from "../api";

type Props = {
  token: string;
  onUploaded: () => Promise<void>;
};

const MAX_PDF_BYTES = 10 * 1024 * 1024;

export function UploadDocument({ token, onUploaded }: Props) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInput = useRef<HTMLInputElement>(null);

  function handleFileChange(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    const selected = event.target.files?.[0] ?? null;

    setFile(selected);
    setPendingId(null);
    setError(null);

    if (selected && !title.trim()) {
      setTitle(
        selected.name.replace(/\.pdf$/i, "").replaceAll("_", " "),
      );
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!file || !title.trim()) {
      setError("Enter a title and select a PDF.");
      return;
    }

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Only PDF files are supported.");
      return;
    }

    if (file.size > MAX_PDF_BYTES) {
      setError("The maximum PDF size is 10 MiB.");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      let documentId = pendingId;

      if (!documentId) {
        const registered = await registerDocument(
          token,
          title.trim(),
          file.name,
        );

        documentId = registered.id;
        setPendingId(documentId);
      }

      await uploadDocumentPdf(token, documentId, file);

      setPendingId(null);
      setTitle("");
      setFile(null);

      if (fileInput.current) {
        fileInput.current.value = "";
      }

      await onUploaded();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Document upload failed",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="document-panel upload-panel">
      <div>
        <h2>Upload purchase order or company document</h2>

        <p className="muted">
          Register a PDF securely in your department workspace.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="upload-form">
        <div>
          <label htmlFor="document-title">Document title</label>

          <input
            id="document-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Purchase Order PO-SYN-2026-004"
            required
          />
        </div>

        <div>
          <label htmlFor="document-file">PDF document</label>

          <input
            id="document-file"
            ref={fileInput}
            type="file"
            accept="application/pdf,.pdf"
            onChange={handleFileChange}
            required
          />
        </div>

        <button
          className="primary-button"
          type="submit"
          disabled={busy}
        >
          {busy
            ? "Uploading..."
            : pendingId
              ? "Retry upload"
              : "Register and upload"}
        </button>
      </form>

      {pendingId && (
        <p className="muted">
          Registration ID: {pendingId}
        </p>
      )}

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}