"use client";

import { useEffect, useRef, useState } from "react";
import { api, type KBDocument } from "@/lib/api";
import { Card, Empty, ErrorSummary, Field, Notice, PageHeader, Spinner, Tag, when } from "@/components/ui";

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
      setNotice(created.warning ?? `${created.filename} was indexed into ${created.chunk_count} searchable sections.`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function remove(doc: KBDocument) {
    if (!window.confirm(`Remove ${doc.filename} from the knowledge base? The receptionist will no longer answer from it.`)) return;
    setError(null);
    try {
      await api.delete(`/kb/documents/${doc.id}`);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  async function runTest(event: React.FormEvent) {
    event.preventDefault();
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
    <div>
      <PageHeader
        title="Knowledge base"
        lede="The documents here are the only source of facts the receptionist may state. Anything it cannot find, it escalates."
      />
      <ErrorSummary error={error} />
      {notice && <Notice kind="success">{notice}</Notice>}

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <Card
            title="Documents"
            description="PDF, Word, plain text or Markdown"
            flush
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
                <button className="btn btn-sm" disabled={uploading} onClick={() => fileInput.current?.click()}>
                  {uploading ? "Indexing…" : "Upload a document"}
                </button>
              </>
            }
          >
            {documents === null ? (
              <Spinner />
            ) : documents.length === 0 ? (
              <Empty
                message="No documents have been uploaded."
                hint="Without a knowledge base the receptionist escalates every question rather than guessing."
              />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">File</th>
                    <th scope="col" className="num">Sections</th>
                    <th scope="col">Status</th>
                    <th scope="col">Uploaded</th>
                    <th scope="col"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id}>
                      <td className="break-all font-bold">{doc.filename}</td>
                      <td className="num">{doc.chunk_count}</td>
                      <td>{doc.indexed ? <Tag value="searchable" tone="tag-green" /> : <Tag value="not indexed" tone="tag-yellow" />}</td>
                      <td className="text-secondary">{when(doc.created_at)}</td>
                      <td className="text-right">
                        <button className="btn btn-warning btn-sm" onClick={() => remove(doc)}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>

        <div className="lg:col-span-2">
          <Card title="Test a question" description="Runs the same retrieval a live caller triggers">
            <form onSubmit={runTest}>
              <Field label="Question" htmlFor="question">
                <textarea id="question" className="input" value={question} onChange={(e) => setQuestion(e.target.value)} />
              </Field>
              <button type="submit" className="btn" disabled={testing || !question.trim()}>
                {testing ? "Checking…" : "Ask the receptionist"}
              </button>
            </form>

            {result && (
              <div className="mt-6 border-t border-border pt-4">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  {result.answered ? <Tag value="would answer" tone="tag-green" /> : <Tag value="would escalate" tone="tag-orange" />}
                  <span className="text-sm text-secondary">Confidence {(result.confidence * 100).toFixed(0)}%</span>
                  {result.tier && <Tag value={result.tier} />}
                  {result.provider && <span className="kv text-secondary">{result.provider}</span>}
                </div>
                <p>{result.answer}</p>
                {result.sources.length > 0 && (
                  <p className="mt-3 text-sm text-secondary">Based on: {result.sources.join(", ")}</p>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
