from pathlib import Path
import json
import subprocess
from datetime import datetime
import os
from dotenv import load_dotenv

from integrations.sheets import upsert_video

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_PATH = Path(os.getenv("VIDEO_METADATA_INPUT_PATH"))

RAW_METADATA_PATH = BASE_DIR / "data" / "metadata_raw"
NORMALIZED_METADATA_PATH = BASE_DIR / "data" / "metadata_normalized"
COVERS_PATH = BASE_DIR / "data" / "covers"


def get_video_metadata(video_file: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_file)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error for {video_file.name}: {result.stderr}")

    return json.loads(result.stdout)


def parse_fps(value: str):
    if not value or value == "0/0":
        return None

    numerator, denominator = value.split("/")
    denominator = int(denominator)

    if denominator == 0:
        return None

    return round(int(numerator) / denominator, 2)


def bytes_to_mb(value: int):
    return round(value / 1024 / 1024, 2)


def get_file_dates(video_file: Path):
    stat = video_file.stat()

    return {
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(timespec="seconds"),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
    }


def get_video_orientation(width, height):
    if not width or not height:
        return None

    if width > height:
        return "horizontal"

    if height > width:
        return "vertical"

    return "square"


def get_streams_by_type(streams: list, codec_type: str) -> list:
    return [
        stream for stream in streams
        if stream.get("codec_type") == codec_type
    ]


def get_attached_image_streams(streams: list) -> list:
    return [
        stream for stream in streams
        if stream.get("codec_type") == "video"
        and stream.get("disposition", {}).get("attached_pic") == 1
    ]


def get_main_video_stream(streams: list) -> dict:
    video_streams = get_streams_by_type(streams, "video")

    for stream in video_streams:
        if stream.get("disposition", {}).get("attached_pic") != 1:
            return stream

    return {}


def get_source_url(format_tags: dict):
    comment = format_tags.get("comment")

    if comment and comment.startswith("http"):
        return comment

    return None


def build_video_card(video_file: Path, metadata: dict) -> dict:
    format_data = metadata.get("format", {})
    format_tags = format_data.get("tags", {})
    streams = metadata.get("streams", [])

    video_streams = get_streams_by_type(streams, "video")
    audio_streams = get_streams_by_type(streams, "audio")
    subtitle_streams = get_streams_by_type(streams, "subtitle")
    attached_image_streams = get_attached_image_streams(streams)

    video_stream = get_main_video_stream(streams)
    audio_stream = audio_streams[0] if audio_streams else {}

    file_dates = get_file_dates(video_file)

    width = video_stream.get("width")
    height = video_stream.get("height")

    cover_file_name = f"{video_file.stem}.png" if attached_image_streams else None

    card = {
        "file_name": video_file.name,
        "folder": video_file.parent.name,
        "file_extension": video_file.suffix.lower().replace(".", ""),

        "created_at": file_dates["created_at"],
        "modified_at": file_dates["modified_at"],

        "duration_sec": int(round(float(format_data.get("duration", 0)))),
        "size_mb": bytes_to_mb(int(format_data.get("size", 0))),
        "format_name": format_data.get("format_name"),
        "format_long_name": format_data.get("format_long_name"),
        "container_bit_rate": format_data.get("bit_rate"),

        "nb_streams": format_data.get("nb_streams"),
        "video_stream_count": len(video_streams) - len(attached_image_streams),
        "audio_stream_count": len(audio_streams),
        "subtitle_stream_count": len(subtitle_streams),
        "attached_image_count": len(attached_image_streams),
        "has_attached_image": bool(attached_image_streams),
        "attached_image_file": cover_file_name,

        "source_title": format_tags.get("title"),
        "source_author": format_tags.get("artist"),
        "source_date": format_tags.get("date"),
        "source_genre": format_tags.get("genre"),
        "source_url": get_source_url(format_tags),

        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else None,
        "aspect_ratio": video_stream.get("display_aspect_ratio"),
        "video_orientation": get_video_orientation(width, height),
        "fps": parse_fps(video_stream.get("avg_frame_rate")),
        "video_codec": video_stream.get("codec_name"),
        "video_bit_rate": video_stream.get("bit_rate"),
        "video_duration_sec": round(float(video_stream.get("duration", 0)), 2) if video_stream.get("duration") else None,
        "video_frame_count": video_stream.get("nb_frames"),

        "has_audio": bool(audio_streams),
        "audio_codec": audio_stream.get("codec_name"),
        "audio_channels": audio_stream.get("channels"),
        "audio_sample_rate": audio_stream.get("sample_rate"),
        "audio_bit_rate": audio_stream.get("bit_rate"),
        "audio_duration_sec": round(float(audio_stream.get("duration", 0)), 2) if audio_stream.get("duration") else None,

        "has_subtitle_stream": bool(subtitle_streams),

        "needs_transcription": bool(audio_streams),
        "needs_ocr_cover": bool(attached_image_streams),
        "needs_ocr_overlay_text": None,
        "needs_vision": None,

        "manual_video_type": None,
        "client_comment": None,
        "processing_notes": None
    }

    return card


def safe_json_filename(video_file: Path) -> str:
    return f"{video_file.stem}.json"


def save_json(data: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def extract_attached_cover(video_file: Path, metadata: dict):
    streams = metadata.get("streams", [])
    attached_image_streams = get_attached_image_streams(streams)

    if not attached_image_streams:
        return None

    COVERS_PATH.mkdir(parents=True, exist_ok=True)

    cover_output_file = COVERS_PATH / f"{video_file.stem}.png"
    stream_index = attached_image_streams[0].get("index")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_file),
        "-map", f"0:{stream_index}",
        "-frames:v", "1",
        str(cover_output_file)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"WARNING: cover extraction failed for {video_file.name}")
        print(result.stderr)
        return None

    return cover_output_file


if __name__ == "__main__":
    for video in VIDEO_PATH.iterdir():
        if video.is_file():
            metadata = get_video_metadata(video)

            extract_attached_cover(video, metadata)

            card = build_video_card(video, metadata)

            raw_output_file = RAW_METADATA_PATH / safe_json_filename(video)
            normalized_output_file = NORMALIZED_METADATA_PATH / safe_json_filename(video)

            save_json(metadata, raw_output_file)
            save_json(card, normalized_output_file)

            upsert_video(card)

            print("=" * 80)
            print(f"FILE: {video.name}")
            print(json.dumps(card, indent=2, ensure_ascii=False))