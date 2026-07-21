"use client";

import { useEffect, useRef, useState } from "react";
import { api, type KBDocument } from "@/lib/api";
import { Badge, Empty, ErrorNote, Panel, Spinner, when } from "@/components/ui";

interface TestResult {
  answered: boolean;
  answer: string;
  confidence: number;
  sources: string[];
  provider: string | null;
  tier: string | null;
}

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<KBDocument[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const [question, setQuestion] = useState("What are your opening hours?");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);

  function load() {
    api
      .get<KBDocument[]>("/kb/documents")
      .then(setDocuments)
      .catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.upload<KBDocument & { warning?: string }>("/kb/upload", file);
      setNotice(
        created.warning ??
          `Indexed ${created.filename} into ${created.chunk_count} searchable chunks.`,
      );
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api.delete(`/kb/documents/${id}`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function runTest() {
    setTesting(true);
    setResult(null);
    setError(null);
    try {
      setResult(await api.post<TestResult>("/kb/test", { question }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Test failed");
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-6">
      <ErrorNote error={error} />
      {notice && (
        <div className="rounded-md border border-emerald-900 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-300">
          {notice}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Documents"
          subtitle="PDF, DOCX, TXT, or Markdown — the only facts the agent may state"
          actions={
            <>
              <input
                ref={fileInput}
                type="file"
                accept=".pdf,.docx,.txt,.md,.markdown"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload(file);
                }}
              />
              <button
                className="btn btn-primary px-2 py-1 text-xs"
                disabled={uploading}
                onClick={() => fileInput.current?.click()}
              >
                {uploading ? "Indexing…" : "Upload"}
              </button>
            </>
          }
        >
          {documents === null ? (
            <Spinner />
          ) : documents.length === 0 ? (
            <Empty
              message="No documents yet."
              hint="Without a knowledge base the agent will escalate every question instead of guessing."
            />
          ) : (
            <div className="divide-y divide-edge">
              {documents.map((doc) => (
                <div key={doc.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm text-slate-200">{doc.filename}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {doc.chunk_count} chunks · {when(doc.created_at)}
                    </div>
                  </div>
                  {doc.indexed ? (
                    <span className="chip bg-emerald-950 text-emerald-300">searchable</span>
                  ) : (
                    <span className="chip bg-amber-950 text-amber-300">not indexed</span>
                  )}
                  <button
                    className="btn btn-danger px-2 py-1 text-xs"
                    onClick={() => remove(doc.id)}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Test a question"
          subtitle="Runs the exact retrieval path a live caller hits"
        >
          <div className="space-y-3 p-4">
            <textarea
              className="input min-h-[5rem] resize-y"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask something a caller might ask…"
            />
            <button
              className="btn btn-primary"
              onClick={runTest}
              disabled={testing || !question.trim()}
            >
              {testing ? "Thinking…" : "Ask"}
            </button>

            {result && (
              <div className="space-y-3 rounded-md border border-edge bg-ink p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {result.answered ? (
                    <span className="chip bg-emerald-950 text-emerald-300">answered</span>
                  ) : (
                    <span className="chip bg-amber-950 text-amber-300">would escalate</span>
                  )}
                  <span className="text-muted">
                    confidence {(result.confidence * 100).toFixed(0)}%
                  </span>
                  {result.tier && <Badge value={result.tier} />}
                  {result.provider && (
                    <span className="font-mono text-muted">{result.provider}</span>
                  )}
                </div>

                <p className="text-sm leading-relaxed text-slate-200">{result.answer}</p>

                {result.sources.length > 0 && (
                  <div className="text-xs text-muted">
                    Grounded in: {result.sources.join(", ")}
                  </div>
                )}
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
