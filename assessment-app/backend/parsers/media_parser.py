import re
from typing import List, Optional
from youtube_transcript_api import YouTubeTranscriptApi
from models import SourceChunk, IngestionResult

class MediaParser:
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins:02d}:{secs:02d}"

    @classmethod
    def parse_youtube(cls, youtube_url: str, title: Optional[str] = None) -> IngestionResult:
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", youtube_url)
        video_id = match.group(1) if match else None
        if not video_id:
            raise ValueError(f"Invalid YouTube URL: {youtube_url}")

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        chunks: List[SourceChunk] = []
        chunk_idx = 0
        current_text = []
        start_time = None
        end_time = None

        for entry in transcript_list:
            if start_time is None:
                start_time = entry["start"]
            end_time = entry["start"] + entry["duration"]
            current_text.append(entry["text"])

            if (end_time - start_time) >= 45.0:
                chunk_idx += 1
                chunks.append(SourceChunk(
                    chunk_index=chunk_idx,
                    locator_type="timestamp",
                    locator_value=f"{cls._format_timestamp(start_time)} - {cls._format_timestamp(end_time)}",
                    content=" ".join(current_text)
                ))
                current_text = []
                start_time = None

        if current_text:
            chunk_idx += 1
            chunks.append(SourceChunk(
                chunk_index=chunk_idx,
                locator_type="timestamp",
                locator_value=f"{cls._format_timestamp(start_time or 0)} - {cls._format_timestamp(end_time or 0)}",
                content=" ".join(current_text)
            ))

        return IngestionResult(source_title=title or f"YouTube Video ({video_id})", source_type="youtube", total_chunks=len(chunks), chunks=chunks)
