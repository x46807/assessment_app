'use client';

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { FolderPlus, Layers, ArrowRight, Loader2 } from "lucide-react";

export default function Dashboard() {
  const { user, apiFetch } = useAuth();
  const [buckets, setBuckets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (user) {
      apiFetch("/api/buckets").then(setBuckets).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [user]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    await apiFetch("/api/buckets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, description }),
    });
    setTitle("");
    setDescription("");
    setIsModalOpen(false);
    apiFetch("/api/buckets").then(setBuckets);
  };

  if (!user) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-24 text-center">
        <h1 className="text-4xl font-extrabold text-slate-900 tracking-tight mb-4">Psychometric Test Generation Powered by AI</h1>
        <p className="text-slate-600 mb-8 max-w-xl mx-auto">Create grounded practice items anchored directly to your documents with verifiable citations.</p>
        <p className="text-sm font-medium text-indigo-700 bg-indigo-50 border border-indigo-100 inline-block px-4 py-2 rounded-lg">Sign in with Google in the navbar to begin.</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      <div className="flex justify-between items-center pb-8 border-b border-slate-200">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Topic Buckets</h1>
          <p className="text-sm text-slate-500">Organize your course materials and generated practice questions.</p>
        </div>
        <button onClick={() => setIsModalOpen(true)} className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold px-4 py-2.5 rounded-lg shadow-sm transition-colors">
          <FolderPlus className="h-4 w-4" />
          <span>New Topic Bucket</span>
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-20"><Loader2 className="h-8 w-8 animate-spin text-indigo-600" /></div>
      ) : buckets.length === 0 ? (
        <div className="text-center py-20 border-2 border-dashed border-slate-200 rounded-2xl mt-8">
          <Layers className="h-10 w-10 text-slate-400 mx-auto mb-2" />
          <h3 className="text-base font-semibold text-slate-800">No topic buckets yet</h3>
          <p className="text-sm text-slate-500">Create your first topic bucket to upload sources and build tests.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-8">
          {buckets.map((b) => (
            <Link key={b.id} href={`/bucket/${b.id}`} className="block bg-white rounded-xl border border-slate-200 p-6 hover:border-indigo-500 hover:shadow-md transition-all group">
              <h3 className="font-semibold text-lg text-slate-900 group-hover:text-indigo-600">{b.title}</h3>
              <p className="text-sm text-slate-500 line-clamp-2 mt-2 h-10">{b.description || "No description."}</p>
              <div className="flex justify-between text-xs text-slate-500 border-t border-slate-100 pt-4 mt-4">
                <span>{b.sources_count} Sources</span>
                <span>{b.items_count} Questions</span>
                <ArrowRight className="h-4 w-4 text-slate-400 group-hover:text-indigo-600" />
              </div>
            </Link>
          ))}
        </div>
      )}

      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl border border-slate-100">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Create New Topic Bucket</h3>
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">Title *</label>
                <input required placeholder="e.g. The Middle Ages" value={title} onChange={(e) => setTitle(e.target.value)} className="w-full px-3.5 py-2 border rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">Description</label>
                <textarea rows={3} placeholder="Topic description..." value={description} onChange={(e) => setDescription(e.target.value)} className="w-full px-3.5 py-2 border rounded-lg text-sm" />
              </div>
              <div className="flex justify-end space-x-3 pt-2">
                <button type="button" onClick={() => setIsModalOpen(false)} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
                <button type="submit" className="px-4 py-2 text-sm font-semibold bg-indigo-600 text-white rounded-lg">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
