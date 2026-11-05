import { useState, type FormEvent } from "react";

import {
  askKnowledge,
  type RagAnswer,
} from "../api";

import "./RagAssistant.css";

type Props = {
  token: string;
  onOpenDocument: (documentId: string) => void;
};

export default function RagAssistant({
  token,
  onOpenDocument,
}: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<RagAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleAsk(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (question.trim().length < 2) {
      return;
    }

    setLoading(true);
    setResult(null);
    setError("");

    try {
      const answer = await askKnowledge(
        token,
        question,
      );

      setResult(answer);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not generate an answer",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rag-assistant">
      <header>
        <h2>OpsPilot AI Assistant</h2>

        <p>
          Ask questions about approved company documents.
          Answers include supporting sources.
        </p>
      </header>

      <form onSubmit={handleAsk} className="rag-form">
        <textarea
          value={question}
          onChange={(event) =>
            setQuestion(event.target.value)
          }
          placeholder="Ask a question about procurement or operations..."
          maxLength={500}
          rows={3}
          aria-label="Question for OpsPilot"
        />

        <button
          type="submit"
          disabled={
            loading || question.trim().length < 2
          }
        >
          {loading ? "Generating answer..." : "Ask OpsPilot"}
        </button>
      </form>

      {error && (
        <p className="rag-error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="rag-response">
          <h3>Answer</h3>

          <p className="rag-answer">
            {result.answer}
          </p>

          {!result.supported && (
            <p className="rag-warning">
              Insufficient supporting evidence.
            </p>
          )}

          {result.citations.length > 0 && (
            <div className="rag-citations">
              <h4>Supporting sources</h4>

              {result.citations.map((source, index) => (
                <div
                  key={`${source.source_ref}-${index}`}
                  className="rag-citation"
                >
                  <div>
                    <strong>
                      {source.document_title}
                    </strong>

                    <p>
                      Page {source.page_number}
                    </p>

                    <code>{source.source_ref}</code>
                  </div>

                  <button
                    type="button"
                    onClick={() =>
                      onOpenDocument(source.document_id)
                    }
                  >
                    Open document
                  </button>
                </div>
              ))}
            </div>
          )}

          <p className="rag-model">
            Model: {result.model_name}
          </p>
        </div>
      )}
    </section>
  );
}