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
        # Caption-based methods first (verbatim text, exact timestamps,
        # no model cost) -- the same data NotebookLM imports, fetched
        # from outside Google. Gemini video understanding is the last
        # resort: it watches/listens to the video on Google's servers,
        # so it works even when YouTube blocks caption downloads and
        # even for videos with no captions at all.
        transcript_list = None
        try:
            transcript_list = YouTubeTranscriptApi().fetch(video_id).to_raw_data()
        except (NoTranscriptFound, TranscriptsDisabled):
            print("[YouTube] no captions via transcript API; trying yt-dlp, then Gemini")
        except Exception as e:
            print("[YouTube] transcript API failed (%s); trying yt-dlp, then Gemini" % e)
        if transcript_list is None:
            try:
                transcript_list = cls._transcript_via_ytdlp(youtube_url, video_id)
            except Exception as e:
                print("[YouTube] yt-dlp failed (%s); trying Gemini video understanding" % e)
                transcript_list = cls._transcript_via_gemini(youtube_url, video_id)
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
                raise ValueError("yt-dlp subtitle download failed: %s" % str(e)[:200])
            vtt_files = sorted(f for f in os.listdir(tmpdir) if f.endswith(".vtt"))
            if not vtt_files:
                raise ValueError("yt-dlp found no subtitle files for this video.")
            with open(os.path.join(tmpdir, vtt_files[0]), encoding="utf-8", errors="ignore") as f:
                entries = _parse_vtt(f.read())
            if not entries:
                raise ValueError("The downloaded subtitles contained no usable text.")
            print("[YouTube] yt-dlp subtitles: %d cues from %s" % (len(entries), vtt_files[0]))
            return entries

    @staticmethod
    def _transcript_via_gemini(youtube_url: str, video_id: str) -> List[dict]:
        """Transcribe a YouTube video with Gemini video understanding.

        This is the public equivalent of how NotebookLM ingests YouTube:
        instead of this server downloading captions, the YouTube URL is
        passed to the Gemini API and Google's servers fetch and process
        the video, so YouTube's IP blocks on caption downloads do not
        apply. It also works for videos with no captions at all. The
        transcript is model-generated (like the Gemini image transcription
        already used for JPG/PNG sources), so timestamps are approximate;
        the citation still points at the video timestamp, which can be
        checked by watching. Costs Flash video input tokens (about 258
        tokens per second of video, so a 10-minute video is roughly 155k
        input tokens); only runs when the free caption routes have failed.
        Public videos only; very long videos (roughly 45+ minutes) may
        fail or return a partial transcript."""
        from gemini_schema import make_gemini_client
        from google.genai import types

        prompt = (
            "Transcribe the spoken content of this video as a timestamped transcript. "
            "Output one segment per 30-45 seconds of speech, each on its own line in exactly this format: "
            "[MM:SS] <what was said>. Cover the whole video from start to finish. "
            "Transcribe what is actually said; do not summarize, do not add commentary, "
            "and do not invent content for parts you cannot hear. If a part is inaudible, skip it rather than guessing."
        )
        try:
            client = make_gemini_client()
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[prompt, types.Part.from_uri(file_uri=youtube_url, mime_type="video/mp4")],
                config=types.GenerateContentConfig(temperature=0.2),
            )
        except Exception as e:
            raise ValueError(
                "YouTube captions could not be fetched (YouTube is blocking requests from this server), "
                "and Gemini could not transcribe this video either: %s. "
                "Please check the video is public and try again later." % str(e)[:200]
            )
        entries = _parse_transcript_text((response.text or "").strip())
        if not entries:
            raise ValueError(
                "YouTube captions could not be fetched (YouTube is blocking requests from this server), "
                "and Gemini returned no usable transcript for this video. "
                "Please check the video is public and try again later."
            )
        print("[YouTube] Gemini transcript: %d segments" % len(entries))
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


_TRANSCRIPT_LINE = re.compile(r"^\[(\d+):(\d+)\]\s*(.+)$")


def _parse_transcript_text(text: str) -> List[dict]:
    """Parse a "[MM:SS] spoken words" transcript into {text, start,
    duration} entries. Each segment's duration is the gap to the next
    segment (capped at 45s); the last segment defaults to 30s."""
    entries: List[dict] = []
    for line in text.splitlines():
        m = _TRANSCRIPT_LINE.match(line.strip())
        if not m:
            continue
        spoken = m.group(3).strip()
        if not spoken:
            continue
        entries.append({
            "text": spoken,
            "start": float(int(m.group(1)) * 60 + int(m.group(2))),
            "duration": 0.0,
        })
    for i, entry in enumerate(entries):
        if i + 1 < len(entries):
            entry["duration"] = max(1.0, min(45.0, entries[i + 1]["start"] - entry["start"]))
        else:
            entry["duration"] = 30.0
    return entries
