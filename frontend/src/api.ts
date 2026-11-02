export type ApiUser = {
  id: string;
  email: string;
  role: string;
  department_id: string | null;
};

export type DocumentRecord = {
  id: string;
  title: string;
  original_filename: string;
  created_by_id: string;
  status: string;
  extraction_status: string | null;
  visibility: string;
  created_at: string;
  department_id: string;
};

type LoginResponse = {
  access_token: string;
  token_type: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api${path}`, options);

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const body: unknown = await response.json();

      if (
        body !== null &&
        typeof body === "object" &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        message = body.detail;
      }
    } catch {
      // Preserve the HTTP status message.
    }

    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
  };
}

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      username: email,
      password,
    }),
  });
}

export async function fetchProfile(
  token: string,
): Promise<ApiUser> {
  return request<ApiUser>("/auth/me", {
    headers: authHeaders(token),
  });
}

export async function fetchDocuments(
  token: string,
): Promise<DocumentRecord[]> {
  const result = await request<
    DocumentRecord[] | { items: DocumentRecord[] }
  >("/documents", {
    headers: authHeaders(token),
  });

  if (Array.isArray(result)) {
    return result;
  }

  if (result && Array.isArray(result.items)) {
    return result.items;
  }

  throw new Error("Unexpected document list response");
}

export type ClassificationResult = {
  predicted_type: string;
  confidence: string;
  rationale: string;
  review_status: string;
  evidence_page_numbers: number[];
  model_name: string;
};

export type PurchaseOrderLine = {
  description: string;
  quantity: string;
  unit_price: string;
  printed_line_total: string | null;
  page_number: number;
};

export type PurchaseOrderResult = {
  document_id: string;
  extraction: {
    po_number: string | null;
    vendor: string | null;
    buyer: string | null;
    currency: string | null;
    line_items: PurchaseOrderLine[];
    subtotal: string | null;
    tax_amount: string | null;
    total_amount: string | null;
    delivery_milestones?: {
    name: string;
    due_date: string;
    deliverables: string;
    page_number: number;
}[];
  };
  validation: {
    status: "passed" | "flagged" | "needs_review";
    calculated_total: string | null;
    issues: {
      code: string;
      field: string;
      message: string;
      expected: string | null;
      stated: string | null;
    }[];
  };
  model_name: string;
};

export type DocumentPage = {
  page_number: number;
  text: string;
  source_ref: string;
};

async function optionalGet<T>(
  path: string,
  token: string,
): Promise<T | null> {
  try {
    return await request<T>(path, {
      headers: authHeaders(token),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }

    throw error;
  }
}

export async function registerDocument(
  token: string,
  title: string,
  filename: string,
): Promise<DocumentRecord> {
  return request<DocumentRecord>("/documents", {
    method: "POST",
    headers: {
      ...authHeaders(token),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title,
      original_filename: filename,
      visibility: "department",
    }),
  });
}

export async function uploadDocumentPdf(
  token: string,
  documentId: string,
  file: File,
): Promise<unknown> {
  const form = new FormData();
  form.append("file", file, file.name);

  return request<unknown>(
    `/documents/${documentId}/upload`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: form,
    },
  );
}

export async function extractDocumentText(
  token: string,
  documentId: string,
): Promise<unknown> {
  return request<unknown>(
    `/documents/${documentId}/extract`,
    {
      method: "POST",
      headers: authHeaders(token),
    },
  );
}

export async function classifyDocument(
  token: string,
  documentId: string,
): Promise<unknown> {
  return request<unknown>(
    `/documents/${documentId}/classify`,
    {
      method: "POST",
      headers: authHeaders(token),
    },
  );
}

export async function extractPurchaseOrder(
  token: string,
  documentId: string,
): Promise<unknown> {
  return request<unknown>(
    `/documents/${documentId}/purchase-order/extract`,
    {
      method: "POST",
      headers: authHeaders(token),
    },
  );
}

export async function reprocessPurchaseOrder(
  token: string,
  documentId: string,
): Promise<unknown> {
  return request<unknown>(
    `/documents/${documentId}/purchase-order/reprocess`,
    {
      method: "POST",
      headers: authHeaders(token),
    },
  );
}

export function fetchClassification(
  token: string,
  documentId: string,
): Promise<ClassificationResult | null> {
  return optionalGet<ClassificationResult>(
    `/documents/${documentId}/classification`,
    token,
  );
}

export function fetchPurchaseOrder(
  token: string,
  documentId: string,
): Promise<PurchaseOrderResult | null> {
  return optionalGet<PurchaseOrderResult>(
    `/documents/${documentId}/purchase-order`,
    token,
  );
}

export function fetchDocumentPages(
  token: string,
  documentId: string,
): Promise<DocumentPage[]> {
  return request<DocumentPage[]>(
    `/documents/${documentId}/pages`,
    {
      headers: authHeaders(token),
    },
  );
}

export type PurchaseOrderRevision =
  PurchaseOrderResult & {
    revision_number: number;
    created_by_id: string | null;
    created_at: string;
  };

export type PurchaseOrderReview = {
  document_id: string;
  revision_number: number;
  decision: "approved" | "rejected" | "changes_requested";
  note: string | null;
  reviewed_by_id: string;
  reviewed_at: string;
};

export type ClassificationDecision = "approve" | "reject";

export type PurchaseOrderDecision =
  | "approve"
  | "reject"
  | "request_changes";

export async function submitClassificationReview(
  token: string,
  documentId: string,
  decision: ClassificationDecision,
  note: string,
): Promise<unknown> {
  return request<unknown>(
    `/documents/${documentId}/classification/review`,
    {
      method: "POST",
      headers: {
        ...authHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        decision,
        note: note.trim() || null,
      }),
    },
  );
}

export async function submitPurchaseOrderReview(
  token: string,
  documentId: string,
  revisionNumber: number,
  decision: PurchaseOrderDecision,
  note: string,
): Promise<PurchaseOrderReview> {
  return request<PurchaseOrderReview>(
    `/documents/${documentId}/purchase-order/review`,
    {
      method: "POST",
      headers: {
        ...authHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        revision_number: revisionNumber,
        decision,
        note: note.trim() || null,
      }),
    },
  );
}

export async function fetchPurchaseOrderHistory(
  token: string,
  documentId: string,
): Promise<PurchaseOrderRevision[]> {
  return request<PurchaseOrderRevision[]>(
    `/documents/${documentId}/purchase-order/history`,
    {
      headers: authHeaders(token),
    },
  );
}

export async function fetchPurchaseOrderReviews(
  token: string,
  documentId: string,
): Promise<PurchaseOrderReview[]> {
  return request<PurchaseOrderReview[]>(
    `/documents/${documentId}/purchase-order/reviews`,
    {
      headers: authHeaders(token),
    },
  );
}

export type KnowledgeSearchHit = {
  document_id: string;
  document_title: string; // Previously: title
  page_number: number;
  snippet: string;
  source_ref: string;
};

export async function searchKnowledge(
  token: string,
  query: string,
): Promise<KnowledgeSearchHit[]> {
  const params = new URLSearchParams({
    q: query.trim(),
    limit: "20",
  });

  const response = await fetch(
    `/api/knowledge/search?${params.toString()}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );

  if (response.status === 401) {
    throw new Error("Session expired. Please log in again.");
  }

  if (!response.ok) {
    throw new Error(
      `Knowledge search failed (HTTP ${response.status})`,
    );
  }

  return (await response.json()) as KnowledgeSearchHit[];
}

export type SemanticSearchHit = KnowledgeSearchHit & {
  similarity: number;
};

export async function searchSemanticKnowledge(
  token: string,
  query: string,
): Promise<SemanticSearchHit[]> {
  const params = new URLSearchParams({
    q: query.trim(),
    limit: "10",
  });

  const response = await fetch(
    `/api/knowledge/semantic-search?${params.toString()}`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );

  if (response.status === 401) {
    throw new Error("Session expired. Please log in again.");
  }

  if (!response.ok) {
    throw new Error(
      `Semantic search failed (HTTP ${response.status})`,
    );
  }

  return (await response.json()) as SemanticSearchHit[];
}