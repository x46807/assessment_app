'use client';

import React, { useState } from "react";
import StimulusViewer from "./StimulusViewer";
import { CheckCircle2, XCircle, Clock, FileText } from "lucide-react";

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

export default function InteractiveQuiz({ items }: { items: QuestionItem[] }) {
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, string>>({});
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});

  return (
    <div className="space-y-8">
      {items.map((item, idx) => {
        const isAnswered = !!selectedAnswers[idx];
        const isRevealed = !!revealed[idx];
        const isCorrect = selectedAnswers[idx] === item.correct_option;

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
                  onClick={() => setSelectedAnswers((prev) => ({ ...prev, [idx]: opt.label }))}
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
                onClick={() => setRevealed((prev) => ({ ...prev, [idx]: true }))}
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
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
