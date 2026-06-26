"""Google Home integration via Assistant SDK gRPC."""
import os
import json
import tempfile

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

from google_auth import get_google_credentials, check_google_auth

import google.assistant.embedded.v1alpha2.embedded_assistant_pb2 as _pb
import google.assistant.embedded.v1alpha2.embedded_assistant_pb2_grpc as _pb_grpc
import grpc
import google.auth.transport.grpc
import google.auth.transport.requests

ASSISTANT_LANGS = {
    "it": "it-IT", "en": "en-US", "de": "de-DE",
    "fr": "fr-FR", "es": "es-ES", "pt": "pt-BR",
    "ja": "ja-JP", "ko": "ko-KR", "zh": "zh-CN",
}

ENDPOINT = "embeddedassistant.googleapis.com"
API_SCOPE = "https://www.googleapis.com/auth/assistant-sdk-prototype"
GRPC_TIMEOUT = 15


_FAILURE_KEYWORDS = {
    "it": ["non ho capito", "mi dispiace", "scusa", "non posso", "non riesco",
           "non posso aiutarti", "non so", "non capisco", "impossibile",
           "mi ripeti", "puoi ripetere", "ripeti cosa"],
    "en": ["i don't understand", "i'm sorry", "i can't", "i cannot",
           "i don't know", "i'm not able", "unable to", "i'm afraid",
           "repeat that", "say that again", "can you repeat"],
    "de": ["habe ich nicht verstanden", "es tut mir leid", "kann ich nicht",
           "weiß ich nicht", "leider nicht",
           "wiederholen", "wie bitte", "nochmal"],
    "fr": ["je n'ai pas compris", "je suis desole", "je ne peux pas",
           "je ne sais pas", "desole", "impossible",
           "repetez", "repeter", "peux-tu repeter", "comment"],
    "es": ["no he entendido", "lo siento", "no puedo", "no se",
           "no lo se", "imposible", "disculpa",
           "repitelo", "puedes repetir", "repite"],
    "pt": ["nao entendi", "sinto muito", "nao posso", "nao sei",
           "desculpa", "impossivel",
           "repita", "pode repetir", "pode dizer de novo"],
    "ja": ["わかりません", "ごめんなさい", "できません", "申し訳ありません",
           "もう一度", "繰り返して", "何です"],
    "ko": ["이해하지 못했습니다", "죄송합니다", "할 수 없습니다", "모르겠습니다",
           "다시 말씀해", "다시 말해", "반복"],
    "zh": ["我不明白", "对不起", "我不能", "我不知道", "抱歉",
           "再说一次", "重复", "请重复", "再说一遍"],
}


def _classify_gh_response(audio_bytes, lang="it"):
    if not audio_bytes:
        return True
    try:
        import numpy as np
        arr = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        from faster_whisper import WhisperModel
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(arr, language=lang[:2], beam_size=1,
                                       word_timestamps=False)
        text = " ".join([seg.text for seg in segments]).lower().strip()
        keywords = _FAILURE_KEYWORDS.get(lang[:2] if len(lang) > 1 else lang, _FAILURE_KEYWORDS["en"])
        for kw in keywords:
            if kw in text:
                print(f"[GoogleHome] Failure detected: '{text}' (matched '{kw}')")
                return False
        print(f"[GoogleHome] Response: '{text}' -> success")
        return True
    except Exception as e:
        print(f"[GoogleHome] Classification error: {e}")
        return True


class GoogleHome:
    def __init__(self, model_id="", device_id="", lang="it"):
        self._model_id = model_id
        self._device_id = device_id
        self._lang = lang
        self._channel = None
        self._stub = None

    @property
    def configured(self):
        return bool(self._model_id and self._device_id)

    def send_text_query(self, text):
        if not self.configured:
            return {"error": "not_configured"}
        creds = get_google_credentials()
        if not creds:
            return {"error": "not_authenticated"}

        channel = None
        try:
            channel = google.auth.transport.grpc.secure_authorized_channel(
                creds, google.auth.transport.requests.Request(), ENDPOINT
            )
            stub = _pb_grpc.EmbeddedAssistantStub(channel)

            assistant_lang = ASSISTANT_LANGS.get(self._lang, "en-US")
            config = _pb.AssistConfig()
            config.text_query = text
            config.audio_out_config.encoding = _pb.AudioOutConfig.LINEAR16
            config.audio_out_config.sample_rate_hertz = 24000
            config.screen_out_config.screen_mode = _pb.ScreenOutConfig.OFF
            config.dialog_state_in.language_code = assistant_lang
            config.dialog_state_in.is_new_conversation = True
            config.device_config.device_id = self._device_id
            config.device_config.device_model_id = self._model_id

            response_text = ""
            response_audio = b""

            for resp in stub.Assist(self._gen_requests(config), timeout=GRPC_TIMEOUT):
                if resp.dialog_state_out and resp.dialog_state_out.supplemental_display_text:
                    response_text += resp.dialog_state_out.supplemental_display_text + "\n"
                if resp.audio_out and resp.audio_out.audio_data:
                    response_audio += resp.audio_out.audio_data

            response_text = response_text.strip()
            return {"text": response_text or "", "audio": response_audio}
        except grpc.RpcError as e:
            code = e.code()
            msg = _clean_grpc_error(code, e.details())
            print(f"[GoogleHome] gRPC error: {msg}")
            return {"error": msg}
        except Exception as e:
            print(f"[GoogleHome] Error: {e}")
            return {"error": str(e)[:200]}
        finally:
            if channel:
                channel.close()

    def play_audio_response(self, audio_bytes, output_device=None, volume=1.0):
        if not audio_bytes:
            return False
        try:
            import soundfile as sf
            import sounddevice as sd
            import numpy as np
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()
            arr = np.frombuffer(audio_bytes, dtype=np.int16)
            arr = arr.astype(np.float32) / 32768.0
            sf.write(tmp_path, arr, 24000)
            data, sr = sf.read(tmp_path)
            sd.play(data * volume, sr, device=output_device)
            sd.wait()
            os.unlink(tmp_path)
            return True
        except Exception as e:
            print(f"[GoogleHome] Audio playback error: {e}")
            return False

    def close(self):
        pass

    @staticmethod
    def _gen_requests(config):
        yield _pb.AssistRequest(config=config)


def _clean_grpc_error(code, details):
    if code == grpc.StatusCode.UNAUTHENTICATED:
        return "auth_expired"
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return "invalid_request"
    if code == grpc.StatusCode.PERMISSION_DENIED:
        return "permission_denied"
    if code == grpc.StatusCode.UNAVAILABLE:
        return "service_unavailable"
    if code == grpc.StatusCode.DEADLINE_EXCEEDED:
        return "timeout"
    return details[:200]
