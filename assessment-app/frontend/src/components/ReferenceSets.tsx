'use client';

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { UploadCloud, FileText, Loader2, Trash2, Plus, ChevronDown, ChevronRight } from "lucide-react";

interface ReferenceSet {
  id: string;
  title: string;
  description?: string | null;
  created_at: string;
  examples_count: number;
  source_count: number;
  is_source_enriched: boolean;
}

interface ReferenceExample {
  id: string;
  title: string;
  source_type: string;
  purpose: string;
  source_url?: string | null;
  chunks: number;
  created_at: string;
}

export default function ReferenceSets() {
  const { apiFetch } = useAuth();
  const [sets, setSets] = useState<ReferenceSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [examples, setExamples] = useState<Record<string, ReferenceExample[]>>({});
  const [uploading, setUploading] = useState<Record<string, boolean>>({});
  // Per-set choice for the next upload: example questions, or the
  // source material the questions were written about.
  const [uploadPurpose, setUploadPurpose] = useState<Record<string, "example" | "source">>({});
  const [error, setError] = useState("");

  const loadSets = async () => {
    setLoading(true);
    try {
      setSets(await apiFetch("/api/reference-sets"));
    } catch {
      setSets([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadExamples = async (setId: string) => {
    try {
      const data = await apiFetch(`/api/reference-sets/${setId}/examples`);
      setExamples((prev) => ({ ...prev, [setId]: data }));
    } catch {
      setExamples((prev) => ({ ...prev, [setId]: [] }));
    }
  };

  const toggleExpand = (setId: string) => {
    setExpanded((prev) => {
      const next = { ...prev, [setId]: !prev[setId] };
      if (next[setId] && !examples[setId]) loadExamples(setId);
      return next;
    });
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    const created = await apiFetch("/api/reference-sets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: newTitle.trim(), description: newDescription || null }),
    });
    setNewTitle("");
    setNewDescription("");
    setShowCreate(false);
    setSets((prev) => [...prev, created]);
  };

  const handleUpload = async (setId: string, files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading((prev) => ({ ...prev, [setId]: true }));
    setError("");
    try {
      const formData = new FormData();
      Array.from(files).forEach((f) => formData.append("files", f));
      formData.append("purpose", uploadPurpose[setId] || "example");
      const data = await apiFetch(`/api/reference-sets/${setId}/examples/files`, { method: "POST", body: formData });
      const failed = (data.results || []).filter((r: any) => r.status !== "success");
      if (failed.length > 0) {
        setError(failed.map((r: any) => `${r.filename}: ${r.detail || "upload failed"}`).join("; "));
      }
      await loadExamples(setId);
      await loadSets();
    } catch (err: any) {
      setError(err?.message || "Upload failed");
    } finally {
      setUploading((prev) => ({ ...prev, [setId]: false }));
    }
  };

  const handleDeleteExample = async (setId: string, exampleId: string) => {
    await apiFetch(`/api/reference-sets/${setId}/examples/${exampleId}`, { method: "DELETE" });
    await loadExamples(setId);
    await loadSets();
  };

  const handleDeleteSet = async (setId: string) => {
    if (!window.confirm("Delete this reference set and all its files?")) return;
    await apiFetch(`/api/reference-sets/${setId}`, { method: "DELETE" });
    setSets((prev) => prev.filter((s) => s.id !== setId));
  };

  return (
    <div className="mt-12">
      <div className="flex justify-between items-center pb-6 border-b border-slate-200">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Reference Test Sets</h2>
          <p className="text-sm text-slate-500">Upload a set of example questions once, then reuse its style when generating in any topic — no need to re-upload the examples for every topic. You can also upload the source material the questions were written about, so the model learns how questions connect to that kind of source.</p>
        </div>
        <button onClick={() => setShowCreate(true)} className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2.5 rounded-lg shadow-sm transition-colors shrink-0">
          <Plus className="h-4 w-4" />
          <span>New Reference Set</span>
        </button>
      </div>

      {error && <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 mt-4">{error}</p>}

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div>
      ) : sets.length === 0 ? (
        <div className="text-center py-12 border-2 border-dashed border-slate-200 rounded-2xl mt-6">
          <FileText className="h-10 w-10 text-slate-400 mx-auto mb-2" />
          <h3 className="text-base font-semibold text-slate-800">No reference sets yet</h3>
          <p className="text-sm text-slate-500">Create one, upload its example questions, then pick it as the reference style when generating in any topic.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-6">
          {sets.map((s) => (
            <div key={s.id} className="bg-white rounded-xl border border-slate-200 p-6">
              <div className="flex items-start justify-between gap-2">
                <button onClick={() => toggleExpand(s.id)} className="flex items-start gap-2 text-left flex-1 min-w-0">
                  {expanded[s.id] ? <ChevronDown className="h-4 w-4 text-slate-400 mt-1 shrink-0" /> : <ChevronRight className="h-4 w-4 text-slate-400 mt-1 shrink-0" />}
                  <span>
                    <span className="block font-semibold text-slate-900 truncate">{s.title}</span>
                    <span className="block text-xs text-slate-500 mt-1">{s.examples_count} example file{s.examples_count === 1 ? "" : "s"}{s.source_count > 0 ? ` · ${s.source_count} source file${s.source_count === 1 ? "" : "s"}` : ""}</span>
                    {s.is_source_enriched && (
                      <span className="inline-block mt-1.5 text-[11px] font-semibold bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">Source-enriched</span>
                    )}
                  </span>
                </button>
                <button onClick={() => handleDeleteSet(s.id)} aria-label="Delete reference set" className="text-slate-400 hover:text-red-600 shrink-0">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
              {s.description && <p className="text-sm text-slate-500 mt-2 line-clamp-2">{s.description}</p>}

              <div className="mt-4 flex items-center gap-2">
                <label htmlFor={`purpose-${s.id}`} className="text-xs font-medium text-slate-600 shrink-0">Upload files as</label>
                <select
                  id={`purpose-${s.id}`}
                  value={uploadPurpose[s.id] || "example"}
                  onChange={(e) => setUploadPurpose((prev) => ({ ...prev, [s.id]: e.target.value as "example" | "source" }))}
                  disabled={uploading[s.id]}
                  className="flex-1 min-w-0 text-xs border rounded-lg px-2 py-1.5 bg-white"
                >
                  <option value="example">Example questions</option>
                  <option value="source">Source material</option>
                </select>
              </div>
              <label className="mt-2 border-2 border-dashed border-slate-300 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer hover:border-indigo-500 bg-slate-50/50">
                <UploadCloud className="h-6 w-6 text-slate-400 mb-1" />
                <span className="text-xs font-medium text-slate-700">{uploading[s.id] ? "Ingesting..." : (uploadPurpose[s.id] === "source" ? "Upload source material" : "Upload example questions")}</span>
                <span className="text-xs text-slate-400">PDF, Word, text, or image files</span>
                <input type="file" multiple disabled={uploading[s.id]} className="hidden" accept=".pdf,.docx,.txt,.jpg,.jpeg,.png" onChange={(e) => { handleUpload(s.id, e.target.files); e.target.value = ""; }} />
              </label>
              <p className="text-[11px] text-slate-400 mt-2">Source material is the content the example questions were written about — uploading it makes this set source-enriched, so generation learns what kinds of questions that kind of source gives rise to.</p>

              {expanded[s.id] && (
                <ul className="mt-4 space-y-2">
                  {(examples[s.id] || []).length === 0 ? (
                    <li className="text-xs text-slate-500">No example files in this set yet.</li>
                  ) : (
                    (examples[s.id] || []).map((ex) => (
                      <li key={ex.id} className="flex items-center gap-2 text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
                        <FileText className="h-4 w-4 text-slate-400 shrink-0" />
                        <span className="flex-1 min-w-0">
                          <span className="block truncate font-medium text-slate-800">{ex.title}</span>
                          <span className="block text-xs text-slate-400">{ex.source_type} · {ex.chunks} chunk{ex.chunks === 1 ? "" : "s"}</span>
                        </span>
                        {ex.purpose === "source" ? (
                          <span className="text-[11px] font-semibold bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full shrink-0">Source material</span>
                        ) : (
                          <span className="text-[11px] font-semibold bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full shrink-0">Example questions</span>
                        )}
                        <button onClick={() => handleDeleteExample(s.id, ex.id)} aria-label="Delete example file" className="text-slate-400 hover:text-red-600 shrink-0">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </li>
                    ))
                  )}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-100">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Create Reference Test Set</h3>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">Title *</label>
                <input required placeholder="e.g. AP History style" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} className="w-full px-3.5 py-2 border rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">Description</label>
                <textarea rows={3} placeholder="What kind of questions does this set model?" value={newDescription} onChange={(e) => setNewDescription(e.target.value)} className="w-full px-3.5 py-2 border rounded-lg text-sm" />
              </div>
              <div className="flex justify-end space-x-3 pt-2">
                <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm font-semibold bg-indigo-600 text-white rounded-lg">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
