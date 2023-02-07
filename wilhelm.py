import os
import re
import time

import mechanicalsoup as mch
import structlog
from telegram import ParseMode
from telegram.ext import CommandHandler, Updater

LOGGER = structlog.get_logger()

GAME_ID = os.getenv("PD_GID")
USERNAME = os.getenv("PD_USERNAME")
PASSWORD = os.getenv("PD_PASSWORD")
ADMIN_ID = os.getenv("TG_ID")
TOKEN = os.getenv("TG_TOKEN")

BASE_URL = "https://www.playdiplomacy.com/"
GAME_URL = f"https://www.playdiplomacy.com/game_play.php?game_id={GAME_ID}"
HISTORY_URL = f"https://www.playdiplomacy.com/game_history.php?game_id={GAME_ID}"

REFRESH_INTERVAL = 3600  # 3600 seconds is 60 minutes
POWERS = [2**i for i in range(8, 0, -1)]
REGEX = re.compile("Time Left:[^<]*</span>")

GREETING = """
Welcome! My name is Wilhelm Tell. Use the command /tell to ask for the time until the next game deadline, or enable notifications whenever the number of hours left is less than a power of 2 with /enable.
"""

TELL_TEMPLATE = "There are about <b>{} hours</b> left until the next game deadline. To be more precise, the exact time left is {}."

ENABLE_TEMPLATE = """
Notifications enabled. I will notify you once the number of hours left is less than one of the following:

{}

I only refresh once an hour, so keep in mind there might be a delay. For now, there are about <b>{} hours</b> left until the next game deadline.
"""

REMIND_TEMPLATE = """
<i>SCHEDULED NOTIFICATION:</i> 
There are less than <b>{} hours</b> left until the next game deadline.
"""


def main():

    updater = Updater(token=TOKEN, use_context=True)

    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(CommandHandler("tell", tell))
    updater.dispatcher.add_handler(CommandHandler("fetch", fetch))
    updater.dispatcher.add_handler(CommandHandler("enable", enable))
    updater.dispatcher.add_handler(CommandHandler("disable", disable))
    updater.dispatcher.add_handler(CommandHandler("megaphone", megaphone))

    LOGGER.info("Starting polling ...")
    updater.start_polling(poll_interval=1.0, timeout=30.0)
    updater.idle()


def megaphone(update, context):

    if update.effective_message.chat_id == int(ADMIN_ID):
        LOGGER.info(f"Received megaphone request from chat id {update.effective_message.chat_id}")
        target_id = context.args[0]
        msg = " ".join(context.args[1:])
        context.bot.send_message(chat_id=target_id, text=msg, parse_mode=ParseMode.HTML)


def start(update, context):

    LOGGER.info(f"Start request from chat id {update.effective_message.chat_id}")

    context.bot.send_message(
        chat_id=update.effective_message.chat_id, text=GREETING, parse_mode=ParseMode.HTML
    )


def tell(update, context):

    LOGGER.info(f"Tell request from chat id {update.effective_message.chat_id}")

    if " ".join(context.args).strip("? ").lower() == "me why":
        context.bot.send_message(
            chat_id=update.effective_message.chat_id,
            text="ain't nothin but a backstab",
            parse_mode=ParseMode.HTML,
        )

    try:
        total_hours_left, time_left_str = get_time_left()
        reply = TELL_TEMPLATE.format(total_hours_left, time_left_str)
        LOGGER.info(
            f"Replied successfully to tell request from chat id {update.effective_message.chat_id}"
        )
    except Exception as e:
        LOGGER.info(
            f"Failed to reply successfully to tell request from chat id {update.effective_message.chat_id} because of {e}"
        )
        reply = "I sadly couldn't determine the current time left."

    context.bot.send_message(
        chat_id=update.effective_message.chat_id, text=reply, parse_mode=ParseMode.HTML
    )


def fetch(update, context):

    LOGGER.info(f"Fetch request from chat id {update.effective_message.chat_id}")

    try:
        get_img()
    except Exception as e:
        LOGGER.info(
            f"Failed to reply successfully to fetch request from chat id {update.effective_message.chat_id} because of {e}"
        )
        reply = "I sadly couldn't determine the current time left."

    with open("temp.png", "rb") as fh:
        context.bot.send_photo(chat_id=update.effective_message.chat_id, photo=fh)


def enable(update, context):

    LOGGER.info(f"Enable request from chat id {update.effective_message.chat_id}")

    try:
        total_hours_left, time_left_str = get_time_left()

        reply = ENABLE_TEMPLATE.format(
            str([power for power in POWERS if power < total_hours_left]), total_hours_left
        )

        context.job_queue.run_once(
            tell_check,
            REFRESH_INTERVAL,
            context=update.effective_message.chat_id,
            name=str(update.effective_message.chat_id),
        )
        LOGGER.info(
            f"Replied successfully to enable request from chat id {update.effective_message.chat_id}"
        )
    except Exception as e:
        LOGGER.info(
            f"Failed to reply successfully to enable request from chat id {update.effective_message.chat_id} because of {e}"
        )
        reply = "I sadly couldn't determine the current time left."

    context.bot.send_message(
        chat_id=update.effective_message.chat_id, text=reply, parse_mode=ParseMode.HTML
    )


def disable(update, context):

    LOGGER.info(f"Disable request from chat id {update.effective_message.chat_id}")

    for job in context.job_queue.get_jobs_by_name(str(update.effective_message.chat_id)):
        job.schedule_removal()

    context.bot.send_message(
        chat_id=update.effective_message.chat_id,
        text="Disabled all currently scheduled notifications.",
    )


def tell_check(context):

    total_hours_left, time_left_str = get_time_left()
    chat_id = context.job.context

    LOGGER.info(f"Tell check for chat id {chat_id}")

    if total_hours_left in POWERS:
        reply = REMIND_TEMPLATE.format(total_hours_left)
        context.bot.send_message(chat_id=chat_id, text=reply, parse_mode=ParseMode.HTML)

    if total_hours_left > 1:
        context.job_queue.run_once(tell_check, REFRESH_INTERVAL, context=chat_id, name=str(chat_id))
    else:
        context.bot.send_message(
            chat_id=chat_id, text="There will be no more notifications from me for now."
        )


def get_time_left():

    browser = login()
    browser.open(GAME_URL)

    match = REGEX.search(str(browser.page))

    if match is None:
        raise KeyError(f"No match found for regex on {GAME_URL}!")

    time_left_str = match.group()[11:-7]

    days_str, hours_str, mins_str = time_left_str.split(":")
    days, hours, mins = int(days_str[:-1]), int(hours_str[:-1]), int(mins_str[:-1])

    total_hours_left = days * 24 + hours

    return total_hours_left, time_left_str


def get_img():

    browser = login()
    browser.open(HISTORY_URL)

    current_phase_link = browser.links()[-2]
    browser.follow_link(link=current_phase_link)

    img_link = browser.links()[2]
    browser.download_link(link=img_link, file="temp.png")


def login():

    browser = mch.StatefulBrowser()

    browser.open(BASE_URL)
    browser.select_form('form[action="login.php"]')

    browser["username"] = USERNAME
    browser["password"] = PASSWORD

    browser.submit_selected()

    return browser


if __name__ == "__main__":
    main()
