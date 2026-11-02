import { useState, type FormEvent } from "react";

import {
  searchKnowledge,
  searchSemanticKnowledge,
  type KnowledgeSearchHit,
  type SemanticSearchHit,
} from "../api";

import "./KnowledgeSearch.css";

type SearchMode = "keyword" | "semantic";

type SearchResult = KnowledgeSearchHit | SemanticSearchHit;

type Props = {
  token: string;
  onOpenDocument: (documentId: string) => void;
};

export default function KnowledgeSearch({
  token,
  onOpenDocument,
}: Props) {
  const [mode, setMode] = useState<SearchMode>("keyword");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hasSearched, setHasSearched] = useState(false);

  function changeMode(nextMode: SearchMode) {
    if (loading) {
      return;
    }

    setMode(nextMode);
    setResults([]);
    setHasSearched(false);
    setError("");
  }

  async function handleSearch(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    const searchTerm = query.trim();

    if (searchTerm.length < 2) {
      return;
    }

    setLoading(true);
    setError("");
    setHasSearched(false);
    setResults([]);

    try {
      const data =
        mode === "keyword"
          ? await searchKnowledge(token, searchTerm)
          : await searchSemanticKnowledge(token, searchTerm);

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

      <div
        className="knowledge-search-modes"
        role="group"
        aria-label="Search mode"
      >
        <button
          type="button"
          className={
            mode === "keyword"
              ? "knowledge-mode active"
              : "knowledge-mode"
          }
          aria-pressed={mode === "keyword"}
          disabled={loading}
          onClick={() => changeMode("keyword")}
        >
          Keyword Search
        </button>

        <button
          type="button"
          className={
            mode === "semantic"
              ? "knowledge-mode active"
              : "knowledge-mode"
          }
          aria-pressed={mode === "semantic"}
          disabled={loading}
          onClick={() => changeMode("semantic")}
        >
          Semantic Search
        </button>
      </div>

      <p className="knowledge-mode-description">
        {mode === "keyword"
          ? "Find documents containing specific words or phrases."
          : "Find relevant information using natural-language questions."}
      </p>

      <form
        className="knowledge-search-form"
        onSubmit={handleSearch}
      >
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={
            mode === "keyword"
              ? "e.g. barcode, Pinecrest, Batch A"
              : "e.g. When will the first delivery arrive?"
          }
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

      {hasSearched && (
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

            {"similarity" in result && (
              <div className="knowledge-similarity">
                Similarity: {result.similarity.toFixed(3)}
              </div>
            )}

            <p className="knowledge-snippet">
              {result.snippet}
            </p>

            <div className="knowledge-result-footer">
              <div className="knowledge-source">
                Source: <code>{result.source_ref}</code>
              </div>

              <button
                type="button"
                className="knowledge-open-source"
                onClick={() =>
                  onOpenDocument(result.document_id)
                }
              >
                Open document
              </button>
            </div>
          </article>
        ))}
      </div>

      {mode === "semantic" && hasSearched && (
        <p className="knowledge-disclaimer">
          Similarity scores indicate retrieval relevance,
          not the probability that the information is correct.
        </p>
      )}
    </section>
  );
}