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
  status: string;
  extraction_status: string | null;
  visibility: string;
  created_at: string;
};

type LoginResponse = {
  access_token: string;
  token_type: string;
};

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

    throw new Error(message);
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