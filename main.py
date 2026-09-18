from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel
import requests
import re

app = FastAPI()

# Tu nuevo Token limpio y tu enlace oficial de Render
TOKEN = "8715321676:AAFSeZupHZrp4zT_qxRJ8UzkN27k55JL6B4"
TELEGRAM_API = f"https://telegram.org{TOKEN}"
BASE_URL = "https://onrender.com"

# Base de datos en memoria para guardar las referencias de Pago Móvil del teléfono
pagos_recibidos = {}

class SMSData(BaseModel):
    mensaje: str

@app.get("/")
def inicio():
    return {"status": "servidor_activo", "mensaje": "Validador Directo Mirvi Style Activo"}

@app.get("/activar-bot")
def activar_bot():
    """Interruptor manual para conectar Telegram con Render sin bloqueos de red"""
    url_webhook = f"{BASE_URL}/webhook-telegram"
    try:
        requests.get(f"{TELEGRAM_API}/deleteWebhook")
        response = requests.get(f"{TELEGRAM_API}/setWebhook", params={"url": url_webhook})
        return {"status": "proceso_completado", "respuesta_telegram": response.json()}
    except Exception as e:
        return {"status": "error", "detalle": str(e)}

@app.post("/webhook-sms")
def recibir_sms(data: SMSData):
    texto = data.mensaje
    try:
        # Captura los datos oficiales del mensaje del Banco de Venezuela (BDV)
        referencia = re.search(r"Ref:\s*(\d+)", texto).group(1)
        monto_str = re.search(r"Bs\.\s*([\d\.,]+)", texto).group(1)
        monto_limpio = monto_str.replace(".", "")
        
        pagos_recibidos[referencia] = {
            "monto": monto_limpio,
            "usado": False
        }
        return {"status": "success", "referencia": referencia}
    except AttributeError:
        return {"status": "ignored"}

@app.post("/webhook-telegram")
async def webhook_telegram(request: Request):
    """Procesa los mensajes enviados por tus clientes en el nuevo Bot"""
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
        
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        texto_usuario = data["message"]["text"].strip()
        
        # Comando /start en el chat
        if texto_usuario.startswith("/start"):
            mensaje_bienvenida = (
                "👋 ¡Hola! Bienvenido al sistema automatizado de verificación de pagos.\n\n"
                "Para validar tu Pago Móvil, por favor envíame el **Número de Referencia** de tu transacción."
            )
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_bienvenida})
            return {"ok": True}
        
        # Filtra que el usuario mande una referencia de 6 a 12 dígitos
        match_ref = re.search(r"\b(\d{6,12})\b", texto_usuario)
        if not match_ref:
            mensaje_error = "❌ No logré identificar una referencia válida.\nPor favor, envíame solo los números de tu referencia (de 6 a 12 dígitos)."
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_error})
            return {"ok": True}
            
        referencia = match_ref.group(1)
        
        # Validación cruzada contra la memoria del servidor
        if referencia in pagos_recibidos:
            pago = pagos_recibidos[referencia]
            if pago["usado"]:
                requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": "⚠️ Esta referencia ya fue registrada previamente para otro pago."})
            else:
                pago["usado"] = True
                monto_pago = pago["monto"]
                mensaje_exito = f"✅ ¡Pago Verificado Exitosamente!\n\n🔹 **Referencia:** {referencia}\n🔹 **Monto:** Bs. {monto_pago}\n\n¡Tu orden ha sido procesada!"
                requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_exito})
        else:
            mensaje_no_encontrado = f"🔍 Buscando la referencia **{referencia}**...\n\n❌ Aún no hemos recibido la notificación de este pago en nuestra cuenta bancaria.\n\nIntenta nuevamente en unos minutos."
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_no_encontrado})
                
    return {"ok": True}
