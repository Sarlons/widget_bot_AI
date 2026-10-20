import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- PERCORSI ---
PROJECT_1_DIR = os.path.dirname(os.path.abspath(__file__))
DESKTOP_DIR = os.path.dirname(PROJECT_1_DIR)
LOCAL_CLAUDE_INSTRUCTIONS_DIR = os.path.join(DESKTOP_DIR, "local claude instructions")
SUMMARY_FILE = os.path.join(PROJECT_1_DIR, "orchestrator_summary.md")

ADMIN_TELEGRAM_ID = 736509520  # IL TUO ID TELEGRAM

def get_projects():
    projects = []
    for entry in os.scandir(PROJECT_1_DIR):
        if entry.is_dir() and os.path.exists(os.path.join(entry.path, "TODO.md")):
            projects.append(entry.name)
    return sorted(projects)

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_TELEGRAM_ID

async def generate_orchestrator_summary():
    """Legge i file di istruzioni dai percorsi mirati e compila il manuale operativo."""
    if not os.path.exists(LOCAL_CLAUDE_INSTRUCTIONS_DIR):
        return False
        
    all_texts = []
    for entry in os.scandir(LOCAL_CLAUDE_INSTRUCTIONS_DIR):
        if entry.is_file() and entry.name.endswith(".md"):
            try:
                with open(entry.path, "r", encoding="utf-8") as f:
                    all_texts.append(f"--- FILE: {entry.name} ---\n" + f.read())
            except Exception as e:
                print(f"[ERRORE] Impossibile leggere {entry.path}: {e}")

    if not all_texts:
        return False

    full_context = "\n\n".join(all_texts)
    prompt = (
        "Sei il Lead AI Agent. Leggi queste 'local claude instructions'. "
        "Estrapola un 'Manuale di Esecuzione' imperativo per te stesso (Qwen) "
        "con Ruolo, Protocollo d'Attacco, Uso Strumenti (Swarm) e Regole di Chiusura."
    )

    process = await asyncio.create_subprocess_exec(
        "ollama", "run", "qwen2.5:7b",
        f"{prompt}\n\nDOCUMENTAZIONE:\n{full_context[:14000]}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
        output = stdout.decode().strip()
        if process.returncode == 0 and output:
            with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
                f.write("# MANUALE OPERATIVO (SINTESI MIRATA)\n\n" + output)
            return True
    except asyncio.TimeoutError:
        print("[ERRORE] Timeout durante la generazione della sintesi.")
    return False

async def set_bot_commands(app):
    """Configura il menu dei comandi persistente in basso a sinistra su Telegram."""
    commands = [
        BotCommand("start", "Apri la Dashboard Sviluppatore"),
        BotCommand("menu", "Menu principale dei progetti")
    ]
    await app.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    
    # Resetta lo stato della chat attiva
    context.user_data["awaiting_qwen_task"] = False
    
    if not os.path.exists(SUMMARY_FILE):
        await generate_orchestrator_summary()

    projects = get_projects()
    if not projects:
        msg = "Nessun progetto trovato con TODO.md"
        if update.callback_query:
            await update.callback_query.message.edit_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    keyboard = [[InlineKeyboardButton(f"📁 {p}", callback_data=f"devproj_{p}")] for p in projects]
    keyboard.append([InlineKeyboardButton("🔄 Rigenera Sintesi Direttive", callback_data="refresh_summary")])
    
    text = "🛠️ **Dashboard Sviluppatore**\nSeleziona un progetto:"
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(update): return
    await query.answer()

    if query.data == "dev_main_menu":
        context.user_data["awaiting_qwen_task"] = False
        await start(update, context)
    
    elif query.data == "refresh_summary":
        await query.message.edit_text("⏳ Compressione direttive in corso...")
        if await generate_orchestrator_summary():
            await query.message.reply_text("✅ Sintesi aggiornata!")
        await start(update, context)

    elif query.data.startswith("devproj_"):
        project = query.data.replace("devproj_", "")
        context.user_data["active_dev_project"] = project
        context.user_data["awaiting_qwen_task"] = False
        
        kb = [
            [InlineKeyboardButton("⚡ Invia Task a Qwen", callback_data=f"cmdqwen_{project}")],
            [InlineKeyboardButton("🔄 Analizza Feedback Community", callback_data=f"runfeed_{project}")],
            [InlineKeyboardButton("⬅️ Torna al Menu", callback_data="dev_main_menu")]
        ]
        await query.message.edit_text(f"🎯 **Progetto: `{project}`**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

    elif query.data.startswith("cmdqwen_"):
        context.user_data["awaiting_qwen_task"] = True
        kb = [[InlineKeyboardButton("🛑 Termina Chat / Torna al Menu", callback_data="dev_main_menu")]]
        await query.message.reply_text(
            "🤖 **Chat con Qwen attiva.** Scrivi il tuo ordine.\n"
            "Qwen eseguirà il task tramite Aider rispettando le direttive.\n"
            "Quando hai finito, clicca il pulsante sotto per uscire.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif query.data.startswith("runfeed_"):
        project = query.data.replace("runfeed_", "")
        script_path = os.path.join(PROJECT_1_DIR, project, "run_analysis.py")
        
        await query.message.reply_text(f"⏳ Analisi feedback in corso per `{project}`...", parse_mode="Markdown")
        process = await asyncio.create_subprocess_exec("python", script_path, cwd=os.path.join(PROJECT_1_DIR, project), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            await asyncio.wait_for(process.communicate(), timeout=90)
            await query.message.reply_text(f"✅ Analisi feedback completata per `{project}`!", parse_mode="Markdown")
        except asyncio.TimeoutError:
            await query.message.reply_text("❌ Timeout scaduto durante l'analisi dei feedback.")

async def handle_dev_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not context.user_data.get("awaiting_qwen_task"): 
        return
    
    project = context.user_data["active_dev_project"]
    task = update.message.text

    # Messaggio con rotella di caricamento iniziale
    status_msg = await update.message.reply_text(f"⏳ **Qwen sta elaborando il task su `{project}`...** 🔄", parse_mode="Markdown")

    enforced_task = f"ATTENZIONE QWEN: Applica rigorosamente le istruzioni in 'orchestrator_summary.md'.\n\nTASK: {task}"
    cmd = [
        "aider", 
        "--model", "ollama/qwen2.5:7b", 
        "--message", enforced_task, 
        "--yes-always", 
        "--no-show-model-warnings", 
        "CLAUDE.md", "DESIGN.md", "TODO.md"
    ]
    if os.path.exists(SUMMARY_FILE): 
        cmd.extend(["--read", SUMMARY_FILE])

    process = await asyncio.create_subprocess_exec(
        *cmd, 
        cwd=os.path.join(PROJECT_1_DIR, project), 
        stdout=asyncio.subprocess.PIPE, 
        stderr=asyncio.subprocess.PIPE
    )
    
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
        
        # Rimaniamo in chat attiva: l'utente può continuare a scrivere o chiudere col pulsante
        kb = [[InlineKeyboardButton("🛑 Termina Chat / Torna al Menu", callback_data="dev_main_menu")]]
        
        if process.returncode == 0:
            output_log = stdout.decode().strip()
            # Estraiamo un riassunto pulito o le ultime righe rilevanti del log di Aider
            summary_snippet = output_log[-1000:] if len(output_log) > 1000 else output_log
            
            report = (
                f"✅ **Task Completato con Successo!**\n\n"
                f"📋 **Progetto:** `{project}`\n"
                f"⚙️ **Swarm/Aider:** Eseguito correttamente.\n"
                f"📝 **Log sintetico:**\n```\n{summary_snippet}\n```\n\n"
                f"*(La chat con Qwen è ancora attiva. Scrivi un altro comando oppure chiudi sotto:)*"
            )
            await status_msg.edit_text(report, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        else:
            err_snippet = stderr.decode().strip()[-1000:]
            report = f"❌ **Errore durante l'esecuzione:**\n```\n{err_snippet}\n```"
            await status_msg.edit_text(report, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            
    except asyncio.TimeoutError:
        kb = [[InlineKeyboardButton("🛑 Torna al Menu", callback_data="dev_main_menu")]]
        await status_msg.edit_text("❌ **Timeout scaduto!** L'operazione con Aider ha impiegato troppo tempo.", reply_markup=InlineKeyboardMarkup(kb))

if __name__ == "__main__":
    DEV_BOT_TOKEN = "8667133916:AAFR8qu0cFQSFCEWOKmvRxawupHmOCP1zbU"

    app = ApplicationBuilder().token(DEV_BOT_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).build()

    # Registra i comandi e i gestori
    app.job_queue.run_once(lambda ctx: asyncio.create_task(set_bot_commands(app)), 1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dev_message))

    print("🚀 Dev Bot avviato con menu pulito e chat persistente...")
    app.run_polling()
