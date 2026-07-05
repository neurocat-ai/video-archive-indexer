from pathlib import Path
import json
import subprocess
import base64
from datetime import datetime
import os

from dotenv import load_dotenv
from openai import OpenAI

from integrations.sheets import upsert_video

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Add it to .env file.")

client = OpenAI(api_key=OPENAI_API_KEY)


BASE_DIR = Path(__file__).resolve().parent.parent

VIDEO_PATH = Path(os.getenv("VIDEO_VISION_INPUT_PATH"))

SCENE_FRAMES_PATH = BASE_DIR / "data" / "scene_frames"
SCENES_PATH = BASE_DIR / "data" / "scenes"

SAMPLE_TIMESTAMPS = [1, 5, 10]
MODEL = "gpt-4o-mini"


def extract_frame(video_file: Path, timestamp: int) -> Path:
    SCENE_FRAMES_PATH.mkdir(parents=True, exist_ok=True)

    frame_file = SCENE_FRAMES_PATH / f"{video_file.stem}_{timestamp}s.png"

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


def encode_image_to_base64(image_file: Path) -> str:
    with image_file.open("rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


def analyze_frame(image_file: Path, timestamp: int) -> dict:
    image_base64 = encode_image_to_base64(image_file)

    prompt = """
Опиши кадр для будущего поиска по видеоархиву.

Нужно вернуть только JSON без markdown.

Структура:
{
  "scene_description": "краткое описание сцены",
  "visible_objects": ["объект 1", "объект 2"],
  "visible_people": ["кто изображён, если понятно"],
  "actions": ["что происходит в кадре"],
  "visual_topics": ["темы, которые можно искать"],
  "search_phrases": ["по каким фразам пользователь мог бы искать этот кадр"],
  "confidence_notes": "что неочевидно или требует проверки"
}

Важно:
- Не пересказывай текст с экрана, если это просто субтитры.
- Описывай именно визуальное содержание.
- Если видна схема, сравнение, объект, символ или метафора — обязательно зафиксируй.
- Если кадр подходит под запрос вроде "сходство отпечатка пальца и среза дерева", опиши это явно.
"""

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{image_base64}"
                    }
                ]
            }
        ]
    )

    raw_text = response.output_text.strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {
            "scene_description": raw_text,
            "visible_objects": [],
            "visible_people": [],
            "actions": [],
            "visual_topics": [],
            "search_phrases": [],
            "confidence_notes": "Model response was not valid JSON."
        }

    return {
        "timestamp_sec": timestamp,
        "frame_file": str(image_file),
        **parsed
    }


def save_scene_result(video_file: Path, data: dict):
    SCENES_PATH.mkdir(parents=True, exist_ok=True)

    output_file = SCENES_PATH / f"{video_file.stem}.json"

    with output_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def process_video(video_file: Path) -> dict:
    frame_results = []

    for timestamp in SAMPLE_TIMESTAMPS:
        frame_file = extract_frame(video_file, timestamp)
        scene_data = analyze_frame(frame_file, timestamp)
        frame_results.append(scene_data)

    return {
        "file_name": video_file.name,
        "folder": video_file.parent.name,
        "vision_processed_at": datetime.now().isoformat(timespec="seconds"),
        "vision_model": MODEL,
        "sampled_timestamps_sec": SAMPLE_TIMESTAMPS,
        "scene_results": frame_results
    }

def build_vision_sheet_data(result: dict) -> dict:
    scene_results = result.get("scene_results", [])

    return {
        "file_name": result["file_name"],
        "folder": result["folder"],

        "scene_timestamp_sec": "\n".join(
            str(scene.get("timestamp_sec", ""))
            for scene in scene_results
        ),

        "scene_description": "\n\n".join(
            f"[{scene.get('timestamp_sec')}s] {scene.get('scene_description', '')}"
            for scene in scene_results
        ),

        "visible_objects": "\n\n".join(
            f"[{scene.get('timestamp_sec')}s]\n" +
            "\n".join(scene.get("visible_objects", []))
            for scene in scene_results
        ),

        "scene_actions": "\n\n".join(
            f"[{scene.get('timestamp_sec')}s]\n" +
            "\n".join(scene.get("actions", []))
            for scene in scene_results
        ),

        "visual_topics": "\n\n".join(
            f"[{scene.get('timestamp_sec')}s]\n" +
            "\n".join(scene.get("visual_topics", []))
            for scene in scene_results
        ),

        "search_phrases": "\n\n".join(
            f"[{scene.get('timestamp_sec')}s]\n" +
            "\n".join(scene.get("search_phrases", []))
            for scene in scene_results
        )
    }

if __name__ == "__main__":
    video_files = [
        file
        for file in VIDEO_PATH.iterdir()
        if file.is_file()
    ]

    if not video_files:
        raise FileNotFoundError(
            f"No video files found in: {VIDEO_PATH}"
        )

    target_video = video_files[0]

    print("=" * 80)
    print(f"FILE: {target_video.name}")

    try:
        result = process_video(target_video)
        save_scene_result(target_video, result)

        vision_sheet_data = build_vision_sheet_data(result)
        upsert_video(vision_sheet_data)

        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as error:
        error_result = {
            "file_name": target_video.name,
            "folder": target_video.parent.name,
            "vision_processed_at": datetime.now().isoformat(timespec="seconds"),
            "vision_model": MODEL,
            "sampled_timestamps_sec": SAMPLE_TIMESTAMPS,
            "scene_results": [],
            "vision_notes": f"Vision analysis failed: {error}"
        }

        save_scene_result(target_video, error_result)
        upsert_video(error_result)
        print(json.dumps(error_result, indent=2, ensure_ascii=False))