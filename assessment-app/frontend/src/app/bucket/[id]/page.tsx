'use client';

import React, { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import InteractiveQuiz from "@/components/InteractiveQuiz";
import TopicEvaluation from "@/components/TopicEvaluation";
import { UploadCloud, Link as LinkIcon, Sparkles, Loader2, Play, FileText, CheckCircle2, XCircle, X, Pencil, Trash2 } from "lucide-react";

type Purpose = "source" | "example";

interface SourceItem {
  id: string;
  title: string;
  source_type: string;
  purpose: Purpose;
  is_concepts_source: boolean;
  source_url?: string | null;
  chunks: number;
  images?: number;
  created_at: string;
}

interface ReferenceSet {
  id: string;
  title: string;
  description?: string | null;
  created_at: string;
  examples_count: number;
}

interface QuestionBank {
  id: string;
  title: string;
  created_at: string;
  question_count: number;
}

interface UploadResult {
  name: string;
  purpose: Purpose;
  status: "success" | "error";
  detail?: string;
}

const PURPOSE_LABEL: Record<Purpose, string> = {
  source: "Source material",
  example: "Example questions",
};

function formatFileSize(bytes: number) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export default function BucketWorkspace() {
  const { id } = useParams();
  const { apiFetch } = useAuth();

  const [activeTab, setActiveTab] = useState<"sources" | "practice">("sources");
  const [banks, setBanks] = useState<QuestionBank[]>([]);
  const [loadingBanks, setLoadingBanks] = useState(false);
  // The bank whose questions are open in the quiz view (null = banks list).
  const [openBankId, setOpenBankId] = useState<string | null>(null);
  const [bankItems, setBankItems] = useState<any[]>([]);
  const [loadingBankItems, setLoadingBankItems] = useState(false);
  // "new" = create a fresh bank on generate; otherwise a bank id to add to.
  const [bankChoice, setBankChoice] = useState("new");
  // Inline rename: which bank is being renamed, and the draft title.
  const [renamingBankId, setRenamingBankId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [bankActionError, setBankActionError] = useState("");
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [urlTitle, setUrlTitle] = useState("");
  const [urlPurpose, setUrlPurpose] = useState<Purpose>("source");
  const [urlError, setUrlError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState("");
  const [questionCount, setQuestionCount] = useState(3);
  const [typology, setTypology] = useState("SCENARIO_VIGNETTE");
  const [injectStimulus, setInjectStimulus] = useState(false);
  const [conceptualUnderstanding, setConceptualUnderstanding] = useState(false);
  const [sourceFlagError, setSourceFlagError] = useState("");
  // "topic": this topic's own example questions (current behaviour).
  // "none": ignore examples, the typology picker decides the type.
  // Otherwise a reference-set id: use that set's examples as the style.
  const [styleChoice, setStyleChoice] = useState("topic");
  const [referenceSets, setReferenceSets] = useState<ReferenceSet[]>([]);

  // Files picked for the next bulk upload, with a purpose per file.
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [filePurposes, setFilePurposes] = useState<Purpose[]>([]);
  const [batchPurpose, setBatchPurpose] = useState<Purpose>("source");
  const [uploadResults, setUploadResults] = useState<UploadResult[]>([]);

  const loadBanks = async (): Promise<QuestionBank[]> => {
    setLoadingBanks(true);
    try {
      const data = await apiFetch(`/api/buckets/${id}/banks`);
      setBanks(data);
      return data as QuestionBank[];
    } catch {
      setBanks([]);
      return [];
    } finally {
      setLoadingBanks(false);
    }
  };

  const openBank = async (bankId: string) => {
    setOpenBankId(bankId);
    setLoadingBankItems(true);
    try {
      const data = await apiFetch(`/api/buckets/${id}/items?bank_id=${bankId}`);
      setBankItems(data);
    } catch {
      setBankItems([]);
    } finally {
      setLoadingBankItems(false);
    }
  };

  const saveRename = async (bankId: string) => {
    const title = renameValue.trim();
    if (!title) return;
    setBankActionError("");
    try {
      const updated = await apiFetch(`/api/banks/${bankId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      setBanks((prev) => prev.map((b) => (b.id === bankId ? updated : b)));
      setRenamingBankId(null);
    } catch (err: any) {
      // Keep the editor open so the draft title is not lost.
      setBankActionError(err?.message || "Rename failed");
    }
  };

  const handleDeleteBank = async (bank: QuestionBank) => {
    if (!window.confirm(`Delete ${bank.title} and all ${bank.question_count} of its questions?`)) return;
    setBankActionError("");
    try {
      await apiFetch(`/api/banks/${bank.id}`, { method: "DELETE" });
      setBanks((prev) => prev.filter((b) => b.id !== bank.id));
      if (openBankId === bank.id) {
        setOpenBankId(null);
        setBankItems([]);
      }
      if (bankChoice === bank.id) setBankChoice("new");
    } catch (err: any) {
      setBankActionError(err?.message || "Delete failed");
    }
  };

  const loadSources = async () => {
    setLoadingSources(true);
    try {
      const data = await apiFetch(`/api/buckets/${id}/sources`);
      setSources(data);
    } catch {
      setSources([]);
    } finally {
      setLoadingSources(false);
    }
  };

  useEffect(() => {
    loadBanks();
    loadSources();
    apiFetch("/api/reference-sets").then(setReferenceSets).catch(() => setReferenceSets([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setSelectedFiles((prev) => [...prev, ...files]);
    setFilePurposes((prev) => [...prev, ...files.map(() => batchPurpose)]);
    setUploadResults([]);
    e.target.value = "";
  };

  // One batch-level choice classifies every file already selected,
  // and becomes the default for files added later in this upload.
  const applyBatchPurpose = (purpose: Purpose) => {
    setBatchPurpose(purpose);
    setFilePurposes((prev) => prev.map(() => purpose));
  };

  const setFilePurpose = (index: number, purpose: Purpose) => {
    setFilePurposes((prev) => prev.map((p, i) => (i === index ? purpose : p)));
  };

  const removeSelectedFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
    setFilePurposes((prev) => prev.filter((_, i) => i !== index));
  };

  const handleBulkUpload = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setUploadResults([]);
    const results: UploadResult[] = [];
    const remainingFiles: File[] = [];
    const remainingPurposes: Purpose[] = [];

    // Group by purpose so each bulk request carries a single purpose.
    // Files are uploaded group by group (never in parallel) so the
    // free-tier backend is not asked to ingest several documents at once.
    const groups: Record<Purpose, File[]> = { source: [], example: [] };
    selectedFiles.forEach((file, i) => {
      groups[filePurposes[i] || batchPurpose].push(file);
    });

    for (const purpose of ["source", "example"] as Purpose[]) {
      const groupFiles = groups[purpose];
      if (groupFiles.length === 0) continue;
      const formData = new FormData();
      groupFiles.forEach((file) => formData.append("files", file));
      formData.append("purpose", purpose);
      try {
        const data = await apiFetch(`/api/buckets/${id}/sources/files`, { method: "POST", body: formData });
        const byName = new Map<string, { status: string; detail?: string }>();
        (data.results || []).forEach((r: any) => byName.set(r.filename, r));
        groupFiles.forEach((file) => {
          const r = byName.get(file.name);
          if (r && r.status === "success") {
            results.push({ name: file.name, purpose, status: "success" });
          } else {
            results.push({ name: file.name, purpose, status: "error", detail: (r && r.detail) || "Upload failed" });
            remainingFiles.push(file);
            remainingPurposes.push(purpose);
          }
        });
      } catch (err: any) {
        groupFiles.forEach((file) => {
          results.push({ name: file.name, purpose, status: "error", detail: err?.message || "Upload failed" });
          remainingFiles.push(file);
          remainingPurposes.push(purpose);
        });
      }
    }

    setUploadResults(results);
    // Keep only the files that failed, so they can be retried.
    setSelectedFiles(remainingFiles);
    setFilePurposes(remainingPurposes);
    setUploading(false);
    await loadSources();
  };

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInput.trim()) return;
    const formData = new FormData();
    formData.append("url", urlInput);
    formData.append("purpose", urlPurpose);
    if (urlTitle) formData.append("title", urlTitle);
    try {
      setUploading(true);
      setUrlError("");
      await apiFetch(`/api/buckets/${id}/sources/url`, { method: "POST", body: formData });
      setUrlInput("");
      setUrlTitle("");
      await loadSources();
    } catch (err: any) {
      const message = err?.message || "Link ingest failed";
      setUrlError(
        message.includes("Failed to fetch")
          ? "The request did not reach the server or timed out. The backend may have been restarting for a deploy. Please wait a moment and try again."
          : message
      );
    } finally {
      setUploading(false);
    }
  };

  const toggleConcepts = async (source: SourceItem) => {
    setSourceFlagError("");
    try {
      const updated = await apiFetch(`/api/buckets/${id}/sources/${source.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_concepts_source: !source.is_concepts_source }),
      });
      setSources((prev) => prev.map((s) => (s.id === source.id ? updated : s)));
    } catch (err: any) {
      setSourceFlagError(err?.message || "Could not update the flag");
    }
  };

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      setGenerateError("");
      const body: any = { count: questionCount, target_typology: typology, inject_external_stimulus: injectStimulus };
      if (conceptualUnderstanding) body.conceptual_understanding = true;
      if (styleChoice === "none") {
        body.use_topic_examples = false;
      } else if (styleChoice !== "topic") {
        body.reference_set_id = styleChoice;
      }
      if (bankChoice !== "new") {
        body.bank_id = bankChoice;
      }
      await apiFetch(`/api/buckets/${id}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const freshBanks = await loadBanks();
      setActiveTab("practice");
      const targetId = bankChoice === "new" ? freshBanks[0]?.id : bankChoice;
      if (targetId) openBank(targetId);
    } catch (err: any) {
      const message = err?.message || "Generation failed";
      setGenerateError(
        message.includes("Failed to fetch")
          ? "The request did not reach the server or timed out. The backend may have been restarting for a deploy, or generation took longer than the connection allows. Please wait a moment and try again."
          : message
      );
    } finally {
      setGenerating(false);
    }
  };

  const sourceCount = sources.filter((s) => s.purpose === "source").length;
  const openBankObj = banks.find((b) => b.id === openBankId) || null;
  const exampleCount = sources.filter((s) => s.purpose === "example").length;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <div className="flex border-b border-slate-200 mb-8 space-x-8">
        <button
          onClick={() => setActiveTab("sources")}
          className={`pb-4 text-sm font-semibold border-b-2 flex items-center space-x-2 ${activeTab === "sources" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500"}`}
        >
          <UploadCloud className="h-4 w-4" />
          <span>Ingest Source Materials</span>
        </button>
        <button
          onClick={() => setActiveTab("practice")}
          className={`pb-4 text-sm font-semibold border-b-2 flex items-center space-x-2 ${activeTab === "practice" ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500"}`}
        >
          <Play className="h-4 w-4" />
          <span>Question Banks ({banks.length})</span>
        </button>
      </div>

      {activeTab === "sources" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-white p-6 rounded-2xl border border-slate-200">
            <h3 className="font-bold text-slate-900 mb-1">Upload Documents</h3>
            <p className="text-xs text-slate-500 mb-4">PDF, Word DOCX, text, and image files (JPG/PNG). Pick several at once.</p>

            <div className="mb-4">
              <p className="text-xs font-semibold text-slate-700 uppercase mb-2">Upload these files as</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => applyBatchPurpose("source")}
                  className={`px-3 py-2.5 text-sm font-semibold rounded-lg border text-left ${batchPurpose === "source" ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-700 border-slate-300 hover:border-indigo-400"}`}
                >
                  All source material
                  <span className={`block text-xs font-normal mt-0.5 ${batchPurpose === "source" ? "text-indigo-100" : "text-slate-500"}`}>Questions are generated from this content</span>
                </button>
                <button
                  type="button"
                  onClick={() => applyBatchPurpose("example")}
                  className={`px-3 py-2.5 text-sm font-semibold rounded-lg border text-left ${batchPurpose === "example" ? "bg-amber-500 text-white border-amber-500" : "bg-white text-slate-700 border-slate-300 hover:border-amber-400"}`}
                >
                  All example questions
                  <span className={`block text-xs font-normal mt-0.5 ${batchPurpose === "example" ? "text-amber-100" : "text-slate-500"}`}>Style examples only, not question content</span>
                </button>
              </div>
            </div>

            <label className="border-2 border-dashed border-slate-300 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:border-indigo-500 bg-slate-50/50">
              <UploadCloud className="h-8 w-8 text-slate-400 mb-2" />
              <span className="text-sm font-medium text-slate-700">Choose files to ingest</span>
              <span className="text-xs text-slate-400 mt-1">You can add more files after picking the first set</span>
              <input type="file" multiple onChange={handleFileSelect} disabled={uploading} className="hidden" accept=".pdf,.docx,.txt,.jpg,.jpeg,.png" />
            </label>

            {selectedFiles.length > 0 && (
              <ul className="mt-4 space-y-2">
                {selectedFiles.map((file, i) => (
                  <li key={file.name + "-" + i} className="flex items-center gap-2 text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                    <FileText className="h-4 w-4 text-slate-400 shrink-0" />
                    <span className="flex-1 min-w-0">
                      <span className="block truncate font-medium text-slate-800">{file.name}</span>
                      <span className="block text-xs text-slate-400">{formatFileSize(file.size)}</span>
                    </span>
                    <label className="text-xs text-slate-500 shrink-0">
                      Use just this file as
                      <select
                        value={filePurposes[i] || batchPurpose}
                        onChange={(e) => setFilePurpose(i, e.target.value as Purpose)}
                        disabled={uploading}
                        className="ml-1 text-xs border rounded-md p-1 bg-white"
                      >
                        <option value="source">Source material</option>
                        <option value="example">Example questions</option>
                      </select>
                    </label>
                    <button type="button" onClick={() => removeSelectedFile(i)} disabled={uploading} aria-label="Remove file" className="text-slate-400 hover:text-slate-700 shrink-0">
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {selectedFiles.length > 0 && (
              <button
                type="button"
                onClick={handleBulkUpload}
                disabled={uploading}
                className="mt-4 w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg flex items-center justify-center space-x-2 disabled:opacity-60"
              >
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
                <span>{uploading ? "Ingesting..." : `Upload ${selectedFiles.length} file${selectedFiles.length === 1 ? "" : "s"}`}</span>
              </button>
            )}

            {uploadResults.length > 0 && (
              <ul className="mt-3 space-y-1">
                {uploadResults.map((r, i) => (
                  <li key={r.name + "-" + i} className={`flex items-start gap-2 text-xs ${r.status === "success" ? "text-emerald-700" : "text-red-700"}`}>
                    {r.status === "success" ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <XCircle className="h-4 w-4 shrink-0" />}
                    <span>
                      {r.status === "success" ? "Ingested" : "Failed"}: {r.name} ({PURPOSE_LABEL[r.purpose]})
                      {r.detail ? ` — ${r.detail}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200">
            <h3 className="font-bold text-slate-900 mb-1">Ingest URLs &amp; YouTube</h3>
            <p className="text-xs text-slate-500 mb-4">YouTube timestamps, Google Docs, or articles.</p>
            <form onSubmit={handleUrlSubmit} className="space-y-3">
              <input type="url" required placeholder="https://..." value={urlInput} onChange={(e) => setUrlInput(e.target.value)} className="w-full px-3.5 py-2 text-sm border rounded-lg" />
              <input type="text" placeholder="Title (optional)" value={urlTitle} onChange={(e) => setUrlTitle(e.target.value)} className="w-full px-3.5 py-2 text-sm border rounded-lg" />
              <label className="flex items-center gap-2 text-xs font-medium text-slate-700">
                Ingest link as
                <select value={urlPurpose} onChange={(e) => setUrlPurpose(e.target.value as Purpose)} className="text-xs border rounded-md p-2 bg-white">
                  <option value="source">Source material</option>
                  <option value="example">Example questions</option>
                </select>
              </label>
              <button type="submit" disabled={uploading} className="w-full py-2.5 bg-slate-900 text-white text-sm font-semibold rounded-lg flex items-center justify-center space-x-2 disabled:opacity-60">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <LinkIcon className="h-4 w-4" />}
                <span>{uploading ? "Ingesting..." : "Ingest Link"}</span>
              </button>
              {urlError && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{urlError}</p>}
            </form>
          </div>

          <div className="md:col-span-2 bg-white p-6 rounded-2xl border border-slate-200">
            <div className="flex items-baseline justify-between mb-1">
              <h3 className="font-bold text-slate-900">Uploaded files</h3>
              <span className="text-xs text-slate-500">{sources.length} total · {sourceCount} source material · {exampleCount} example questions</span>
            </div>
            <p className="text-xs text-slate-500 mb-4">Everything ingested into this topic, with what each file is used for. Questions are generated from source material only. Flag a source — e.g. a course outline or summary slides — as holding the key concepts, and generation can test understanding of them.</p>
            {sourceFlagError && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">{sourceFlagError}</p>}
            {loadingSources ? (
              <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-indigo-600" /></div>
            ) : sources.length === 0 ? (
              <p className="text-sm text-slate-500 py-6 text-center border-2 border-dashed border-slate-200 rounded-xl">No files uploaded yet. Upload documents or ingest a link above.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {sources.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 py-3">
                    <FileText className="h-5 w-5 text-slate-400 shrink-0" />
                    <span className="flex-1 min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-800">{s.title}</span>
                      <span className="block text-xs text-slate-400">
                        {s.source_type} · {s.chunks} chunk{s.chunks === 1 ? "" : "s"}
                        {(s.images ?? 0) > 0 ? ` · ${s.images} image${s.images === 1 ? "" : "s"} extracted` : ""}
                        {s.source_url ? ` · ${s.source_url}` : ""} · {new Date(s.created_at).toLocaleDateString()}
                      </span>
                    </span>
                    <span className={`text-xs font-semibold px-2 py-1 rounded-full shrink-0 ${s.purpose === "example" ? "bg-amber-100 text-amber-800" : "bg-indigo-100 text-indigo-800"}`}>
                      {PURPOSE_LABEL[s.purpose] || "Source material"}
                    </span>
                    {s.purpose === "source" && (
                      <button
                        onClick={() => toggleConcepts(s)}
                        title={s.is_concepts_source ? "Unmark as key concepts" : "Flag as holding the key concepts / objectives for this topic"}
                        className={`text-xs font-semibold px-2 py-1 rounded-full shrink-0 ${s.is_concepts_source ? "bg-emerald-100 text-emerald-800 hover:bg-emerald-200" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}
                      >
                        {s.is_concepts_source ? "Key concepts ✓" : "Mark as key concepts"}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="md:col-span-2 bg-gradient-to-r from-indigo-50 to-purple-50 p-6 rounded-2xl border border-indigo-100">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="font-bold text-slate-900 flex items-center space-x-2"><Sparkles className="h-5 w-5 text-indigo-600" /><span>Generate Practice Items</span></h3>
                <p className="text-xs text-slate-600">Tests Bloom&apos;s Level 3/4, grounded strictly in this bucket&apos;s source material. The style comes from a reference test set if you pick one below, otherwise from this topic&apos;s example questions; the typology picker is the fallback when there are none.</p>
              {styleChoice !== "topic" && styleChoice !== "none" && (
                <p className="text-xs text-amber-700 mt-1">Using the reference style &ldquo;{referenceSets.find((s) => s.id === styleChoice)?.title || "selected set"}&rdquo;.</p>
              )}
              {styleChoice === "topic" && exampleCount > 0 && (
                <p className="text-xs text-amber-700 mt-1">Using the style of {exampleCount} example question file{exampleCount === 1 ? "" : "s"} in this topic.</p>
              )}
              {styleChoice === "none" && (
                <p className="text-xs text-slate-500 mt-1">Ignoring this topic&apos;s example questions — the typology picker below decides the question type.</p>
              )}
              {sources.filter((s) => s.is_concepts_source).length > 0 && (
                <p className="text-xs text-emerald-700 mt-1">Key concepts flagged from: {sources.filter((s) => s.is_concepts_source).map((s) => s.title).join(", ")} — enable &ldquo;Conceptual understanding&rdquo; below to test against them.</p>
              )}
              <p className="text-xs text-slate-500 mt-1">Generation can take a minute or two &mdash; please keep this tab open while it runs.</p>
              </div>
              <button onClick={handleGenerate} disabled={generating} className="px-5 py-2.5 bg-indigo-600 text-white font-semibold text-sm rounded-xl flex items-center space-x-2 disabled:opacity-60">
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                <span>{generating ? "Generating..." : "Generate Items"}</span>
              </button>
            </div>
            {generateError && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">{generateError}</p>}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs pt-4 border-t border-indigo-100">
              <div>
                <label className="font-semibold block mb-1">Reference style</label>
                <select value={styleChoice} onChange={(e) => setStyleChoice(e.target.value)} className="w-full p-2 border rounded-lg bg-white">
                  <option value="topic">This topic&apos;s examples{exampleCount === 0 ? " (none yet)" : ""}</option>
                  <option value="none">None — typology picker only</option>
                  {referenceSets.map((s) => (
                    <option key={s.id} value={s.id}>Reference set: {s.title} ({s.examples_count} file{s.examples_count === 1 ? "" : "s"})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="font-semibold block mb-1">Item Typology</label>
                <select value={typology} onChange={(e) => setTypology(e.target.value)} className="w-full p-2 border rounded-lg bg-white">
                  <option value="SCENARIO_VIGNETTE">Scenario / Clinical Vignette</option>
                  <option value="STIMULUS_INTERPRETATION">Stimulus Interpretation (Quote/Map)</option>
                  <option value="DATA_EVALUATION">Data Table Evaluation</option>
                  <option value="ASSERTION_REASON">Assertion &amp; Reason</option>
                </select>
              </div>
              <div>
                <label className="font-semibold block mb-1">Question Count</label>
                <input type="number" min={1} max={10} value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} className="w-full p-2 border rounded-lg bg-white" />
              </div>
              <div>
                <label className="font-semibold block mb-1">Save to bank</label>
                <select value={bankChoice} onChange={(e) => setBankChoice(e.target.value)} className="w-full p-2 border rounded-lg bg-white">
                  <option value="new">New bank</option>
                  {banks.map((b) => (
                    <option key={b.id} value={b.id}>{b.title} — {new Date(b.created_at).toLocaleDateString()} ({b.question_count} question{b.question_count === 1 ? "" : "s"})</option>
                  ))}
                </select>
              </div>
              <div className="flex items-center space-x-2 pt-5">
                <input type="checkbox" id="stimulusToggle" checked={injectStimulus} onChange={(e) => setInjectStimulus(e.target.checked)} className="h-4 w-4 rounded text-indigo-600" />
                <label htmlFor="stimulusToggle" className="font-medium">Fetch External Stimulus (Map / Quote)</label>
              </div>
              <div className="flex items-start space-x-2 pt-5">
                <input type="checkbox" id="conceptualToggle" checked={conceptualUnderstanding} onChange={(e) => setConceptualUnderstanding(e.target.checked)} className="h-4 w-4 rounded text-indigo-600 mt-0.5" />
                <label htmlFor="conceptualToggle" className="font-medium">Conceptual understanding
                  <span className="block font-normal text-slate-500">Guide generation by key concepts &amp; objectives{sources.filter((s) => s.is_concepts_source).length > 0 ? " from your flagged source(s)" : " — identified automatically from your sources"}.</span>
                </label>
              </div>
            </div>
          </div>
        </div>
      ) : openBankObj ? (
        <div>
          <button onClick={() => setOpenBankId(null)} className="text-sm font-semibold text-indigo-600 hover:text-indigo-800 mb-4">&larr; Back to banks</button>
          <div className="mb-6">
            <h3 className="font-bold text-slate-900 text-lg">{openBankObj.title}</h3>
            <p className="text-xs text-slate-500">{new Date(openBankObj.created_at).toLocaleString()} · {openBankObj.question_count} question{openBankObj.question_count === 1 ? "" : "s"}</p>
          </div>
          {loadingBankItems ? <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div> : <InteractiveQuiz items={bankItems} bucketId={id as string} bankId={openBankId} />}
        </div>
      ) : loadingBanks ? (
        <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div>
      ) : banks.length === 0 ? (
        <p className="text-sm text-slate-500 py-10 text-center border-2 border-dashed border-slate-200 rounded-xl">No question banks yet. Generate items from the Sources tab and they will land in a bank here.</p>
      ) : (
        <div>
          <TopicEvaluation bucketId={id as string} />
          <div className="mb-4">
            <h3 className="font-bold text-slate-900">Question Banks</h3>
            <p className="text-xs text-slate-500">{banks.reduce((n, b) => n + b.question_count, 0)} questions across {banks.length} bank{banks.length === 1 ? "" : "s"}, newest first. Click a bank to answer its questions.</p>
          </div>
          {bankActionError && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mb-4">{bankActionError}</p>}
          <ul className="space-y-3">
            {banks.map((b) => (
              <li key={b.id} className="bg-white border border-slate-200 rounded-xl px-5 py-4 flex items-center gap-3">
                {renamingBankId === b.id ? (
                  <span className="flex-1 min-w-0 flex items-center gap-2">
                    <input
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") saveRename(b.id); if (e.key === "Escape") setRenamingBankId(null); }}
                      autoFocus
                      aria-label="Bank title"
                      className="flex-1 min-w-0 px-2 py-1 text-sm font-medium border rounded-lg"
                    />
                    <button onClick={() => saveRename(b.id)} className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 shrink-0">Save</button>
                    <button onClick={() => setRenamingBankId(null)} className="text-xs font-semibold text-slate-500 hover:text-slate-700 shrink-0">Cancel</button>
                  </span>
                ) : (
                  <button onClick={() => openBank(b.id)} className="flex-1 min-w-0 text-left flex items-center gap-3 hover:opacity-80">
                    <Play className="h-5 w-5 text-indigo-600 shrink-0" />
                    <span className="flex-1 min-w-0">
                      <span className="block truncate font-semibold text-slate-900">{b.title}</span>
                      <span className="block text-xs text-slate-500">{new Date(b.created_at).toLocaleString()} · {b.question_count} question{b.question_count === 1 ? "" : "s"}</span>
                    </span>
                    <span className="text-sm font-semibold text-indigo-600 shrink-0">Take quiz &rarr;</span>
                  </button>
                )}
                {renamingBankId !== b.id && (
                  <span className="flex items-center gap-1 shrink-0">
                    <button onClick={() => { setRenamingBankId(b.id); setRenameValue(b.title); }} aria-label={`Rename ${b.title}`} title="Rename bank" className="p-1.5 text-slate-400 hover:text-indigo-600 rounded-lg">
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button onClick={() => handleDeleteBank(b)} aria-label={`Delete ${b.title}`} title="Delete bank" className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
