import { useState, type FormEvent } from "react";

import {
  searchKnowledge,
  type KnowledgeSearchHit,
} from "../api";

import "./KnowledgeSearch.css";

type Props = {
  token: string;
};

export default function KnowledgeSearch({ token }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<
    KnowledgeSearchHit[]
  >([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);

  async function handleSearch(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const trimmedQuery = query.trim();

    if (trimmedQuery.length < 2) {
      return;
    }

    setLoading(true);
    setError("");
    setHasSearched(false);
    setResults([]);

    try {
      const data = await searchKnowledge(
        token,
        trimmedQuery,
      );

      setResults(data);
      setHasSearched(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Search failed",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="knowledge-search">
      <header>
        <h2>Knowledge Search</h2>
        <p>
          Search approved procurement and operations
          documents.
        </p>
      </header>

      <form
        className="knowledge-search-form"
        onSubmit={handleSearch}
      >
        <input
          type="search"
          value={query}
          onChange={(event) =>
            setQuery(event.target.value)
          }
          placeholder="Search documents, suppliers, items..."
          minLength={2}
          maxLength={100}
          aria-label="Knowledge search query"
        />

        <button
          type="submit"
          disabled={
            loading || query.trim().length < 2
          }
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {error && (
        <p className="knowledge-error" role="alert">
          {error}
        </p>
      )}

      {hasSearched && !loading && (
        <p className="knowledge-count" aria-live="polite">
          {results.length} result(s) found
        </p>
      )}

      {hasSearched && results.length === 0 && (
        <div className="knowledge-empty">
          No matching approved documents found.
        </div>
      )}

      <div className="knowledge-results">
        {results.map((result, index) => (
          <article
            key={`${result.source_ref}-${index}`}
            className="knowledge-result"
          >
            <div className="knowledge-result-header">
              <h3>{result.document_title}</h3>

              <span className="knowledge-page">
                Page {result.page_number}
              </span>
            </div>

            <p className="knowledge-snippet">
              {result.snippet}
            </p>

            <div className="knowledge-source">
              Source: <code>{result.source_ref}</code>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}