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

    def play_audio_response(self, audio_bytes, output_device=None):
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
            sd.play(data, sr, device=output_device)
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
