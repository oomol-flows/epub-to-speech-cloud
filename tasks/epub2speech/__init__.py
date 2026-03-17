#region generated meta
import typing
class Inputs(typing.TypedDict):
    epub_path: str
    voice: typing.Literal["zh_male_lengkugege_emo_v2_mars_bigtts", "zh_female_tianmeixiaomei_emo_v2_mars_bigtts", "zh_female_gaolengyujie_emo_v2_mars_bigtts", "zh_male_aojiaobazong_emo_v2_mars_bigtts", "zh_male_guangzhoudege_mars_bigtts", "zh_male_jingqiangkanye_mars_bigtts", "zh_female_linjuaayi_mars_bigtts", "zh_male_yourougongzi_mars_bigtts", "zh_male_ruyananyou_emo_v2_mars_bigtts", "zh_male_junlangnanyou_emo_v2_mars_bigtts", "zh_male_beijingxiaoye_mars_bigtts", "zh_female_roumeinvyou_emo_v2_mars_bigtts", "zh_male_yangguangqingnian_emo_v2_mars_bigtts", "zh_female_meilinvyou_emo_v2_mars_bigtts", "zh_male_shenyeboke_mars_bigtts", "en_female_candice_emo_v2_mars_bigtts", "en_female_serena_emo_v2_mars_bigtts", "en_male_glen_emo_v2_mars_bigtts", "en_male_sylus_emo_v2_mars_bigtts", "en_male_corey_mars_bigtts", "en_female_nadia_mars_bigtts"]
    output_filename: str | None
    max_chunk_length: float | None
class Outputs(typing.TypedDict):
    audiobook_path: typing.NotRequired[str]
#endregion

from oocana import Context
from epub2speech import convert_epub_to_m4b, ConversionProgress
from epub2speech.tts.doubao_provider import DoubaoTextToSpeech
from pathlib import Path
import os
from ebooklib import epub


async def main(params: Inputs, context: Context) -> Outputs:
    base_url = "https://fusion-api.oomol.com/v1/oomol-tts"
    if _check_is_dev_env(context):
        base_url = "https://fusion-api.oomol.dev/v1/oomol-tts"

    epub_path = params["epub_path"]
    voice = params["voice"]

    # Apply defaults for optional parameters
    output_filename = params.get("output_filename") or "audiobook"
    max_chunk_length = int(params.get("max_chunk_length") or 500)

    context.report_progress(5)

    # Validate input and EPUB file
    if not os.path.exists(epub_path):
        raise ValueError(f"EPUB file not found: {epub_path}")

    # Verify EPUB can be parsed
    try:
        epub.read_epub(epub_path)
    except Exception as e:
        raise ValueError(f"Failed to parse EPUB file: {e}. The file may be corrupted or in an unsupported format.") from e

    # Setup workspace and output paths
    workspace = Path(context.session_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    context.report_progress(10)

    # Get OOMOL token and create TTS engine using the library's DoubaoTextToSpeech
    token = await context.oomol_token()
    tts_engine = DoubaoTextToSpeech(
        access_token=token,
        base_url=base_url,
    )

    # Define progress callback - receives ConversionProgress object
    def progress_callback(progress: ConversionProgress):
        # Scale progress from 10% to 95%
        scaled_progress = 10 + int(progress.progress * 0.85)
        context.report_progress(scaled_progress)

    output_path = workspace / f"{output_filename}.m4b"

    context.report_progress(15)

    # Convert EPUB to audiobook
    result_path = convert_epub_to_m4b(
        epub_path=Path(epub_path),
        workspace=workspace,
        output_path=output_path,
        tts_protocol=tts_engine,
        voice=voice,
        max_tts_segment_chars=max_chunk_length,
        progress_callback=progress_callback,
    )

    if result_path is None:
        raise RuntimeError("EPUB to audiobook conversion failed: convert_epub_to_m4b returned None")

    if not result_path.exists():
        raise RuntimeError(f"EPUB to audiobook conversion failed: output file not created at {result_path}")

    audiobook_path = str(result_path)

    context.report_progress(100)

    return {
        "audiobook_path": audiobook_path
    }

import re
DEV_PATTERN = re.compile(r"^https?://[^/]+\.oomol\.dev.*")

def _check_is_dev_env(context: Context) -> bool:
    base_url = context.oomol_llm_env.get("base_url")
    if base_url is None:
        return False
    else:
        return bool(DEV_PATTERN.match(base_url))