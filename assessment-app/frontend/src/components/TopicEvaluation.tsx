'use client';

import React, { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { Loader2, RefreshCw, TrendingUp, TrendingDown, Minus, Target, Lightbulb, ListChecks } from "lucide-react";

interface ConceptAssessment {
  concept: string;
  verdict: "strength" | "weakness" | "developing";
  correct: number;
  total: number;
  evidence: string;
  recommendation: string;
}

interface EvaluationBody {
  summary: string;
  concepts: ConceptAssessment[];
  strategy_observations: string[];
  strategy_recommendations: string[];
  next_steps: string[];
}

interface EvaluationData {
  sufficient: boolean;
  attempts: number;
  minimum: number;
  correct: number | null;
  accuracy: number | null;
  evaluation: EvaluationBody | null;
}

const VERDICT_STYLE: Record<string, { label: string; icon: React.ReactNode; ring: string }> = {
  strength: { label: "Strength", icon: <TrendingUp className="h-4 w-4 text-emerald-600" />, ring: "border-emerald-200 bg-emerald-50/50" },
  weakness: { label: "Needs work", icon: <TrendingDown className="h-4 w-4 text-rose-600" />, ring: "border-rose-200 bg-rose-50/50" },
  developing: { label: "Developing", icon: <Minus className="h-4 w-4 text-amber-600" />, ring: "border-amber-200 bg-amber-50/50" },
};

export default function TopicEvaluation({ bucketId }: { bucketId: string }) {
  const { apiFetch } = useAuth();
  const [data, setData] = useState<EvaluationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const load = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setLoading(true);
    setError("");
    try {
      const res = await apiFetch(`/api/buckets/${bucketId}/evaluation`);
      setData(res);
    } catch (e: any) {
      setError(e?.message || "Could not load the topic evaluation.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, [bucketId]);

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-5 mb-6 flex items-center gap-2 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin text-indigo-600" /> Checking your topic evaluation…
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-5 mb-6">
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        <button onClick={() => load()} className="mt-3 text-sm font-semibold text-indigo-600 hover:text-indigo-800">Try again</button>
      </div>
    );
  }

  if (!data) return null;

  if (!data.sufficient) {
    const remaining = data.minimum - data.attempts;
    const pct = Math.min(100, Math.round((data.attempts / data.minimum) * 100));
    return (
      <div className="bg-white rounded-xl border border-slate-200 p-5 mb-6">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-indigo-600" />
          <h3 className="font-bold text-slate-900">Topic evaluation</h3>
        </div>
        <p className="text-sm text-slate-600 mt-2">
          {data.attempts} of {data.minimum} questions answered. Answer {remaining} more {remaining === 1 ? "question" : "questions"} in this topic to unlock an evaluation of your strengths and weaknesses — by concept and by test-taking strategy.
        </p>
        <div className="mt-3 h-2 rounded-full bg-slate-100 overflow-hidden">
          <div className="h-full bg-indigo-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  }

  const ev = data.evaluation!;
  const accuracyPct = data.accuracy !== null ? Math.round(data.accuracy * 100) : null;
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 sm:p-6 mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-indigo-600" />
          <h3 className="font-bold text-slate-900">Topic evaluation</h3>
          <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700">
            {data.correct} / {data.attempts} correct{accuracyPct !== null ? ` · ${accuracyPct}%` : ""}
          </span>
        </div>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          {refreshing ? "Re-running…" : "Re-run with latest answers"}
        </button>
      </div>

      <p className="text-sm text-slate-700 leading-relaxed mt-3">{ev.summary}</p>

      {ev.concepts.length > 0 && (
        <div className="mt-5 space-y-3">
          <span className="font-semibold uppercase tracking-wider text-slate-500 text-xs block">By concept</span>
          {ev.concepts.map((c) => {
            const style = VERDICT_STYLE[c.verdict] || VERDICT_STYLE.developing;
            return (
              <div key={c.concept} className={`rounded-xl border p-4 ${style.ring}`}>
                <div className="flex flex-wrap items-center gap-2">
                  {style.icon}
                  <span className="font-semibold text-sm text-slate-900">{c.concept}</span>
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-white border border-slate-200 text-slate-600">{style.label}{c.total > 0 ? ` · ${c.correct}/${c.total}` : ""}</span>
                </div>
                <p className="text-sm text-slate-700 mt-1.5">{c.evidence}</p>
                <p className="text-sm text-slate-700 mt-1"><span className="font-semibold">Do this: </span>{c.recommendation}</p>
              </div>
            );
          })}
        </div>
      )}

      {ev.strategy_observations.length > 0 && (
        <div className="mt-5">
          <span className="font-semibold uppercase tracking-wider text-slate-500 text-xs block">Test-taking strategy — what your answers show</span>
          <ul className="mt-2 space-y-1.5">
            {ev.strategy_observations.map((o, i) => (
              <li key={i} className="text-sm text-slate-700 flex items-start gap-2">
                <Lightbulb className="h-4 w-4 text-amber-600 flex-shrink-0 mt-0.5" />
                <span>{o}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {ev.strategy_recommendations.length > 0 && (
        <div className="mt-4">
          <span className="font-semibold uppercase tracking-wider text-slate-500 text-xs block">Strategy to practise</span>
          <ul className="mt-2 space-y-1.5">
            {ev.strategy_recommendations.map((r, i) => (
              <li key={i} className="text-sm text-slate-700 list-disc ml-5">{r}</li>
            ))}
          </ul>
        </div>
      )}

      {ev.next_steps.length > 0 && (
        <div className="mt-4">
          <span className="font-semibold uppercase tracking-wider text-slate-500 text-xs flex items-center gap-1.5">
            <ListChecks className="h-4 w-4" /> Next steps
          </span>
          <ul className="mt-2 space-y-1.5">
            {ev.next_steps.map((s, i) => (
              <li key={i} className="text-sm text-slate-700 list-disc ml-5">{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
