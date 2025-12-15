import os
import json
import asyncio
import uuid
import base64
from typing import Dict, Optional
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import VoiceResponse, Connect, Start

from amivoice_client import AmiVoiceClient
from llm_client import LLMClient
from config import settings



app = FastAPI()

# Global Session Store
# request_id or call_sid -> Session
sessions: Dict[str, 'Session'] = {}

class Session:
    def __init__(self, session_id):
        self.session_id = session_id
        self.relay_ws: Optional[WebSocket] = None
        self.amivoice = AmiVoiceClient(
            app_key=settings.amivoice_appkey,
            on_message=self.on_amivoice_message
        )
        self.llm = LLMClient(api_key=settings.gemini_api_key)
        self.call_active = True
        print(f"[Session {session_id}] Created")

    async def connect_amivoice(self):
        await self.amivoice.connect()

    async def on_amivoice_message(self, data: dict):
        """
        AmiVoiceからのメッセージ受信時のコールバック
        'A' (Final Result) イベントのみを拾ってLLMに送信します
        'A' = Final Result (確定), 'U' = Intermediate Result (途中経過)
        """
        event_code = data.get('code', '')
        text = data.get('text', '')

        if not text:
            # テキストがない場合は処理しない
            return

        # デバッグ用：全てのテキストイベントをログ出力
        if event_code == 'U':
            print(f"[AmiVoice Partial] {text}")
        elif event_code == 'A':
            print(f"[AmiVoice Final] {text}")
        else:
            print(f"[AmiVoice {event_code}] {text}")

        # フィルタリング: 確定結果（'A'）のみLLMへ送る
        if event_code != 'A':
            return

        # LLMでの応答生成を非同期で実行
        asyncio.create_task(self.trigger_response(text))

    async def trigger_response(self, user_text: str):
        """
        LLMに応答生成を依頼し、結果をConversation Relay経由で音声合成させます
        """
        if not self.relay_ws:
            print("[System] No Relay WebSocket to send response.")
            return

        print(f"[LLM] User said: {user_text}")
        
        # 1. Geminiで応答生成
        ai_text = await self.llm.generate_response(user_text)
        print(f"[LLM] Response: {ai_text}")

        # 2. Conversation Relayへテキスト送信 (TTS用)
        # Format: { "type": "text", "token": "...", "last": true, "lang": "ja-JP" }
        msg = {
            "type": "text",
            "token": ai_text,
            "last": True,
            "lang": settings.language_code
        }
        try:
            await self.relay_ws.send_text(json.dumps(msg))
            print(f"[Relay] Sent TTS: {ai_text}")
        except Exception as e:
            print(f"[Relay] Send Error: {e}")

    async def close(self):
        """
        セッション終了時のクリーンアップ
        """
        self.call_active = False
        if self.amivoice:
            await self.amivoice.close()
        # グローバルセッションストアから削除
        if self.session_id in sessions:
            del sessions[self.session_id]
        print(f"[Session {self.session_id}] Closed")


@app.post("/voice")
async def voice(request: Request):
    """
    Twilioからの着信リクエストを受け取るエンドポイント (Webhook)
    TwiML (XML) を返却し、MediaStreamとConversationRelayを開始させます
    ngrok経由の場合、X-Forwarded-Hostを優先してホスト名を取得
    """
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    
    # セッションIDを生成し、WebSocket接続を紐付けるために使用
    session_id = str(uuid.uuid4())
    
    # セッションオブジェクトを作成
    sessions[session_id] = Session(session_id)
    print(f"[Session {session_id}] Created")
    
    response = VoiceResponse()
    
    # 1. Start Media Stream (AmiVoiceへ音声を送るため)
    start = Start()
    stream = start.stream(url=f"wss://{host}/stream")
    # session_id をカスタムパラメータとして埋め込む（/stream 側で取得）
    stream.parameter(name="session_id", value=session_id)
    response.append(start)

    # 2. Connect Conversation Relay (LLM/TTSとの対話用)
    connect = Connect()
    try:
        # ConversationRelayの言語設定 (日本語固定)
        # 親タグでの設定でデフォルト言語を指定
        cr = connect.conversation_relay(
            url=f"wss://{host}/relay?session_id={session_id}",
            language=settings.language_code, 
            tts_provider=settings.tts_provider,
            voice=settings.twilio_voice_name
        )
        # 詳細な言語設定
        cr.language(
            code=settings.language_code,
            tts_provider=settings.tts_provider,
            voice=settings.twilio_voice_name,
            transcription_provider=settings.transcription_provider,
            speech_model=settings.speech_model
        )
    except AttributeError:
        # 古いライブラリ向けのフォールバック実装
        from twilio.twiml import TwiML
        cr = TwiML("ConversationRelay")
        cr.attrs["url"] = f"wss://{host}/relay?session_id={session_id}"
        
        lang = TwiML("Language")
        lang.attrs["code"] = settings.language_code
        lang.attrs["ttsProvider"] = settings.tts_provider
        lang.attrs["voice"] = settings.twilio_voice_name
        lang.attrs["transcriptionProvider"] = settings.transcription_provider
        lang.attrs["speechModel"] = settings.speech_model
        cr.append(lang)
        
        connect.append(cr)
        
    response.append(connect)

    return Response(content=str(response), media_type="application/xml")


@app.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    # Twilio Media Stream用のWebSocketエンドポイント
    # Twilioから送られてくる音声データを受け取り、AmiVoiceへ転送します
    await websocket.accept()
    # session_id は通常、クエリパラメータでは利用できないため、
    # 'start' イベントのカスタムパラメータから取得します。
    
    session = None
    session_id = None

    print(f"[Stream] WebSocket Accepted. Waiting for 'start' event...")

    try:
        while True:
            data = await websocket.receive_text()
            packet = json.loads(data)
            event = packet.get("event")
            
            if event == "start":
                # Media Stream開始 ('start') イベント
                # ここでカスタムパラメータから session_id を取得
                params = packet.get("start", {}).get("customParameters", {})
                session_id = params.get("session_id")
                print(f"[Stream] Start Event. Session ID: {session_id}")
                
                session = sessions.get(session_id)
                if not session:
                    print(f"[Stream] Session {session_id} not found")
                    # セッションが見つからない場合、以降のメディア処理は行わない
                    return
                else:
                    print(f"[Stream] Connected to Session {session_id}")
                    # AmiVoiceへの接続を開始
                    await session.connect_amivoice()

            elif event == "media":
                # 音声データ受信イベント
                if session and session.amivoice:
                    payload = packet["media"]["payload"]
                    chunk = base64.b64decode(payload)
                    # デコードした音声をAmiVoiceへ送信 (8k mulaw)
                    await session.amivoice.send_audio(chunk)
                    
                    # デバッグ: 音声パケットが流れているか確認 (50個ごとに '.' を表示)
                    if not hasattr(session, 'audio_count'):
                        session.audio_count = 0
                    session.audio_count += 1
                    if session.audio_count % 50 == 0:
                        print(".", end="", flush=True)
                
            elif event == "stop":
                print("[Stream] Stopped")
                break
                
    except WebSocketDisconnect:
        print("[Stream] Disconnected")
    except Exception as e:
        print(f"[Stream] Error: {e}")
    finally:
        # Stream側が切断されても、Relay側がアクティブな場合はセッションを閉じない
        pass 

@app.websocket("/relay")
async def websocket_relay(websocket: WebSocket):
    """
    Conversation Relay用のWebSocketエンドポイント
    LLMからの応答テキストをTTS用に送信したり、Twilioからのイベントを受信します
    """
    await websocket.accept()
    session_id = websocket.query_params.get("session_id")
    session = sessions.get(session_id)
    
    if not session:
        print(f"[Relay] Session {session_id} not found")
        await websocket.close()
        return

    print(f"[Relay] Connected for Session {session_id}")
    # セッションにWebSocketを紐付け
    session.relay_ws = websocket

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            # デバッグ: Relayメッセージの内容を全出力
            print(f"[Relay Msg] {msg}")
            
    except WebSocketDisconnect:
        print("[Relay] Disconnected")
    except Exception as e:
        print(f"[Relay] Error: {e}")
    finally:
        await session.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
