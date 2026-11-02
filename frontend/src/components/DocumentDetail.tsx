import { useCallback, useEffect, useState } from "react";
import { ReviewPanel } from "./ReviewPanel";
import {
  classifyDocument,
  extractDocumentText,
  extractPurchaseOrder,
  fetchClassification,
  fetchDocumentPages,
  fetchPurchaseOrder,
  reprocessPurchaseOrder,
  type ApiUser,
  type ClassificationResult,
  type DocumentPage,
  type DocumentRecord,
  type PurchaseOrderResult,
} from "../api";

type Props = {
  token: string;
  user: ApiUser;
  document: DocumentRecord;
  onUpdated: () => Promise<void>;
  onClose: () => void;
};

function display(value: string | null | undefined): string {
  return value ?? "Not extracted";
}

export function DocumentDetail({
  token,
  user,
  document,
  onUpdated,
  onClose,
}: Props) {
  const [classification, setClassification] =
    useState<ClassificationResult | null>(null);

  const [purchaseOrder, setPurchaseOrder] =
    useState<PurchaseOrderResult | null>(null);

  const [pages, setPages] = useState<DocumentPage[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canProcess =
    user.role === "admin" ||
    document.created_by_id === user.id;

  const loadDetails = useCallback(async () => {
    setLoading(true);

    try {
      const [classificationResult, purchaseOrderResult] =
        await Promise.all([
          fetchClassification(token, document.id),
          fetchPurchaseOrder(token, document.id),
        ]);

      setClassification(classificationResult);
      setPurchaseOrder(purchaseOrderResult);

      if (document.extraction_status === "completed") {
        const pageResults = await fetchDocumentPages(
          token,
          document.id,
        );

        setPages(pageResults);
      } else {
        setPages([]);
      }

      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load document details",
      );
    } finally {
      setLoading(false);
    }
  }, [token, document.id, document.extraction_status]);

  useEffect(() => {
    void loadDetails();
  }, [loadDetails]);

  async function performAction(
    name: string,
    action: () => Promise<unknown>,
  ) {
    setWorking(name);
    setError(null);

    try {
      await action();
      await onUpdated();
      await loadDetails();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : `${name} failed`,
      );
    } finally {
      setWorking(null);
    }
  }

  const canExtractText =
    canProcess &&
    document.status === "ready" &&
    document.extraction_status !== "completed";

  const canClassify =
    canProcess &&
    document.extraction_status === "completed" &&
    classification === null;

  const canExtractPO =
    canProcess &&
    classification?.predicted_type === "purchase_order" &&
    classification.review_status === "approved" &&
    purchaseOrder === null;

  const canReprocessPO =
    canProcess &&
    purchaseOrder !== null &&
    ["needs_review", "flagged"].includes(
      purchaseOrder.validation.status,
    );

  return (
    <section className="document-panel detail-panel">
      <div className="panel-heading">
        <div>
          <h2>{document.title}</h2>

          <p className="muted">
            {document.original_filename}
          </p>
        </div>

        <button
          className="secondary-button"
          onClick={onClose}
        >
          Close details
        </button>
      </div>

      <div className="document-meta">
        <span>Document: {document.id}</span>
        <span>Status: {document.status}</span>
        <span>
          Text extraction: {document.extraction_status}
        </span>
      </div>

      <div className="action-row">
        <button
          className="secondary-button"
          disabled={!canExtractText || working !== null}
          onClick={() =>
            performAction("Text extraction", () =>
              extractDocumentText(token, document.id),
            )
          }
        >
          Extract PDF text
        </button>

        <button
          className="secondary-button"
          disabled={!canClassify || working !== null}
          onClick={() =>
            performAction("Classification", () =>
              classifyDocument(token, document.id),
            )
          }
        >
          Classify document
        </button>

        <button
          className="primary-button"
          disabled={!canExtractPO || working !== null}
          onClick={() =>
            performAction("Purchase order extraction", () =>
              extractPurchaseOrder(token, document.id),
            )
          }
        >
          Extract purchase order
        </button>

        <button
          className="secondary-button"
          disabled={!canReprocessPO || working !== null}
          onClick={() =>
            performAction("Purchase order reprocessing", () =>
              reprocessPurchaseOrder(token, document.id),
            )
          }
        >
          Reprocess
        </button>
      </div>

      {working && (
        <p className="muted" role="status">
          Running {working.toLowerCase()}.
          Local AI processing may take some time.
        </p>
      )}

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      {loading && (
        <p className="muted">Loading document details...</p>
      )}

      {!loading && (
        <>
          <div className="detail-section">
            <h3>AI classification</h3>

            {classification ? (
              <div className="info-grid">
                <p>
                  <strong>Document type:</strong>{" "}
                  {classification.predicted_type}
                </p>

                <p>
                  <strong>Confidence:</strong>{" "}
                  {classification.confidence}
                </p>

                <p>
                  <strong>Review status:</strong>{" "}
                  {classification.review_status}
                </p>

                <p>
                  <strong>Explanation:</strong>{" "}
                  {classification.rationale}
                </p>
              </div>
            
            ) : (
              <p className="muted">
                No classification is available yet.
              </p>
            )}

            {classification?.review_status ===
              "pending_review" && (
              <p className="notice">
                Classification requires manager or admin
                approval before purchase order extraction.
              </p>
            )}
          </div>

          <div className="detail-section">
            <h3>Purchase order validation</h3>

            {purchaseOrder ? (
              <>
                <div className="info-grid">
                  <p>
                    <strong>PO number:</strong>{" "}
                    {display(purchaseOrder.extraction.po_number)}
                  </p>

                  <p>
                    <strong>Supplier:</strong>{" "}
                    {display(purchaseOrder.extraction.vendor)}
                  </p>

                  <p>
                    <strong>Currency:</strong>{" "}
                    {display(purchaseOrder.extraction.currency)}
                  </p>

                  <p>
                    <strong>Printed total:</strong>{" "}
                    {display(purchaseOrder.extraction.total_amount)}
                  </p>

                  <p>
                    <strong>Calculated total:</strong>{" "}
                    {display(
                      purchaseOrder.validation.calculated_total,
                    )}
                  </p>

                  <p>
                    <strong>Validation:</strong>{" "}
                    <span className="status-pill">
                      {purchaseOrder.validation.status}
                    </span>
                  </p>
                </div>

                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th>Quantity</th>
                        <th>Unit price</th>
                        <th>Printed amount</th>
                        <th>Page</th>
                      </tr>
                    </thead>

                    <tbody>
                      {purchaseOrder.extraction.line_items.map(
                        (item, index) => (
                          <tr key={index}>
                            <td>{item.description}</td>
                            <td>{item.quantity}</td>
                            <td>{item.unit_price}</td>
                            <td>
                              {display(item.printed_line_total)}
                            </td>
                            <td>{item.page_number}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
                {(purchaseOrder.extraction.delivery_milestones ?? []).length > 0 && (
                <div className="detail-section">
                <h4>Delivery milestones</h4>

                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Milestone</th>
                        <th>Due date</th>
                        <th>Deliverables</th>
                        <th>Source page</th>
                      </tr>
                    </thead>

                    <tbody>
                      {purchaseOrder.extraction.delivery_milestones?.map(
                        (milestone, index) => (
                          <tr key={index}>
                            <td>{milestone.name}</td>
                            <td>{milestone.due_date}</td>
                            <td>{milestone.deliverables}</td>
                            <td>{milestone.page_number}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

                {purchaseOrder.validation.issues.length > 0 && (
                  <div className="validation-issues">
                    <h4>Validation findings</h4>

                    {purchaseOrder.validation.issues.map(
                      (issue, index) => (
                        <div className="issue" key={index}>
                          <strong>{issue.code}</strong>

                          <p>{issue.message}</p>

                          {issue.expected !== null && (
                            <p>Calculated: {issue.expected}</p>
                          )}

                          {issue.stated !== null && (
                            <p>Printed: {issue.stated}</p>
                          )}
                        </div>
                      ),
                    )}
                  </div>
                )}
              </>
            ) : (
              <p className="muted">
                Purchase order data has not been extracted.
              </p>
            )}
          </div>

          <div className="detail-section">
            <h3>Source document text</h3>

            {pages.length === 0 && (
              <p className="muted">
                No extracted page text is available.
              </p>
            )}

            {pages.map((page) => (
              <details key={page.page_number}>
                <summary>
                  Page {page.page_number}
                </summary>

                <p className="source-ref">
                  {page.source_ref}
                </p>

                <pre className="page-text">
                  {page.text}
                </pre>
              </details>
            ))}
          </div>
          <ReviewPanel
              token={token}
              user={user}
              document={document}
              classification={classification}
              purchaseOrder={purchaseOrder}
              onReviewed={async () => {
                await onUpdated();
                await loadDetails();
              }}
            />
        </>
      )}
    </section>
  );
}