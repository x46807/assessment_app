'use client';

import React, { useEffect, useRef } from "react";
import mermaid from "mermaid";
import { Quote, Image as ImageIcon, GitFork, Table } from "lucide-react";

interface StimulusProps {
  stimulus: {
    stimulus_type: string;
    content: string;
    attribution_or_context: string;
  };
}

export default function StimulusViewer({ stimulus }: StimulusProps) {
  const mermaidRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (stimulus.stimulus_type === "diagram" && mermaidRef.current) {
      mermaid.initialize({ startOnLoad: true, theme: "neutral" });
      mermaid.render(`mermaid-${Math.random().toString(36).substring(7)}`, stimulus.content).then(({ svg }) => {
        if (mermaidRef.current) mermaidRef.current.innerHTML = svg;
      });
    }
  }, [stimulus]);

  return (
    <div className="mb-6 rounded-xl border border-indigo-100 bg-indigo-50/40 p-5 overflow-hidden">
      <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-indigo-700 mb-3">
        {stimulus.stimulus_type === "historical_passage" && <Quote className="h-4 w-4" />}
        {stimulus.stimulus_type === "map" && <ImageIcon className="h-4 w-4" />}
        {stimulus.stimulus_type === "diagram" && <GitFork className="h-4 w-4" />}
        {stimulus.stimulus_type === "data_table" && <Table className="h-4 w-4" />}
        <span>Stimulus Material: {stimulus.stimulus_type.replace("_", " ")}</span>
      </div>

      {stimulus.stimulus_type === "map" || stimulus.stimulus_type === "illustration" ? (
        <img src={stimulus.content} alt={stimulus.attribution_or_context} className="max-h-80 w-auto rounded-lg mx-auto border border-slate-200" />
      ) : stimulus.stimulus_type === "diagram" ? (
        <div ref={mermaidRef} className="flex justify-center my-4 overflow-x-auto" />
      ) : (
        <div className="border-l-4 border-indigo-400 pl-4 py-1 italic text-slate-800 text-sm leading-relaxed whitespace-pre-line font-serif bg-white/60 rounded-r-lg p-3">
          "{stimulus.content}"
        </div>
      )}

      <p className="text-xs text-slate-500 mt-3 text-right">
        Source: <span className="font-medium text-slate-700">{stimulus.attribution_or_context}</span>
      </p>
    </div>
  );
}
