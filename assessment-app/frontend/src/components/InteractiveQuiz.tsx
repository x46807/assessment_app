'use client';

import React, { useState, useRef } from "react";
import StimulusViewer from "./StimulusViewer";
import { CheckCircle2, XCircle, Clock, FileText, ChevronDown, ChevronUp, Lightbulb, Loader2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export interface QuestionItem {
  id: string;
  catalog_typology: string;
  bloom_level: string;
  stem: string;
  stimulus?: { stimulus_type: string; content: string; attribution_or_context: string };
  options: { label: string; text: string }[];
  correct_option: string;
  pedagogical_feedback: string;
  distractor_rationales: Record<string, string>;
  citation: { source_title: string; source_file?: string; location_type: "page" | "timestamp" | "section" | "line"; location_value: string; verbatim_grounding_quote: string };
}

interface DetailedFeedback {
  concept_paragraph: string;
  key_concepts: string[];
  strategy_tip: string;
}

export default function InteractiveQuiz({ items, bucketId, bankId }: { items: QuestionItem[]; bucketId: string; bankId?: string | null }) {
  const { apiFetch } = useAuth();
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, string>>({});
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  // When the student first picks an option on each question, so the
  // attempt records how long they deliberated (first choice to submit).
  const firstChoiceAt = useRef<Record<number, number>>({});
  // Tier 1 detailed feedback, per question.
  const [detailedOpen, setDetailedOpen] = useState<Record<number, boolean>>({});
  const [detailed, setDetailed] = useState<Record<number, DetailedFeedback | null>>({});
  const [detailedLoading, setDetailedLoading] = useState<Record<number, boolean>>({});
  const [detailedError, setDetailedError] = useState<Record<number, string>>({});

  const choose = (idx: number, label: string) => {
    if (firstChoiceAt.current[idx] === undefined) firstChoiceAt.current[idx] = Date.now();
    setSelectedAnswers((prev) => ({ ...prev, [idx]: label }));
  };

  const submit = (idx: number) => {
    const item = items[idx];
    const selected = selectedAnswers[idx];
    if (!selected) return;
    setRevealed((prev) => ({ ...prev, [idx]: true }));
    // Record the attempt for the topic evaluation. It must never block
    // or break the quiz, so it runs in the background and a failure is
    // only logged -- the evaluation simply will not count that answer.
    const started = firstChoiceAt.current[idx];
    const timeSpent = started !== undefined ? Math.round((Date.now() - started) / 1000) : null;
    apiFetch(`/api/buckets/${bucketId}/attempts`, {
      method: "POST",
      body: JSON.stringify({ question_id: item.id, selected_option: selected, time_spent_seconds: timeSpent, bank_id: bankId || null }),
    }).catch((e) => console.warn("[Quiz] attempt was not recorded:", e));
  };

  const toggleDetailed = async (idx: number) => {
    const open = !detailedOpen[idx];
    setDetailedOpen((prev) => ({ ...prev, [idx]: open }));
    if (!open || detailed[idx]) return;
    setDetailedLoading((prev) => ({ ...prev, [idx]: true }));
    setDetailedError((prev) => ({ ...prev, [idx]: "" }));
    try {
      const fb = await apiFetch(`/api/items/${items[idx].id}/detailed-feedback`);
      setDetailed((prev) => ({ ...prev, [idx]: fb }));
    } catch (e: any) {
      setDetailedError((prev) => ({ ...prev, [idx]: e?.message || "Could not load detailed feedback." }));
    } finally {
      setDetailedLoading((prev) => ({ ...prev, [idx]: false }));
    }
  };

  return (
    <div className="space-y-8">
      {items.map((item, idx) => {
        const isAnswered = !!selectedAnswers[idx];
        const isRevealed = !!revealed[idx];
        const isCorrect = selectedAnswers[idx] === item.correct_option;
        const fb = detailed[idx];

        return (
          <div key={idx} className="bg-white rounded-xl border border-slate-200 p-6 sm:p-8 shadow-sm">
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">Item {idx + 1}</span>
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700">{item.catalog_typology}</span>
              <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700">{item.bloom_level}</span>
            </div>

            {item.stimulus && <StimulusViewer stimulus={item.stimulus} />}
            <h3 className="text-base sm:text-lg font-semibold text-slate-900 mb-6 leading-relaxed">{item.stem}</h3>

            <div className="space-y-3 mb-6">
              {item.options.map((opt) => (
                <button
                  key={opt.label}
                  disabled={isRevealed}
                  onClick={() => choose(idx, opt.label)}
                  className={`w-full text-left p-4 rounded-xl border transition-all flex items-start space-x-3.5 ${
                    isRevealed
                      ? opt.label === item.correct_option
                        ? "border-emerald-500 bg-emerald-50/50 text-emerald-950 font-medium"
                        : selectedAnswers[idx] === opt.label
                        ? "border-rose-400 bg-rose-50/50 text-rose-950"
                        : "border-slate-200 opacity-60"
                      : selectedAnswers[idx] === opt.label
                      ? "border-indigo-600 bg-indigo-50/40 text-indigo-950 font-medium ring-1 ring-indigo-600"
                      : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <span className="w-6 h-6 rounded-full border border-current flex items-center justify-center text-xs font-bold flex-shrink-0">
                    {opt.label}
                  </span>
                  <span className="text-sm pt-0.5">{opt.text}</span>
                </button>
              ))}
            </div>

            {!isRevealed && (
              <button
                disabled={!isAnswered}
                onClick={() => submit(idx)}
                className="px-5 py-2.5 rounded-lg text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 transition-colors"
              >
                Submit Answer
              </button>
            )}

            {isRevealed && (
              <div className="mt-6 pt-6 border-t border-slate-100 space-y-4">
                <div className={`p-4 rounded-xl flex items-start space-x-3 ${isCorrect ? "bg-emerald-50 text-emerald-900" : "bg-rose-50 text-rose-900"}`}>
                  {isCorrect ? <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5 flex-shrink-0" /> : <XCircle className="h-5 w-5 text-rose-600 mt-0.5 flex-shrink-0" />}
                  <div>
                    <p className="font-semibold text-sm">{isCorrect ? "Correct!" : `Incorrect (Correct Option is ${item.correct_option})`}</p>
                    <p className="text-sm mt-1">{item.pedagogical_feedback}</p>
                  </div>
                </div>

                <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 text-xs space-y-2">
                  <span className="font-semibold uppercase tracking-wider text-slate-500 block">Distractor Rationales:</span>
                  {Object.entries(item.distractor_rationales).map(([k, rat]) => (
                    <div key={k} className="flex space-x-2 text-slate-700">
                      <span className="font-bold">Option {k}:</span>
                      <span>{rat}</span>
                    </div>
                  ))}
                </div>

                <div className="flex items-start space-x-3 text-xs bg-amber-50/60 border border-amber-200/60 rounded-xl p-4 text-amber-950">
                  {item.citation.location_type === "timestamp" ? <Clock className="h-4 w-4 text-amber-700 flex-shrink-0" /> : <FileText className="h-4 w-4 text-amber-700 flex-shrink-0" />}
                  <div>
                    <p className="font-bold text-amber-900">{item.citation.source_file || item.citation.source_title}</p>
                    <p className="text-amber-800 mt-0.5">{item.citation.location_value}</p>
                    <p className="italic text-slate-700 bg-white/70 p-2.5 rounded border border-amber-100 mt-1">"{item.citation.verbatim_grounding_quote}"</p>
                  </div>
                </div>

                <div className="pt-1">
                  <button
                    onClick={() => toggleDetailed(idx)}
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-700 hover:text-indigo-900"
                  >
                    {detailedOpen[idx] ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    {detailedOpen[idx] ? "Hide detailed feedback" : "Show detailed feedback"}
                  </button>

                  {detailedOpen[idx] && (
                    <div className="mt-3 space-y-3">
                      {detailedLoading[idx] && (
                        <div className="flex items-center gap-2 text-sm text-slate-500">
                          <Loader2 className="h-4 w-4 animate-spin text-indigo-600" /> Writing the detailed explanation…
                        </div>
                      )}
                      {detailedError[idx] && (
                        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{detailedError[idx]}</p>
                      )}
                      {fb && (
                        <>
                          <div className="bg-indigo-50/60 border border-indigo-100 rounded-xl p-4 text-sm text-slate-800">
                            <span className="font-semibold text-indigo-900">Why this answer, in depth</span>
                            <p className="mt-1.5 leading-relaxed">{fb.concept_paragraph}</p>
                            {fb.key_concepts.length > 0 && (
                              <div className="flex flex-wrap gap-1.5 mt-3">
                                {fb.key_concepts.map((c) => (
                                  <span key={c} className="text-xs font-medium px-2.5 py-1 rounded-full bg-white border border-indigo-200 text-indigo-800">{c}</span>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="bg-amber-50/70 border border-amber-200/60 rounded-xl p-4 text-sm text-amber-950 flex items-start gap-3">
                            <Lightbulb className="h-4 w-4 text-amber-700 flex-shrink-0 mt-0.5" />
                            <div>
                              <span className="font-semibold text-amber-900">Test-taking tip</span>
                              <p className="mt-0.5 leading-relaxed">{fb.strategy_tip}</p>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
