from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from contextlib import asynccontextmanager
import re

# Token de tu Bot de Telegram
TOKEN = "8877460148:AAFCj67-o34iLWiKvdVEltCVYjJiAP4eM7I"
# URL de tu servidor en Render
BASE_URL = "https://onrender.com"

# Diccionario temporal en memoria para almacenar pagos recibidos
pagos_recibidos = {}

# Inicialización de la aplicación de Telegram y el Bot
telegram_app = Application.builder().token(TOKEN).build()
bot = Bot(token=TOKEN)

# --- CONFIGURACIÓN DE LIFESPAN (Arranque moderno de FastAPI) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Código que se ejecuta al arrancar el servidor
    await telegram_app.initialize()
    await telegram_app.start()
    # Conecta tu bot directamente con los servidores de Telegram
    await bot.set_webhook(url=f"{BASE_URL}/webhook-telegram")
    
    yield  # Aquí es donde el servidor se queda escuchando peticiones
    
    # Código que se ejecuta al apagarse el servidor
    await telegram_app.stop()
    await telegram_app.shutdown()

# Creamos la aplicación FastAPI asignándole el gestor de ciclo de vida
app = FastAPI(lifespan=lifespan)

class SMSData(BaseModel):
    mensaje: str

# --- ENDPOINTS DEL SERVIDOR ---

@app.get("/")
def inicio():
    return {"status": "servidor_activo", "bot": "Configurado correctamente"}

@app.post("/webhook-sms")
async def recibir_sms(data: SMSData):
    texto = data.mensaje
    try:
        # Extrae la referencia del SMS del BDV (Ej: Ref: 12345678)
        referencia = re.search(r"Ref:\s*(\d+)", texto).group(1)
        # Extrae el monto del SMS del BDV (Ej: Bs. 150,00)
        monto_str = re.search(r"Bs\.\s*([\d\.,]+)", texto).group(1)
        
        # Limpiamos el monto quitando los puntos de miles
        monto_limpio = monto_str.replace(".", "")
        
        pagos_recibidos[referencia] = {
            "monto": monto_limpio,
            "usado": False
        }
        return {"status": "success", "referencia": referencia, "monto": monto_limpio}
    except AttributeError:
        return {"status": "ignored", "reason": "El SMS no contiene un formato valido de pago BDV"}

@app.post("/webhook-telegram")
async def webhook_telegram(request: Request):
    """Recibe los mensajes que envían los usuarios al Bot de Telegram"""
    data = await request.json()
    update = Update.de_json(data, bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}

# --- LÓGICA DEL BOT DE TELEGRAM ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida al presionar /start"""
    texto_bienvenida = (
        "👋 ¡Hola! Bienvenido al sistema automatizado de verificación de pagos.\n\n"
        "Para validar tu Pago Móvil, por favor envíame el **Número de Referencia** de tu transacción.\n\n"
        "Escribe los números directamente en el chat para procesar la verificación."
    )
    await update.message.reply_text(texto_bienvenida, parse_mode="Markdown")

async def procesar_mensaje_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa cualquier texto que envíe el usuario buscando una referencia"""
    texto_usuario = update.message.text.strip()
    
    # Buscamos si el usuario envió un número largo (potencial referencia de 6 a 12 dígitos)
    match_ref = re.search(r"\b(\d{6,12})\b", texto_usuario)
    
    if not match_ref:
        await update.message.reply_text(
            "❌ No logré identificar un número de referencia válido.\n"
            "Por favor, envíame únicamente los números de la referencia de tu pago (de 6 a 12 dígitos)."
        )
        return
        
    referencia = match_ref.group(1)
    
    # Verificación de la referencia registrada en memoria
    if referencia in pagos_recibidos:
        pago = pagos_recibidos[referencia]
        
        if pago["usado"]:
            await update.message.reply_text("⚠️ Esta referencia ya fue registrada y utilizada previamente para otro pago.")
            return
            
        # Marcamos el pago como aprobado para prevenir doble uso
        pago["usado"] = True
        monto_pago = pago["monto"]
        
        await update.message.reply_text(
            f"✅ ¡Pago Verificado Exitosamente!\n\n"
            f"🔹 **Referencia:** {referencia}\n"
            f"🔹 **Monto:** Bs. {monto_pago}\n\n"
            f"¡Tu orden o servicio ha sido procesado con éxito!"
        )
    else:
        await update.message.reply_text(
            f"🔍 Buscando la referencia **{referencia}**...\n\n"
            f"❌ Aún no hemos recibido la notificación de este pago en nuestra cuenta bancaria.\n"
            f"Asegúrate de que el pago se haya realizado con éxito al teléfono correcto o intenta nuevamente en unos minutos."
        )

# Configuración de los comandos del Bot
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar_mensaje_usuario))
