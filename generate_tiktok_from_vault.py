import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
import requests
import argparse

# The default API endpoint for MoneyPrinterTurbo
API_URL = "http://127.0.0.1:8080/api/v1/videos"

def generate_tiktok_from_vault(markdown_path: str, script_text: str = "", terms: str = "", bgm: str = "", materials: str = "", voice: str = ""):
    if not os.path.exists(markdown_path):
        print(f"Error: File not found -> {markdown_path}")
        sys.exit(1)

    print(f"Reading content from: {markdown_path}")
    with open(markdown_path, 'r', encoding='utf-8') as f:
        content = f.read()

    filename = os.path.basename(markdown_path)
    subject = os.path.splitext(filename)[0]

    payload = {
        "video_subject": f"Vault: {subject[:30]}",
        "video_aspect": "9:16",
        "video_language": "th-TH",  # You can change this to match your target audience
        "voice_name": voice if voice else "th-TH-PremwadeeNeural-Female", # Default Edge TTS voice for Thai
        "bgm_type": "random",
        "subtitle_enabled": True
    }

    if script_text:
        print("Using provided explicit script.")
        payload["video_script"] = script_text
        payload["video_language"] = "en-US" # Set to English since script is English
        if not voice:
            payload["voice_name"] = "en-US-AriaNeural-Female"

    if voice:
        payload["voice_name"] = voice
        print(f"Using explicit voice: {voice}")

    if terms:
        # User provides comma separated terms like "money, finance, investment"
        terms_list = [t.strip() for t in terms.split(",")]
        payload["video_terms"] = terms_list
        print(f"Using explicit video terms: {terms_list}")

    if bgm:
        payload["bgm_type"] = "custom"
        payload["bgm_file"] = bgm
        print(f"Using custom background music: {bgm}")

    if materials:
        # Comma separated list of files in storage/local_videos
        mat_list = [m.strip() for m in materials.split(",")]
        payload["video_materials"] = [{"provider": "local", "url": m, "duration": 0} for m in mat_list]
        print(f"Using custom video materials: {mat_list}")

    if not script_text:
        # Construct the prompt for MoneyPrinterTurbo's LLM to write a TikTok script
        script_prompt = f"""
Please act as an expert TikTok scriptwriter. I will provide you with a note/clipping from my personal vault.
I need you to write a highly engaging, 30-60 second TikTok video script based on the key points in this note.
Make it snappy, use conversational language, and include a strong hook at the beginning.
Do not include camera directions, just output the spoken text.

Here is the vault note:
{content[:1500]}  # Truncating to avoid length limits
"""
        payload["video_script_prompt"] = script_prompt

    print("Sending request to MoneyPrinterTurbo API to generate the video...")
    try:
        response = requests.post(API_URL, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        print("\nSuccess! Video generation task has been queued.")
        print(f"Task ID: {result.get('data', {}).get('task_id')}")
        print("You can check the progress in the MoneyPrinterTurbo WebUI.")
    except requests.exceptions.RequestException as e:
        print(f"\nError connecting to MoneyPrinterTurbo API: {e}")
        print("Please ensure that you have started the API server (uv run python main.py).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate TikTok from Vault Clipping")
    parser.add_argument("markdown_file", help="Path to the markdown file in your vault")
    parser.add_argument("--script", help="Explicit script to use (bypasses LLM generation)", default="")
    parser.add_argument("--terms", help="Comma separated keywords for video search (e.g. 'finance, money, stock')", default="")
    parser.add_argument("--bgm", help="Specific background music file (e.g. 'output012.mp3')", default="")
    parser.add_argument("--materials", help="Comma separated local video/image filenames in storage/local_videos/", default="")
    parser.add_argument("--voice", help="Explicit voice name (e.g. 'en-US-GuyNeural-Male')", default="")
    args = parser.parse_args()
    
    # We pass all args now
    generate_tiktok_from_vault(args.markdown_file, args.script, args.terms, args.bgm, args.materials, args.voice)
