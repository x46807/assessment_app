'use client';

import React, { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import InteractiveQuiz from "@/components/InteractiveQuiz";
import { UploadCloud, Link as LinkIcon, Sparkles, Loader2, Play } from "lucide-react";

export default function BucketWorkspace() {
  const { id } = useParams();
  const { apiFetch } = useAuth();

  const [activeTab, setActiveTab] = useState<"sources" | "practice">("sources");
  const [items, setItems] = useState<any[]>([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const [urlTitle, setUrlTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [questionCount, setQuestionCount] = useState(3);
  const [typology, setTypology] = useState("SCENARIO_VIGNETTE");
  const [injectStimulus, setInjectStimulus] = useState(false);

  useEffect(() => {
    setLoadingItems(true);
    apiFetch(`/api/buckets/${id}/items`).then(setItems).finally(() => setLoadingItems(false));
  }, [id]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      setUploading(true);
      await apiFetch(`/api/buckets/${id}/sources/file`, { method: "POST", body: formData });
      alert(`Ingested: ${file.name}`);
      e.target.value = "";
    } finally {
      setUploading(false);
    }
  };

  const handleUrlSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInput.trim()) return;
    const formData = new FormData();
    formData.append("url", urlInput);
    if (urlTitle) formData.append("title", urlTitle);
    try {
      setUploading(true);
      await apiFetch(`/api/buckets/${id}/sources/url`, { method: "POST", body: formData });
      setUrlInput("");
      setUrlTitle("");
      alert("URL ingested and anchored!");
    } finally {
      setUploading(false);
    }
  };

  const handleGenerate = async () => {
    try {
      setGenerating(true);
      const newItems = await apiFetch(`/api/buckets/${id}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count: questionCount, target_typology: typology, inject_external_stimulus: injectStimulus }),
      });
      setItems((prev) => [...newItems, ...prev]);
      setActiveTab("practice");
    } finally {
      setGenerating(false);
    }
  };

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
          <span>Interactive Test Items ({items.length})</span>
        </button>
      </div>

      {activeTab === "sources" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-white p-6 rounded-2xl border border-slate-200">
            <h3 className="font-bold text-slate-900 mb-1">Upload Documents</h3>
            <p className="text-xs text-slate-500 mb-4">PDF, Word DOCX, and text files.</p>
            <label className="border-2 border-dashed border-slate-300 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:border-indigo-500 bg-slate-50/50">
              <UploadCloud className="h-8 w-8 text-slate-400 mb-2" />
              <span className="text-sm font-medium text-slate-700">Choose file to ingest</span>
              <input type="file" onChange={handleFileUpload} disabled={uploading} className="hidden" accept=".pdf,.docx,.txt" />
            </label>
            {uploading && <div className="text-xs font-medium text-indigo-600 mt-3 flex items-center space-x-2"><Loader2 className="h-4 w-4 animate-spin" /><span>Anchoring...</span></div>}
          </div>

          <div className="bg-white p-6 rounded-2xl border border-slate-200">
            <h3 className="font-bold text-slate-900 mb-1">Ingest URLs & YouTube</h3>
            <p className="text-xs text-slate-500 mb-4">YouTube timestamps, Google Docs, or articles.</p>
            <form onSubmit={handleUrlSubmit} className="space-y-3">
              <input type="url" required placeholder="https://..." value={urlInput} onChange={(e) => setUrlInput(e.target.value)} className="w-full px-3.5 py-2 text-sm border rounded-lg" />
              <input type="text" placeholder="Title (optional)" value={urlTitle} onChange={(e) => setUrlTitle(e.target.value)} className="w-full px-3.5 py-2 text-sm border rounded-lg" />
              <button type="submit" disabled={uploading} className="w-full py-2.5 bg-slate-900 text-white text-sm font-semibold rounded-lg flex items-center justify-center space-x-2">
                <LinkIcon className="h-4 w-4" />
                <span>Ingest Link</span>
              </button>
            </form>
          </div>

          <div className="md:col-span-2 bg-gradient-to-r from-indigo-50 to-purple-50 p-6 rounded-2xl border border-indigo-100">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="font-bold text-slate-900 flex items-center space-x-2"><Sparkles className="h-5 w-5 text-indigo-600" /><span>Generate Practice Items</span></h3>
                <p className="text-xs text-slate-600">Tests Bloom's Level 3/4 grounded strictly in this bucket's content.</p>
              </div>
              <button onClick={handleGenerate} disabled={generating} className="px-5 py-2.5 bg-indigo-600 text-white font-semibold text-sm rounded-xl flex items-center space-x-2">
                {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                <span>{generating ? "Generating..." : "Generate Items"}</span>
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs pt-4 border-t border-indigo-100">
              <div>
                <label className="font-semibold block mb-1">Item Typology</label>
                <select value={typology} onChange={(e) => setTypology(e.target.value)} className="w-full p-2 border rounded-lg bg-white">
                  <option value="SCENARIO_VIGNETTE">Scenario / Clinical Vignette</option>
                  <option value="STIMULUS_INTERPRETATION">Stimulus Interpretation (Quote/Map)</option>
                  <option value="DATA_EVALUATION">Data Table Evaluation</option>
                  <option value="ASSERTION_REASON">Assertion & Reason</option>
                </select>
              </div>
              <div>
                <label className="font-semibold block mb-1">Question Count</label>
                <input type="number" min={1} max={10} value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} className="w-full p-2 border rounded-lg bg-white" />
              </div>
              <div className="flex items-center space-x-2 pt-5">
                <input type="checkbox" id="stimulusToggle" checked={injectStimulus} onChange={(e) => setInjectStimulus(e.target.checked)} className="h-4 w-4 rounded text-indigo-600" />
                <label htmlFor="stimulusToggle" className="font-medium">Fetch External Stimulus (Map / Quote)</label>
              </div>
            </div>
          </div>
        </div>
      ) : (
        loadingItems ? <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div> : <InteractiveQuiz items={items} />
      )}
    </div>
  );
}
