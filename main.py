from fastapi import FastAPI, Request, Response, status
from pydantic import BaseModel
from contextlib import asynccontextmanager
import requests
import re
import time

TOKEN = "8877460148:AAFCj67-o34iLWiKvdVEltCVYjJiAP4eM7I"
TELEGRAM_API = f"https://telegram.org{TOKEN}"
BASE_URL = "https://onrender.com"

# Base de datos en memoria para almacenar las referencias de Pago Móvil
pagos_recibidos = {}

class SMSData(BaseModel):
    mensaje: str

def forzar_desbloqueo_y_conexion_telegram():
    """Borra cualquier bloqueo previo en Telegram y establece la conexión limpia"""
    url_webhook = f"{BASE_URL}/webhook-telegram"
    try:
        # 1. Le ordenamos a Telegram borrar cualquier configuración vieja o bloqueada
        requests.post(f"{TELEGRAM_API}/deleteWebhook")
        time.sleep(1) # Pausa de seguridad
        
        # 2. Establecemos la conexión nueva y limpia
        response = requests.post(f"{TELEGRAM_API}/setWebhook", json={"url": url_webhook})
        print(f"DESBLOQUEO Y CONEXION EXITOSA: {response.json()}")
    except Exception as e:
        print(f"Error al conectar con Telegram: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Esto ejecuta el desbloqueo automático inmediatamente al encender el servidor en Render
    forzar_desbloqueo_y_conexion_telegram()
    yield

# Inicializamos FastAPI con el ciclo de vida Lifespan
app = FastAPI(lifespan=lifespan)

@app.get("/")
def inicio():
    return {"status": "servidor_activo", "mensaje": "Validador Desbloqueado y Activo"}

@app.post("/webhook-sms")
def recibir_sms(data: SMSData):
    texto = data.mensaje
    try:
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
    """Procesa los mensajes enviados por tus clientes en Telegram"""
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)
        
    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        texto_usuario = data["message"]["text"].strip()
        
        # Comando /start
        if texto_usuario.startswith("/start"):
            mensaje_bienvenida = (
                "👋 ¡Hola! Bienvenido al sistema automatizado de verificación de pagos.\n\n"
                "Para validar tu Pago Móvil, por favor envíame el **Número de Referencia** de tu transacción."
            )
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_bienvenida, "parse_mode": "Markdown"})
            return {"ok": True}
        
        # Buscar número de referencia de 6 a 12 dígitos
        match_ref = re.search(r"\b(\d{6,12})\b", texto_usuario)
        if not match_ref:
            mensaje_error = "❌ No logré identificar una referencia válida.\nPor favor, envíame solo los números de tu referencia (de 6 a 12 dígitos)."
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_error})
            return {"ok": True}
            
        referencia = match_ref.group(1)
        
        # Validación interna contra el diccionario de pagos
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
            requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": mensaje_no_encontrado, "parse_mode": "Markdown"})
                
    return {"ok": True}
