import os
import logging
import phonenumbers
from phonenumbers import geocoder, carrier, PhoneNumberFormat

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from supabase import create_client


# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(level=logging.INFO)


# ---------------- HELPERS ----------------
def normalize_number(raw, region="IN"):
    try:
        if not raw.startswith("+"):
            parsed = phonenumbers.parse(raw, region)
        else:
            parsed = phonenumbers.parse(raw)
        if not phonenumbers.is_valid_number(parsed):
            return None
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except Exception:
        return None


def get_owner(number):
    res = supabase.table("numbers").select("owner").eq("number", number).execute()
    if res.data:
        return res.data[0]["owner"]
    return None


def save_owner(number, owner):
    supabase.table("numbers").upsert({
        "number": number,
        "owner": owner
    }).execute()


def build_message(number):
    parsed = phonenumbers.parse(number)
    loc = geocoder.description_for_number(parsed, "en") or "Unknown"
    car = carrier.name_for_number(parsed, "en") or "Unknown"
    owner = get_owner(number)

    msg = (
        "📞 *Phone Number Info*\n\n"
        f"• *Number:* `{number}`\n"
        f"• *Carrier:* {car}\n"
        f"• *Location:* {loc}\n"
    )

    if owner:
        msg += f"• *Owner:* {owner}\n"
    else:
        msg += "• *Owner:* Not available\n"
        msg += f"\n➕ Add name:\n`/add {number} Name`\n"

    return msg


# ---------------- BOT HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is running. Send a phone number.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    number = normalize_number(update.message.text)
    if not number:
        await update.message.reply_text("❌ Invalid number format.")
        return
    await update.message.reply_markdown(build_message(number))


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usage:\n/add +91XXXXXXXXXX Name")
        return
    number = normalize_number(context.args[0])
    if not number:
        await update.message.reply_text("❌ Invalid number.")
        return
    owner = " ".join(context.args[1:])
    save_owner(number, owner)
    await update.message.reply_text(f"✅ Saved: {number} → {owner}")


# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
