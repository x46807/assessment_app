import re
from typing import List, Optional
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
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

        # youtube-transcript-api 1.x: the old classmethod get_transcript()
        # no longer exists. fetch() returns a FetchedTranscript; to_raw_data()
        # gives back the list-of-dicts shape (text/start/duration) this
        # loop expects.
        try:
            transcript_list = YouTubeTranscriptApi().fetch(video_id).to_raw_data()
        except (NoTranscriptFound, TranscriptsDisabled):
            raise ValueError(
                "This YouTube video has no captions/transcript available, "
                "so it cannot be used as source material."
            )
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
                    content=" ".join(current_text),
                    source_file=title or f"YouTube Video ({video_id})",
                ))
                current_text = []
                start_time = None

        if current_text:
            chunk_idx += 1
            chunks.append(SourceChunk(
                chunk_index=chunk_idx,
                locator_type="timestamp",
                locator_value=f"{cls._format_timestamp(start_time or 0)} - {cls._format_timestamp(end_time or 0)}",
                content=" ".join(current_text),
                source_file=title or f"YouTube Video ({video_id})",
            ))

        return IngestionResult(source_title=title or f"YouTube Video ({video_id})", source_type="youtube", total_chunks=len(chunks), chunks=chunks)
