from pathlib import Path
import json
import subprocess
from datetime import datetime
import os

from dotenv import load_dotenv
from faster_whisper import WhisperModel
from integrations.sheets import upsert_video

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_PATH = Path(os.getenv("VIDEO_TRANSCRIPTION_INPUT_PATH"))

AUDIO_PATH = BASE_DIR / "data" / "extracted_audio"
TRANSCRIPTS_PATH = BASE_DIR / "data" / "transcripts"

MODEL_SIZE = "base"  # для теста норм. Потом можно small / medium


def extract_audio(video_file: Path) -> Path:
    AUDIO_PATH.mkdir(parents=True, exist_ok=True)

    audio_file = AUDIO_PATH / f"{video_file.stem}.wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_file),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(audio_file)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Audio extraction failed for {video_file.name}: {result.stderr}")

    return audio_file


def transcribe_audio(model: WhisperModel, audio_file: Path) -> dict:
    segments, info = model.transcribe(
        str(audio_file),
        beam_size=5,
        vad_filter=True
    )

    segment_list = []
    full_text_parts = []

    for segment in segments:
        text = segment.text.strip()

        if not text:
            continue

        segment_data = {
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": text
        }

        segment_list.append(segment_data)
        full_text_parts.append(text)

    transcript_text = " ".join(full_text_parts).strip()

    has_speech = len(transcript_text) > 20 and len(segment_list) > 0

    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "has_speech": has_speech,
        "transcript_text": transcript_text,
        "transcript_segments": segment_list,
        "segment_count": len(segment_list),
        "processing_notes": None if has_speech else "Audio track exists, but speech was not confidently detected."
    }


def save_transcript(video_file: Path, transcript_data: dict):
    TRANSCRIPTS_PATH.mkdir(parents=True, exist_ok=True)

    output_file = TRANSCRIPTS_PATH / f"{video_file.stem}.json"

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(transcript_data, file, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    print("Loading Whisper model...")
    model = WhisperModel(
        MODEL_SIZE,
        device="cpu",
        compute_type="int8"
    )

    for video in VIDEO_PATH.iterdir():
        if not video.is_file():
            continue

        print("=" * 80)
        print(f"FILE: {video.name}")

        try:
            audio_file = extract_audio(video)
            transcription = transcribe_audio(model, audio_file)

            result = {
                "file_name": video.name,
                "folder": video.parent.name,
                "audio_file": str(audio_file),
                "transcribed_at": datetime.now().isoformat(timespec="seconds"),
                **transcription
            }

            save_transcript(video, result)

            upsert_video(result)

            print(json.dumps(result, indent=2, ensure_ascii=False))

        except Exception as error:
            error_result = {
                "file_name": video.name,
                "folder": video.parent.name,
                "transcribed_at": datetime.now().isoformat(timespec="seconds"),
                "has_speech": False,
                "transcript_text": "",
                "transcript_segments": [],
                "processing_notes": f"Transcription failed: {error}"
            }

            save_transcript(video, error_result)

            upsert_video(error_result)

            print(json.dumps(error_result, indent=2, ensure_ascii=False))