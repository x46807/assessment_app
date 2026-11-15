'use client';

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import InteractiveQuiz from "@/components/InteractiveQuiz";
import TopicEvaluation from "@/components/TopicEvaluation";
import { Loader2, Play, Copy, FileText, ArrowLeft } from "lucide-react";

interface SharedSource {
  id: string;
  title: string;
  source_type: string;
  purpose: "source" | "example";
  is_concepts_source: boolean;
  source_url?: string | null;
  chunks: number;
  images?: number;
  created_at: string;
  reused?: boolean;
  ingested_at?: string | null;
  page_range?: string | null;
  page_count?: number | null;
}

interface SharedBank {
  id: string;
  title: string;
  created_at: string;
  question_count: number;
}

interface SharedDetail {
  id: string;
  title: string;
  description?: string | null;
  owner_name?: string | null;
  owner_email: string;
  shared_at: string;
  created_at: string;
  sources: SharedSource[];
  banks: SharedBank[];
}

const PURPOSE_LABEL: Record<string, string> = {
  source: "Source material",
  example: "Example questions",
};

export default function SharedTopicPage() {
  const { id } = useParams();
  const router = useRouter();
  const { apiFetch } = useAuth();

  const [detail, setDetail] = useState<SharedDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openBankId, setOpenBankId] = useState<string | null>(null);
  const [bankItems, setBankItems] = useState<any[]>([]);
  const [loadingBankItems, setLoadingBankItems] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [cloneError, setCloneError] = useState("");

  useEffect(() => {
    apiFetch(`/api/shared-topics/${id}`)
      .then(setDetail)
      .catch((err: any) => setError(err?.message || "Could not open this shared topic"))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const openBank = async (bankId: string) => {
    setOpenBankId(bankId);
    setLoadingBankItems(true);
    try {
      const items = await apiFetch(`/api/shared-topics/${id}/items?bank_id=${bankId}`);
      setBankItems(items);
    } catch {
      setBankItems([]);
    } finally {
      setLoadingBankItems(false);
    }
  };

  const cloneTopic = async () => {
    setCloneError("");
    setCloning(true);
    try {
      const created = await apiFetch(`/api/shared-topics/${id}/clone`, { method: "POST" });
      router.push(`/bucket/${created.id}`);
    } catch (err: any) {
      setCloneError(err?.message || "Could not clone this topic");
    } finally {
      setCloning(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div>;
  }

  if (error || !detail) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8">
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error || "This shared topic could not be found."}</p>
      </div>
    );
  }

  const openBankObj = detail.banks.find((b) => b.id === openBankId) || null;
  const totalQuestions = detail.banks.reduce((n, b) => n + b.question_count, 0);

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex items-start justify-between gap-4 mb-2">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-slate-900 truncate">{detail.title}</h1>
          <p className="text-sm text-slate-500 mt-1">
            Shared by {detail.owner_name || detail.owner_email} · Read-only — you can take the quizzes and clone this topic into your own library. The owner&apos;s answers stay private.
          </p>
          {detail.description && <p className="text-sm text-slate-600 mt-2">{detail.description}</p>}
        </div>
        <button onClick={cloneTopic} disabled={cloning} className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2.5 rounded-lg shadow-sm transition-colors shrink-0 disabled:opacity-50">
          <Copy className="h-4 w-4" />
          <span>{cloning ? "Cloning..." : "Clone into my topics"}</span>
        </button>
      </div>
      {cloneError && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-6">{cloneError}</p>}

      <div className="bg-white border border-slate-200 rounded-2xl px-5 py-4 mb-8">
        <h3 className="font-bold text-slate-900">Sources ({detail.sources.length})</h3>
        {detail.sources.length === 0 ? (
          <p className="text-sm text-slate-500 mt-2">This topic has no uploaded sources yet.</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {detail.sources.map((s) => (
              <li key={s.id} className="flex items-start gap-3 text-sm">
                <FileText className="h-4 w-4 text-slate-400 mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-slate-800 truncate">{s.title}</p>
                  <p className="text-xs text-slate-500">
                    {PURPOSE_LABEL[s.purpose] || s.purpose} · {s.chunks} chunk{s.chunks === 1 ? "" : "s"}
                    {s.images ? ` · ${s.images} image${s.images === 1 ? "" : "s"} extracted` : ""}
                    {s.page_range ? ` · Pages ${s.page_range}` : s.page_count ? " · All pages" : ""}
                    {s.is_concepts_source ? " · Key concepts" : ""}
                    {s.reused && s.ingested_at ? ` · Reused — first ingested ${new Date(s.ingested_at).toLocaleDateString()}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {openBankId && openBankObj ? (
        <div>
          <button onClick={() => setOpenBankId(null)} className="flex items-center gap-1 text-sm font-semibold text-indigo-600 hover:text-indigo-800 mb-4">
            <ArrowLeft className="h-4 w-4" /> Back to banks
          </button>
          <h3 className="font-bold text-slate-900 mb-1">{openBankObj.title}</h3>
          <p className="text-xs text-slate-500 mb-4">{openBankObj.question_count} question{openBankObj.question_count === 1 ? "" : "s"} · {new Date(openBankObj.created_at).toLocaleString()}</p>
          {loadingBankItems ? <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div> : <InteractiveQuiz items={bankItems} bucketId={id as string} bankId={openBankId} />}
        </div>
      ) : (
        <div>
          <TopicEvaluation bucketId={id as string} />
          <div className="mb-4">
            <h3 className="font-bold text-slate-900">Question Banks</h3>
            <p className="text-xs text-slate-500">{totalQuestions} questions across {detail.banks.length} bank{detail.banks.length === 1 ? "" : "s"}, newest first. Click a bank to answer its questions.</p>
          </div>
          {detail.banks.length === 0 ? (
            <p className="text-sm text-slate-500 py-10 text-center border-2 border-dashed border-slate-200 rounded-xl">No question banks yet.</p>
          ) : (
            <ul className="space-y-3">
              {detail.banks.map((b) => (
                <li key={b.id} className="bg-white border border-slate-200 rounded-xl px-5 py-4 flex items-center gap-3">
                  <button onClick={() => openBank(b.id)} className="flex-1 min-w-0 text-left">
                    <span className="font-semibold text-slate-900 block truncate">{b.title}</span>
                    <span className="text-xs text-slate-500">{new Date(b.created_at).toLocaleString()} · {b.question_count} question{b.question_count === 1 ? "" : "s"}</span>
                  </button>
                  <button onClick={() => openBank(b.id)} className="flex items-center gap-1 text-sm font-semibold text-indigo-600 hover:text-indigo-800 shrink-0">
                    <Play className="h-4 w-4" /> Take quiz
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
