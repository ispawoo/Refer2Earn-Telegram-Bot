import logging
from uuid import uuid4
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
)
import sqlite3
import os

# Database setup
def init_db():
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            referral_code TEXT UNIQUE,
            balance REAL DEFAULT 0,
            referred_by TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create referrals table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            amount_earned REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users (user_id),
            FOREIGN KEY (referred_id) REFERENCES users (user_id)
        )
    ''')

    conn.commit()
    conn.close()

# Bot configuration
TOKEN = '8134375600:AAGEE57dxJNcD-tOQtBawMWDMRDJoHjzypY'
GROUP_LINK = 'https://t.me/DownloadNovels'
GROUP_ID = -1571401215  # Replace with your actual group ID
ADMIN_ID = 6026854453  # Replace with your admin user ID

# Bot states
MAIN_MENU, JOIN_GROUP_CHECK, WITHDRAW, EARNING_GUIDE = range(4)

# Initialize database
init_db()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Helper functions
def get_user(user_id):
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()

    # Generate unique referral code
    referral_code = str(uuid4())[:8].upper()

    try:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, referral_code)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, referral_code))
        conn.commit()
    except sqlite3.IntegrityError:
        # User already exists
        pass

    conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def record_referral(referrer_id, referred_id, amount):
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO referrals (referrer_id, referred_id, amount_earned)
        VALUES (?, ?, ?)
    ''', (referrer_id, referred_id, amount))
    conn.commit()
    conn.close()

def get_referral_stats(user_id):
    conn = sqlite3.connect('referral_bot.db')
    cursor = conn.cursor()

    # Get total referrals count
    cursor.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
    total_refs = cursor.fetchone()[0]

    # Get total earnings
    cursor.execute('SELECT COALESCE(SUM(amount_earned), 0) FROM referrals WHERE referrer_id = ?', (user_id,))
    total_earnings = cursor.fetchone()[0]

    # Get referral code
    cursor.execute('SELECT referral_code FROM users WHERE user_id = ?', (user_id,))
    referral_code = cursor.fetchone()[0]

    conn.close()

    return {
        'total_refs': total_refs,
        'total_earnings': total_earnings,
        'referral_code': referral_code
    }

# Bot handlers
def start(update: Update, context: CallbackContext) -> int:
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name)

    # Check if user is in group
    if is_user_in_group(update, context):
        show_main_menu(update, context)
        return MAIN_MENU
    else:
        show_join_group_prompt(update, context)
        return JOIN_GROUP_CHECK

def is_user_in_group(update: Update, context: CallbackContext) -> bool:
    try:
        member = context.bot.get_chat_member(GROUP_ID, update.effective_user.id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking group membership: {e}")
        return False

def show_join_group_prompt(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Join Group", url=GROUP_LINK)],
        [InlineKeyboardButton("✅ I've Joined", callback_data='joined_group')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        "📢 To use this bot, please join our group first!\n\n"
        "After joining, click the button below to continue.",
        reply_markup=reply_markup
    )

def check_join_group(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    if is_user_in_group(update, context):
        query.edit_message_text("Thanks for joining! Here's your menu:")
        show_main_menu(update, context)
        return MAIN_MENU
    else:
        query.answer("You haven't joined the group yet. Please join to continue.", show_alert=True)
        return JOIN_GROUP_CHECK

def show_main_menu(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    stats = get_referral_stats(user_id)

    text = (
        f"👋 Welcome, {user_data[2]}!\n\n"
        f"💰 Your Balance: ${user_data[5]:.2f}\n"
        f"👥 Total Referrals: {stats['total_refs']}\n"
        f"🎯 Your Referral Code: {stats['referral_code']}\n\n"
        "Choose an option below:"
    )

    # 2x2 button layout
    keyboard = [
        [
            InlineKeyboardButton("💵 Check Balance", callback_data='balance'),
            InlineKeyboardButton("👥 Referral Info", callback_data='referral_info')
        ],
        [
            InlineKeyboardButton("📤 Withdraw", callback_data='withdraw'),
            InlineKeyboardButton("📚 Earning Guide", callback_data='earning_guide')
        ],
        [
            InlineKeyboardButton("🔗 My Referral Link", callback_data='my_referral_link')
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
    else:
        update.message.reply_text(text=text, reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    data = query.data

    if data == 'balance':
        show_balance(update, context)
    elif data == 'referral_info':
        show_referral_info(update, context)
    elif data == 'withdraw':
        show_withdraw_options(update, context)
        return WITHDRAW
    elif data == 'earning_guide':
        show_earning_guide(update, context)
        return EARNING_GUIDE
    elif data == 'my_referral_link':
        show_referral_link(update, context)
    elif data == 'back_to_menu':
        show_main_menu(update, context)
        return MAIN_MENU

    return MAIN_MENU

def show_balance(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_data = get_user(user_id)

    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.callback_query.edit_message_text(
        text=f"💰 Your current balance is: ${user_data[5]:.2f}",
        reply_markup=reply_markup
    )

def show_referral_info(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    stats = get_referral_stats(user_id)

    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "👥 Your Referral Stats:\n\n"
        f"🎯 Your Code: {stats['referral_code']}\n"
        f"👥 Total Referrals: {stats['total_refs']}\n"
        f"💰 Total Earnings: ${stats['total_earnings']:.2f}\n\n"
        "Invite friends using your referral link and earn commissions!"
    )

    update.callback_query.edit_message_text(
        text=text,
        reply_markup=reply_markup
    )

def show_referral_link(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_data = get_user(user_id)

    referral_link = f"https://t.me/{context.bot.username}?start={user_data[4]}"

    keyboard = [
        [InlineKeyboardButton("🔗 Share Link", url=f"https://t.me/share/url?url={referral_link}&text=Join%20this%20awesome%20bot%20and%20earn%20money!")],
        [InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "🔗 Your Personal Referral Link:\n\n"
        f"{referral_link}\n\n"
        "Share this link with friends to earn commissions when they join!"
    )

    update.callback_query.edit_message_text(
        text=text,
        reply_markup=reply_markup
    )

def show_withdraw_options(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user_data = get_user(user_id)

    keyboard = [
        [InlineKeyboardButton("PayPal", callback_data='withdraw_paypal')],
        [InlineKeyboardButton("Bank Transfer", callback_data='withdraw_bank')],
        [InlineKeyboardButton("Crypto", callback_data='withdraw_crypto')],
        [InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "📤 Withdrawal Options\n\n"
        f"💰 Available Balance: ${user_data[5]:.2f}\n\n"
        "Minimum withdrawal amount: $10.00\n"
        "Select your preferred withdrawal method:"
    )

    update.callback_query.edit_message_text(
        text=text,
        reply_markup=reply_markup
    )

def process_withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()

    method = query.data.split('_')[1]

    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='withdraw')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        f"To withdraw via {method.capitalize()}, please send a message to @admin with:\n\n"
        "1. Your withdrawal amount\n"
        f"2. Your {method} details\n"
        "3. Your user ID\n\n"
        "Our team will process your request within 24 hours."
    )

    query.edit_message_text(
        text=text,
        reply_markup=reply_markup
    )

    return WITHDRAW

def show_earning_guide(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "📚 Earning Guide\n\n"
        "1. 💰 Earn $5 for each friend who joins using your referral link\n"
        "2. 💸 Earn 10% of your friends' earnings (level 1)\n"
        "3. 🚀 Earn 5% of your friends' friends earnings (level 2)\n\n"
        "🔗 Share your referral link with as many people as possible to maximize your earnings!\n\n"
        "Minimum withdrawal amount is $10."
    )

    update.callback_query.edit_message_text(
        text=text,
        reply_markup=reply_markup
    )

def handle_referral(update: Update, context: CallbackContext):
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name)

    # Check if this is a referral
    if len(context.args) > 0:
        referral_code = context.args[0]
        conn = sqlite3.connect('referral_bot.db')
        cursor = conn.cursor()

        # Check if referral code is valid and not self-referral
        cursor.execute('SELECT user_id FROM users WHERE referral_code = ? AND user_id != ?', 
                      (referral_code, user.id))
        referrer = cursor.fetchone()

        if referrer:
            referrer_id = referrer[0]

            # Check if this user was already referred by someone
            cursor.execute('SELECT referred_by FROM users WHERE user_id = ?', (user.id,))
            existing_ref = cursor.fetchone()[0]

            if not existing_ref:
                # Record the referral
                cursor.execute('UPDATE users SET referred_by = ? WHERE user_id = ?', 
                             (referral_code, user.id))

                # Give bonus to referrer
                bonus_amount = 5.00
                update_balance(referrer_id, bonus_amount)
                record_referral(referrer_id, user.id, bonus_amount)

                # Notify referrer
                try:
                    context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 You earned ${bonus_amount:.2f} for referring {user.first_name}!"
                    )
                except Exception as e:
                    logger.error(f"Could not notify referrer: {e}")

        conn.close()

    # Continue with normal start flow
    if is_user_in_group(update, context):
        show_main_menu(update, context)
        return MAIN_MENU
    else:
        show_join_group_prompt(update, context)
        return JOIN_GROUP_CHECK

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('Operation cancelled.')
    show_main_menu(update, context)
    return MAIN_MENU

def error(update: Update, context: CallbackContext):
    logger.warning(f'Update {update} caused error {context.error}')

def main():
    # Create the Updater and pass it your bot's token.
    updater = Updater(TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Set up conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', handle_referral)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(button_handler),
                MessageHandler(Filters.text & ~Filters.command, start)
            ],
            JOIN_GROUP_CHECK: [
                CallbackQueryHandler(check_join_group, pattern='^joined_group$'),
                MessageHandler(Filters.text & ~Filters.command, start)
            ],
            WITHDRAW: [
                CallbackQueryHandler(process_withdraw, pattern='^withdraw_'),
                CallbackQueryHandler(button_handler),
                MessageHandler(Filters.text & ~Filters.command, start)
            ],
            EARNING_GUIDE: [
                CallbackQueryHandler(button_handler),
                MessageHandler(Filters.text & ~Filters.command, start)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    dp.add_handler(conv_handler)

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()