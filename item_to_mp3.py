from google.cloud import texttospeech
from pydub import AudioSegment
from pydub.playback import play
import io


sidney = {"language_code": "en-GB", "name": "en-AU-Standard-C"}


def item_to_mp3(content: str, uiuid: str):
    try:
        with open(f"mp3_cache/{uiuid}.mp3", "rb") as fp:
            mp3 = fp.read()
    except:
        client = texttospeech.TextToSpeechClient()
        voice = texttospeech.VoiceSelectionParams(content, sidney)

        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

        response = client.synthesize_speech(
            request={
                "input": texttospeech.SynthesisInput(text=content),
                "voice": voice,
                "audio_config": audio_config,
            }
        )

        mp3 = response.audio_content
        with open(f"mp3_cache/{uiuid}.mp3", "wb") as fp:
            fp.write(mp3)

    return mp3
