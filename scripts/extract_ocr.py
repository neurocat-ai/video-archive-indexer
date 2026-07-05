from pathlib import Path
import json
import subprocess
from datetime import datetime
from difflib import SequenceMatcher
import os

from dotenv import load_dotenv
import pytesseract
from PIL import Image

from integrations.sheets import upsert_video

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_PATH = Path(os.getenv("VIDEO_OCR_INPUT_PATH"))

COVERS_PATH = BASE_DIR / "data" / "covers"
FRAMES_PATH = BASE_DIR / "data" / "ocr_frames"
OCR_PATH = BASE_DIR / "data" / "ocr"

SAMPLE_TIMESTAMPS = [1, 3, 5]
OCR_LANG = "rus+eng"

LINE_SIMILARITY_THRESHOLD = 0.65
MIN_LINE_OCCURRENCES = 2


def extract_frame(video_file: Path, timestamp: int) -> Path:
    FRAMES_PATH.mkdir(parents=True, exist_ok=True)

    frame_file = FRAMES_PATH / f"{video_file.stem}_{timestamp}s.png"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp),
        "-i", str(video_file),
        "-frames:v", "1",
        str(frame_file)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Frame extraction failed: {result.stderr}")

    return frame_file


def clean_text(text: str) -> str:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return "\n".join(lines)


def normalize_line(line: str) -> str:
    return " ".join(line.lower().strip().split())


def split_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]


def text_similarity(text_1: str, text_2: str) -> float:
    if not text_1 or not text_2:
        return 0.0

    return SequenceMatcher(
        None,
        normalize_line(text_1),
        normalize_line(text_2)
    ).ratio()


def run_ocr(image_file: Path) -> str:
    image = Image.open(image_file)

    text = pytesseract.image_to_string(
        image,
        lang=OCR_LANG
    )

    return clean_text(text)


def collect_repeated_lines(ocr_results: list) -> list[dict]:
    all_lines = []

    for item in ocr_results:
        timestamp = item["timestamp_sec"]
        text = item["text"]

        for line in split_lines(text):
            all_lines.append({
                "timestamp_sec": timestamp,
                "line": line
            })

    groups = []

    for line_item in all_lines:
        line = line_item["line"]
        matched_group = None

        for group in groups:
            score = text_similarity(line, group["representative_line"])

            if score >= LINE_SIMILARITY_THRESHOLD:
                matched_group = group
                break

        if matched_group:
            matched_group["items"].append(line_item)

            if len(line) > len(matched_group["representative_line"]):
                matched_group["representative_line"] = line
        else:
            groups.append({
                "representative_line": line,
                "items": [line_item]
            })

    repeated_lines = []

    for group in groups:
        timestamps = sorted({
            item["timestamp_sec"]
            for item in group["items"]
        })

        if len(timestamps) >= MIN_LINE_OCCURRENCES:
            repeated_lines.append({
                "text": group["representative_line"],
                "timestamps_sec": timestamps,
                "occurrence_count": len(timestamps)
            })

    return repeated_lines


def build_static_text_result(ocr_results: list) -> dict:
    repeated_lines = collect_repeated_lines(ocr_results)

    if not repeated_lines:
        all_texts = [
            item["text"]
            for item in ocr_results
            if item["text"]
        ]

        if not all_texts:
            return {
                "has_static_overlay_text": False,
                "ocr_text": "",
                "static_ocr_lines": [],
                "ocr_notes": "No readable text detected in sampled frames."
            }

        return {
            "has_static_overlay_text": False,
            "ocr_text": "",
            "static_ocr_lines": [],
            "ocr_notes": "No stable repeated text detected. Text is likely dynamic subtitle-like content."
        }

    ocr_text = "\n".join(
        item["text"]
        for item in repeated_lines
    )

    return {
        "has_static_overlay_text": True,
        "ocr_text": ocr_text,
        "static_ocr_lines": repeated_lines,
        "ocr_notes": f"Stable overlay text detected by repeated lines. Lines found: {len(repeated_lines)}"
    }


def find_cover_file(video_file: Path) -> Path | None:
    cover_file = COVERS_PATH / f"{video_file.stem}.png"

    if cover_file.exists():
        return cover_file

    return None


def save_ocr_result(video_file: Path, data: dict):
    OCR_PATH.mkdir(parents=True, exist_ok=True)

    output_file = OCR_PATH / f"{video_file.stem}.json"

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def process_video(video_file: Path) -> dict:
    frame_ocr_results = []

    for timestamp in SAMPLE_TIMESTAMPS:
        frame_file = extract_frame(video_file, timestamp)
        text = run_ocr(frame_file)

        frame_ocr_results.append({
            "timestamp_sec": timestamp,
            "frame_file": str(frame_file),
            "text": text
        })

    static_text_result = build_static_text_result(frame_ocr_results)

    cover_file = find_cover_file(video_file)
    cover_text = ""

    if cover_file:
        cover_text = run_ocr(cover_file)

    result = {
        "file_name": video_file.name,
        "folder": video_file.parent.name,
        "ocr_processed_at": datetime.now().isoformat(timespec="seconds"),

        "ocr_source": "sampled_frames",
        "sampled_timestamps_sec": SAMPLE_TIMESTAMPS,

        "has_cover": bool(cover_file),
        "cover_file": str(cover_file) if cover_file else None,
        "cover_ocr_text": cover_text,

        "has_static_overlay_text": static_text_result["has_static_overlay_text"],
        "ocr_text": static_text_result["ocr_text"],
        "static_ocr_lines": static_text_result["static_ocr_lines"],

        "frame_ocr_results": frame_ocr_results,

        "ocr_notes": static_text_result["ocr_notes"]
    }

    return result


if __name__ == "__main__":
    for video in VIDEO_PATH.iterdir():
        if not video.is_file():
            continue

        print("=" * 80)
        print(f"FILE: {video.name}")

        try:
            result = process_video(video)
            save_ocr_result(video, result)

            upsert_video(result)

            print(json.dumps(result, indent=2, ensure_ascii=False))

        except Exception as error:
            error_result = {
                "file_name": video.name,
                "folder": video.parent.name,
                "ocr_processed_at": datetime.now().isoformat(timespec="seconds"),
                "has_static_overlay_text": False,
                "ocr_text": "",
                "static_ocr_lines": [],
                "frame_ocr_results": [],
                "ocr_notes": f"OCR failed: {error}"
            }

            save_ocr_result(video, error_result)
            upsert_video(error_result)
            print(json.dumps(error_result, indent=2, ensure_ascii=False))