import os
import re
import tempfile
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
        except Exception:
            # YouTube routinely blocks the transcript API from cloud
            # IPs (Render runs on shared datacenter IPs). Fall back to
            # yt-dlp subtitle extraction, which uses the Android player
            # client and is blocked far less often. Same list-of-dicts
            # shape, so the chunking loop below is unchanged.
            print("[YouTube] transcript API failed, trying yt-dlp subtitles")
            transcript_list = cls._transcript_via_ytdlp(youtube_url, video_id)
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

    @staticmethod
    def _transcript_via_ytdlp(youtube_url: str, video_id: str) -> List[dict]:
        """Download a video's subtitles with yt-dlp (manual captions first,
        auto-generated captions otherwise) and return them as
        {text, start, duration} entries, the transcript API's shape."""
        import yt_dlp  # lazy import: yt-dlp is heavy and only needed here

        with tempfile.TemporaryDirectory(prefix="yt-subs-") as tmpdir:
            ydl_opts = {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en"],
                "subtitlesformat": "vtt/best",
                "skip_download": True,
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "outtmpl": os.path.join(tmpdir, "%(id)s"),
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([youtube_url])
            except Exception as e:
                raise ValueError(
                    "YouTube is blocking transcript requests from this server's network right now "
                    "(both the transcript service and the backup subtitle downloader failed: %s). "
                    "Please try again later, or upload the video file itself as source material."
                    % str(e)[:200]
                )
            vtt_files = sorted(f for f in os.listdir(tmpdir) if f.endswith(".vtt"))
            if not vtt_files:
                raise ValueError(
                    "YouTube is blocking transcript requests from this server's network right now, "
                    "and no subtitles could be downloaded for this video. Please try again later, "
                    "or upload the video file itself as source material."
                )
            with open(os.path.join(tmpdir, vtt_files[0]), encoding="utf-8", errors="ignore") as f:
                entries = _parse_vtt(f.read())
            if not entries:
                raise ValueError(
                    "The downloaded subtitles for this video contained no usable text. "
                    "Please try a different video, or upload the video file itself as source material."
                )
            print("[YouTube] yt-dlp subtitles: %d cues from %s" % (len(entries), vtt_files[0]))
            return entries


_VTT_TIME = re.compile(r"(\d+):(\d+):(\d+)\.(\d+)\s+-->\s+(\d+):(\d+):(\d+)\.(\d+)")
_VTT_TAG = re.compile(r"<[^>]+>")


def _parse_vtt(vtt_text: str) -> List[dict]:
    """Parse WebVTT subtitle text into {text, start, duration} entries.
    Strips YouTube's inline formatting tags and cue-position settings."""
    entries: List[dict] = []
    lines = vtt_text.splitlines()
    i = 0
    while i < len(lines):
        m = _VTT_TIME.search(lines[i])
        if not m:
            i += 1
            continue
        sh, sm, ss, sms, eh, em, es, ems = (int(g) for g in m.groups())
        start = sh * 3600 + sm * 60 + ss + sms / 1000.0
        end = eh * 3600 + em * 60 + es + ems / 1000.0
        i += 1
        cue_lines = []
        while i < len(lines) and lines[i].strip():
            cue_lines.append(_VTT_TAG.sub("", lines[i]).strip())
            i += 1
        text = " ".join(t for t in cue_lines if t)
        if text:
            entries.append({"text": text, "start": start, "duration": max(0.0, end - start)})
    return entries
