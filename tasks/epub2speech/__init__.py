#region generated meta
import typing
class Inputs(typing.TypedDict):
    epub_path: str
    voice: typing.Literal["zh_male_lengkugege_emo_v2_mars_bigtts", "zh_female_tianmeixiaomei_emo_v2_mars_bigtts", "zh_female_gaolengyujie_emo_v2_mars_bigtts", "zh_male_aojiaobazong_emo_v2_mars_bigtts", "zh_male_guangzhoudege_mars_bigtts", "zh_male_jingqiangkanye_mars_bigtts", "zh_female_linjuaayi_mars_bigtts", "zh_male_yourougongzi_mars_bigtts", "zh_male_ruyananyou_emo_v2_mars_bigtts", "zh_male_junlangnanyou_emo_v2_mars_bigtts", "zh_male_beijingxiaoye_mars_bigtts", "zh_female_roumeinvyou_emo_v2_mars_bigtts", "zh_male_yangguangqingnian_emo_v2_mars_bigtts", "zh_female_meilinvyou_emo_v2_mars_bigtts", "zh_male_shenyeboke_mars_bigtts", "en_female_candice_emo_v2_mars_bigtts", "en_female_serena_emo_v2_mars_bigtts", "en_male_glen_emo_v2_mars_bigtts", "en_male_sylus_emo_v2_mars_bigtts", "en_male_corey_mars_bigtts", "en_female_nadia_mars_bigtts"]
    output_filename: str | None
    merge: bool | None
    max_chunk_length: float | None
class Outputs(typing.TypedDict):
    audiobook_path: typing.NotRequired[str]
#endregion

from oocana import Context
from epub2speech import convert_epub_to_m4b, ConversionProgress
from epub2speech.tts.protocol import TextToSpeechProtocol
from pathlib import Path
import requests
import os
import time
from ebooklib import epub


class OomolTTSEngine(TextToSpeechProtocol):
    """OOMOL TTS engine implementation for epub2speech"""

    def __init__(self, token: str):
        self.token = token
        self.tts_url = "https://fusion-api.oomol.com/v1/doubao-tts/submit"
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

    def convert_text_to_audio(self, text: str, output_path: Path, voice: str) -> None:
        """Convert a text to audio and save to output_path"""
        # Submit TTS task
        payload = {"text": text, "voice": voice}
        response = None

        # Debug: print token info (first 20 chars only for security)
        token_preview = self.token[:20] + "..." if len(self.token) > 20 else self.token
        print(f"[DEBUG] Token preview: {token_preview}")
        print(f"[DEBUG] Text length: {len(text)} chars")
        print(f"[DEBUG] Voice: {voice}")

        try:
            response = requests.post(self.tts_url, json=payload, headers=self.headers, timeout=1800.0)
            print(f"[DEBUG] Response status: {response.status_code}")
            if response.status_code != 200:
                print(f"[DEBUG] Response body: {response.text}")
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            error_detail = response.text if response else "No response"
            status_code = response.status_code if response else "N/A"
            raise ValueError(f"TTS API Error (HTTP {status_code}): {error_detail}. Text length: {len(text)} chars. Voice: {voice}") from e
        except Exception as e:
            raise ValueError(f"TTS request failed: {str(e)}. Text length: {len(text)} chars. Voice: {voice}") from e

        result = response.json()

        # Extract task_id from response
        if "sessionID" in result:
            task_id = result["sessionID"]
        elif "taskId" in result:
            task_id = result["taskId"]
        elif "data" in result and "taskId" in result["data"]:
            task_id = result["data"]["taskId"]
        elif "id" in result:
            task_id = result["id"]
        elif "data" in result and "id" in result["data"]:
            task_id = result["data"]["id"]
        else:
            raise ValueError(f"Unexpected TTS response format: {result}")

        # Poll for completion
        status_url = f"https://fusion-api.oomol.com/v1/doubao-tts/result/{task_id}"
        state = "processing"

        while state in ["processing", "queued"]:
            time.sleep(2)
            status_response = requests.get(status_url, headers=self.headers, timeout=60.0)
            status_response.raise_for_status()
            status_result = status_response.json()

            # Get state from response (not 'status')
            state = status_result.get("state", "unknown")

            if state == "completed":
                # Extract data and find audio URL
                data = status_result.get("data", {})

                # Try different possible fields for audio URL
                audio_url = (
                    data.get("audioURL")
                    or data.get("audio_url")
                    or data.get("url")
                    or status_result.get("audioURL")
                    or status_result.get("audio_url")
                    or status_result.get("url")
                )

                if not audio_url:
                    raise ValueError(f"No audio URL in response. Result: {status_result}")

                audio_response = requests.get(audio_url, timeout=300.0)
                audio_response.raise_for_status()

                # Save audio file
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(audio_response.content)
                return

            elif state == "failed":
                error_msg = status_result.get("error") or status_result.get("message", "Unknown error")
                raise ValueError(f"TTS failed: {error_msg}")


async def main(params: Inputs, context: Context) -> Outputs:
    epub_path = params["epub_path"]
    voice = params["voice"]

    # Apply defaults for optional parameters
    output_filename = params.get("output_filename") or "audiobook"
    merge = params.get("merge") if params.get("merge") is not None else True
    max_chunk_length = int(params.get("max_chunk_length") or 500)

    context.report_progress(5)

    # Validate input and EPUB file
    if not os.path.exists(epub_path):
        raise ValueError(f"EPUB file not found: {epub_path}")

    # Verify EPUB can be parsed
    try:
        epub.read_epub(epub_path)
    except Exception as e:
        raise ValueError(f"Failed to parse EPUB file: {e}. The file may be corrupted or in an unsupported format.")

    # Setup workspace and output paths
    workspace = Path(context.session_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    context.report_progress(10)

    # Get OOMOL token and create TTS engine
    token = await context.oomol_token()
    tts_engine = OomolTTSEngine(token)

    # Define progress callback - receives ConversionProgress object
    def progress_callback(progress: ConversionProgress):
        # Scale progress from 10% to 95%
        scaled_progress = 10 + int(progress.progress * 0.85)
        context.report_progress(scaled_progress)

    output_path = workspace / f"{output_filename}.m4b"

    context.report_progress(15)

    # Convert EPUB to audiobook
    if merge:
        result_path = convert_epub_to_m4b(
            epub_path=Path(epub_path),
            workspace=workspace,
            output_path=output_path,
            tts_protocol=tts_engine,
            voice=voice,
            max_tts_segment_chars=max_chunk_length,
            progress_callback=progress_callback,
        )
        audiobook_path = str(result_path) if result_path.exists() else ""
    else:
        # Convert chapters only without merging
        result_path = convert_epub_to_m4b(
            epub_path=Path(epub_path),
            workspace=workspace,
            output_path=None,  # Don't merge
            tts_protocol=tts_engine,
            voice=voice,
            max_tts_segment_chars=max_chunk_length,
            progress_callback=progress_callback,
        )
        audiobook_path = ""

    context.report_progress(100)

    return {
        "audiobook_path": audiobook_path
    }