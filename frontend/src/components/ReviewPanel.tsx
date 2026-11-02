import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react";

import {
  fetchPurchaseOrderHistory,
  fetchPurchaseOrderReviews,
  submitClassificationReview,
  submitPurchaseOrderReview,
  type ApiUser,
  type ClassificationDecision,
  type ClassificationResult,
  type DocumentRecord,
  type PurchaseOrderDecision,
  type PurchaseOrderResult,
  type PurchaseOrderReview,
  type PurchaseOrderRevision,
} from "../api";

type Props = {
  token: string;
  user: ApiUser;
  document: DocumentRecord;
  classification: ClassificationResult | null;
  purchaseOrder: PurchaseOrderResult | null;
  onReviewed: () => Promise<void>;
};

export function ReviewPanel({
  token,
  user,
  document,
  classification,
  purchaseOrder,
  onReviewed,
}: Props) {
  const [history, setHistory] = useState<
    PurchaseOrderRevision[]
  >([]);

  const [reviews, setReviews] = useState<
    PurchaseOrderReview[]
  >([]);

  const [classificationDecision, setClassificationDecision] =
    useState<ClassificationDecision>("approve");

  const [classificationNote, setClassificationNote] =
    useState("");

  const [poDecision, setPoDecision] =
    useState<PurchaseOrderDecision>("request_changes");

  const [poNote, setPoNote] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canReviewDepartment =
    user.role === "admin" ||
    (
      user.role === "manager" &&
      user.department_id !== null &&
      user.department_id === document.department_id
    );

  const isDocumentCreator =
    user.id === document.created_by_id;

  const canReview =
    canReviewDepartment && !isDocumentCreator;

  const loadHistory = useCallback(async () => {
    if (!purchaseOrder) {
      setHistory([]);
      setReviews([]);
      return;
    }

    try {
      const [revisions, reviewRecords] =
        await Promise.all([
          fetchPurchaseOrderHistory(token, document.id),
          fetchPurchaseOrderReviews(token, document.id),
        ]);

      setHistory(revisions);
      setReviews(reviewRecords);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load review history",
      );
    }
  }, [token, document.id, purchaseOrder]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const latestRevision = history.at(-1);

  const latestReview = latestRevision
    ? reviews.find(
        (review) =>
          review.revision_number ===
          latestRevision.revision_number,
      )
    : undefined;

  const initiatedLatestRevision =
    latestRevision?.created_by_id === user.id;

  const canReviewPurchaseOrder =
    canReview &&
    latestRevision !== undefined &&
    !latestReview &&
    !initiatedLatestRevision;

  async function handleClassificationReview(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (
      classificationDecision === "reject" &&
      !classificationNote.trim()
    ) {
      setError("Provide a reason for rejecting classification.");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      await submitClassificationReview(
        token,
        document.id,
        classificationDecision,
        classificationNote,
      );

      setClassificationNote("");
      await onReviewed();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Classification review failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handlePurchaseOrderReview(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!latestRevision) {
      return;
    }

    if (
      poDecision !== "approve" &&
      !poNote.trim()
    ) {
      setError("Provide a reason for this decision.");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      await submitPurchaseOrderReview(
        token,
        document.id,
        latestRevision.revision_number,
        poDecision,
        poNote,
      );

      setPoNote("");
      await onReviewed();
      await loadHistory();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Purchase order review failed",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="review-workspace">
      <div className="detail-section">
        <h3>Classification review</h3>

        {!classification && (
          <p className="muted">
            Classify the document before requesting review.
          </p>
        )}

        {classification && (
          <p className="muted">
            Current status:{" "}
            <strong>{classification.review_status}</strong>
          </p>
        )}

        {classification?.review_status === "pending_review" &&
          canReview && (
            <form
              className="review-form"
              onSubmit={handleClassificationReview}
            >
              <label htmlFor="classification-decision">
                Decision
              </label>

              <select
                id="classification-decision"
                value={classificationDecision}
                onChange={(event) =>
                  setClassificationDecision(
                    event.target.value as ClassificationDecision,
                  )
                }
              >
                <option value="approve">Approve classification</option>
                <option value="reject">Reject classification</option>
              </select>

              <label htmlFor="classification-note">
                Review note
              </label>

              <textarea
                id="classification-note"
                value={classificationNote}
                onChange={(event) =>
                  setClassificationNote(event.target.value)
                }
                maxLength={500}
                required={classificationDecision === "reject"}
                placeholder="Explain your decision"
              />

              <button
                className="primary-button"
                type="submit"
                disabled={busy}
              >
                Submit classification review
              </button>
            </form>
          )}
      </div>

      <div className="detail-section">
        <h3>Purchase order approval</h3>

        {!purchaseOrder && (
          <p className="muted">
            Purchase order extraction is not available yet.
          </p>
        )}

        {purchaseOrder && (
          <>
            <p>
              Validation status:{" "}
              <strong>
                {purchaseOrder.validation.status}
              </strong>
            </p>

            {latestRevision && (
              <p className="muted">
                Latest revision: {latestRevision.revision_number}
              </p>
            )}

            {latestReview && (
              <div className="notice">
                <strong>Reviewed:</strong>{" "}
                {latestReview.decision}

                {latestReview.note && (
                  <p>{latestReview.note}</p>
                )}
              </div>
            )}
            {purchaseOrder && !canReviewPurchaseOrder && !latestReview && (
            <p className="notice">
                {isDocumentCreator
                ? "You cannot review a document you created."
                : initiatedLatestRevision
                    ? "You cannot review an extraction revision you initiated."
                    : !canReviewDepartment
                    ? "You do not have permission to review this department."
                    : "This revision is not currently available for review."}
            </p>
            )}
            {canReviewPurchaseOrder && (
              <form
                className="review-form"
                onSubmit={handlePurchaseOrderReview}
              >
                <label htmlFor="po-decision">
                  Decision
                </label>

                <select
                  id="po-decision"
                  value={poDecision}
                  onChange={(event) =>
                    setPoDecision(
                      event.target.value as PurchaseOrderDecision,
                    )
                  }
                >
                  <option
                    value="approve"
                    disabled={
                      purchaseOrder.validation.status !== "passed"
                    }
                  >
                    Approve purchase order
                  </option>

                  <option value="request_changes">
                    Request changes
                  </option>

                  <option value="reject">
                    Reject purchase order
                  </option>
                </select>

                <label htmlFor="po-review-note">
                  Review note
                </label>

                <textarea
                  id="po-review-note"
                  value={poNote}
                  onChange={(event) =>
                    setPoNote(event.target.value)
                  }
                  maxLength={500}
                  required={poDecision !== "approve"}
                  placeholder="Record findings or required corrections"
                />

                <button
                  className="primary-button"
                  type="submit"
                  disabled={busy}
                >
                  Submit purchase order review
                </button>
              </form>
            )}
          </>
        )}

        {!canReviewDepartment && (
          <p className="muted">
            Review actions are restricted to authorised managers
            and administrators.
          </p>
        )}

        {isDocumentCreator && (
          <p className="muted">
            Document creators cannot review their own purchase orders.
          </p>
        )}
      </div>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      <div className="detail-section">
        <h3>Extraction and review history</h3>

        {history.length === 0 ? (
          <p className="muted">
            No extraction revisions are available.
          </p>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Revision</th>
                  <th>Validation</th>
                  <th>Calculated total</th>
                  <th>Review decision</th>
                </tr>
              </thead>

              <tbody>
                {history.map((revision) => {
                  const review = reviews.find(
                    (item) =>
                      item.revision_number ===
                      revision.revision_number,
                  );

                  return (
                    <tr key={revision.revision_number}>
                      <td>#{revision.revision_number}</td>

                      <td>{revision.validation.status}</td>

                      <td>
                        {revision.validation.calculated_total ??
                          "Not calculated"}
                      </td>

                      <td>
                        {review?.decision ?? "pending_review"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}