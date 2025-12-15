from supabase import create_client, Client
import phonenumbers
from phonenumbers import geocoder, carrier, PhoneNumberFormat

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler


# ----------------------------------------------------
# SUPABASE CONFIG
# ----------------------------------------------------
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# Registration states
REG_NUMBER, REG_NAME, REG_AADHAAR, REG_EMAIL, REG_ALT_MOBILE, REG_ADDRESS = range(6)


# ----------------------------------------------------
# NORMALIZE NUMBER
# ----------------------------------------------------
def normalize_number(raw_input, default_region="IN"):
    try:
        if default_region and not raw_input.startswith("+"):
            parsed = phonenumbers.parse(raw_input, default_region)
        else:
            parsed = phonenumbers.parse(raw_input)
        if not phonenumbers.is_possible_number(parsed):
            return None
        return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except:
        return None


# ----------------------------------------------------
# LOOKUP NAME FROM CLOUD DB
# ----------------------------------------------------
def lookup_owner(e164):
    result = supabase.table("numbers").select("*").eq("number", e164).execute()
    if result.data:
        return result.data[0]
    return None


# ----------------------------------------------------
# INSERT OR UPDATE NAME IN CLOUD DB
# ----------------------------------------------------
def save_owner(e164, name, location=None, aadhaar=None, email=None, alternate_mobile=None, full_address=None):
    supabase.table("numbers").upsert({
        "number": e164,
        "owner": name,
        "location": location,
        "aadhaar": aadhaar,
        "email": email,
        "alternate_mobile": alternate_mobile,
        "full_address": full_address
    }).execute()


# ----------------------------------------------------
# FORMAT INFO FOR TELEGRAM
# ----------------------------------------------------
def format_info(e164):
    db_entry = lookup_owner(e164)

    parsed = phonenumbers.parse(e164)
    sim_car = carrier.name_for_number(parsed, "en") or "Unknown"
    sim_loc = geocoder.description_for_number(parsed, "en") or "Unknown"

    message = "📞 *Phone Number Information*\n\n"
    message += f"• *Number:* `{e164}`\n"

    if db_entry:
        message += f"• *Owner:* {db_entry['owner']}\n"
        
        if db_entry.get("aadhaar"):
            message += f"• *Aadhaar:* {db_entry['aadhaar']}\n"
        
        if db_entry.get("email"):
            message += f"• *Email:* {db_entry['email']}\n"
        
        if db_entry.get("alternate_mobile"):
            message += f"• *Alternate Mobile:* {db_entry['alternate_mobile']}\n"
        
        if db_entry.get("location"):
            message += f"• *Location:* {db_entry['location']}\n"
        
        if db_entry.get("full_address"):
            message += f"• *Full Address:* {db_entry['full_address']}\n"
    else:
        message += "• *Owner:* Not in database\n"

    message += f"• *Carrier:* {sim_car}\n"
    message += f"• *Network Location:* {sim_loc}\n"

    if not db_entry:
        message += f"\n\n⚠️ *Not in database!*\nTo register this number:\n`/register`"

    return message


# ----------------------------------------------------
# TELEGRAM HANDLERS
# ----------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cloud bot active! Send a phone number.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    e164 = normalize_number(raw)

    if not e164:
        await update.message.reply_text("Invalid number format.")
        return

    message = format_info(e164)
    await update.message.reply_markdown(message)


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        number = context.args[0]
        name = context.args[1] if len(context.args) > 1 else None
        
        if not name:
            await update.message.reply_text(
                "Use format:\n"
                "`/add +91XXXXXXXXXX OwnerName`\n\n"
                "Or with full details:\n"
                "`/add_full +91XXXXXXXXXX OwnerName Aadhaar Email AlternateMobile FullAddress`"
            )
            return
            
    except:
        await update.message.reply_text(
            "Use format:\n"
            "`/add +91XXXXXXXXXX OwnerName`"
        )
        return

    e164 = normalize_number(number)
    if not e164:
        await update.message.reply_text("Invalid number format.")
        return

    save_owner(e164, name)
    await update.message.reply_text(f"✔ Saved to cloud:\n{e164} → {name}")


async def add_full_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        number = context.args[0]
        name = context.args[1] if len(context.args) > 1 else None
        aadhaar = context.args[2] if len(context.args) > 2 else None
        email = context.args[3] if len(context.args) > 3 else None
        alternate_mobile = context.args[4] if len(context.args) > 4 else None
        full_address = " ".join(context.args[5:]) if len(context.args) > 5 else None
        
    except:
        await update.message.reply_text(
            "Use format:\n"
            "`/add_full +91XXXXXXXXXX OwnerName Aadhaar Email AlternateMobile FullAddress`"
        )
        return

    e164 = normalize_number(number)
    if not e164:
        await update.message.reply_text("Invalid number format.")
        return

    save_owner(e164, name, None, aadhaar, email, alternate_mobile, full_address)
    await update.message.reply_text(
        f"✔ Saved to cloud:\n"
        f"📞 {e164}\n"
        f"👤 Owner: {name}\n"
        f"🆔 Aadhaar: {aadhaar or 'N/A'}\n"
        f"📧 Email: {email or 'N/A'}\n"
        f"📱 Alt Mobile: {alternate_mobile or 'N/A'}\n"
        f"🏠 Address: {full_address or 'N/A'}"
    )


# ====================================================
# REGISTRATION FLOW
# ====================================================
async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 *Registration Started*\n\n"
        "Enter your phone number (with country code):\n"
        "Example: +91XXXXXXXXXX or 91XXXXXXXXXX"
    )
    return REG_NUMBER


async def register_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_number = update.message.text.strip()
    e164 = normalize_number(raw_number)
    
    if not e164:
        await update.message.reply_text("❌ Invalid number format. Try again with country code.")
        return REG_NUMBER
    
    # Check if already registered
    if lookup_owner(e164):
        await update.message.reply_text(f"✔ This number {e164} is already registered!")
        return ConversationHandler.END
    
    context.user_data['phone_number'] = e164
    await update.message.reply_text(f"✅ Phone: {e164}\n\nNow enter your full name:")
    return REG_NAME


async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name or len(name) < 2:
        await update.message.reply_text("❌ Please enter a valid name.")
        return REG_NAME
    
    context.user_data['name'] = name
    await update.message.reply_text(f"✅ Name: {name}\n\nEnter your Aadhaar number (12 digits):\n(or type 'skip' to skip)")
    return REG_AADHAAR


async def register_aadhaar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text.lower() == 'skip':
        context.user_data['aadhaar'] = None
    else:
        if not text.isdigit() or len(text) != 12:
            await update.message.reply_text("❌ Aadhaar must be 12 digits. Try again or type 'skip':")
            return REG_AADHAAR
        context.user_data['aadhaar'] = text
    
    aadhaar_display = context.user_data['aadhaar'] or 'Skipped'
    await update.message.reply_text(f"✅ Aadhaar: {aadhaar_display}\n\nEnter your email address:\n(or type 'skip' to skip)")
    return REG_EMAIL


async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text.lower() == 'skip':
        context.user_data['email'] = None
    else:
        if '@' not in text:
            await update.message.reply_text("❌ Invalid email format. Try again or type 'skip':")
            return REG_EMAIL
        context.user_data['email'] = text
    
    email_display = context.user_data['email'] or 'Skipped'
    await update.message.reply_text(f"✅ Email: {email_display}\n\nEnter your alternate mobile number:\n(or type 'skip' to skip)")
    return REG_ALT_MOBILE


async def register_alt_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text.lower() == 'skip':
        context.user_data['alternate_mobile'] = None
    else:
        alt_e164 = normalize_number(text)
        if not alt_e164:
            await update.message.reply_text("❌ Invalid number format. Try again or type 'skip':")
            return REG_ALT_MOBILE
        context.user_data['alternate_mobile'] = alt_e164
    
    alt_display = context.user_data['alternate_mobile'] or 'Skipped'
    await update.message.reply_text(f"✅ Alternate Mobile: {alt_display}\n\nEnter your full address:\n(or type 'skip' to skip)")
    return REG_ADDRESS


async def register_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text.lower() == 'skip':
        context.user_data['full_address'] = None
    else:
        context.user_data['full_address'] = text
    
    # Save all data to database
    phone_number = context.user_data['phone_number']
    name = context.user_data['name']
    aadhaar = context.user_data.get('aadhaar')
    email = context.user_data.get('email')
    alternate_mobile = context.user_data.get('alternate_mobile')
    full_address = context.user_data.get('full_address')
    
    save_owner(phone_number, name, None, aadhaar, email, alternate_mobile, full_address)
    
    await update.message.reply_text(
        f"✅ *Registration Complete!*\n\n"
        f"📞 Phone: {phone_number}\n"
        f"👤 Name: {name}\n"
        f"🆔 Aadhaar: {aadhaar or 'N/A'}\n"
        f"📧 Email: {email or 'N/A'}\n"
        f"📱 Alt Mobile: {alternate_mobile or 'N/A'}\n"
        f"🏠 Address: {full_address or 'N/A'}\n\n"
        f"Your data has been saved! 🎉"
    )
    return ConversationHandler.END


async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Registration cancelled.")
    return ConversationHandler.END


# ----------------------------------------------------
# RUN BOT
# ----------------------------------------------------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Registration conversation handler
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("register", start_register)],
        states={
            REG_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_number)],
            REG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REG_AADHAAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_aadhaar)],
            REG_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
            REG_ALT_MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_alt_mobile)],
            REG_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel_register)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("add_full", add_full_cmd))
    app.add_handler(reg_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("☁️ Cloud Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
