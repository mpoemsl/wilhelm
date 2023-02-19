import os
import re

import matplotlib.animation as animation
import matplotlib.pyplot as plt
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


def main():
    updater = Updater(token=TOKEN, use_context=True)

    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(CommandHandler("gif", gif))
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
        get_imgs()
        latest_fp = "imgs/" + max(os.listdir("imgs/"))

        with open(latest_fp, "rb") as fh:
            context.bot.send_photo(chat_id=update.effective_message.chat_id, photo=fh)

        LOGGER.info(
            f"Replied successfully to fetch request from chat id {update.effective_message.chat_id}"
        )

    except Exception as e:
        LOGGER.info(
            f"Failed to reply successfully to fetch request from chat id {update.effective_message.chat_id} because of {e}"
        )


def animate(update, context):

    LOGGER.info(f"Gif request from chat id {update.effective_message.chat_id}")

    try:
        get_imgs()
        gif_fp = make_animation()

        with open(gif_fp, "rb") as fh:
            context.bot.send_document(chat_id=update.effective_message.chat_id, document=fh)

        LOGGER.info(
            f"Replied successfully to gif request from chat id {update.effective_message.chat_id}"
        )

    except Exception as e:
        LOGGER.info(
            f"Failed to reply successfully to gif request from chat id {update.effective_message.chat_id} because of {e}"
        )


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
        reply = "<i>SCHEDULED NOTIFICATION:</i>\n" + TELL_TEMPLATE.format(
            total_hours_left, time_left_str
        )
        context.bot.send_message(chat_id=chat_id, text=reply, parse_mode=ParseMode.HTML)

    context.job_queue.run_once(tell_check, REFRESH_INTERVAL, context=chat_id, name=str(chat_id))


def get_time_left():

    browser = login()
    browser.open(GAME_URL)

    match = REGEX.search(str(browser.page))

    if match is None:
        raise KeyError(f"No match found for regex on {GAME_URL}!")

    time_left_str = match.group()[11:-7]

    intify = lambda s: int(s[:-1])

    if time_left_str.count(":") == 2:
        days, hours, mins = map(intify, time_left_str.split(":"))
    elif time_left_str.count(":") == 1:
        days = 0
        hours, mins = map(intify, time_left_str.split(":"))
    else:
        days, hours = 0, 0
        mins = intify(time_left_str)

    total_hours_left = days * 24 + hours

    return total_hours_left, time_left_str


def get_imgs():

    browser = login()
    browser.open(HISTORY_URL)

    os.makedirs("imgs/", exist_ok=True)

    for ix, link in enumerate(browser.links()[:-1]):

        fp = f"imgs/{ix:02}.png"

        if not os.path.exists(fp):
            browser.follow_link(link=link)

            img_links = [link for link in browser.links() if link.attrs.get("target") == "blank"]
            assert len(img_links) == 1, f"More than one image link found on page {browser.url}!"

            browser.download_link(link=img_links[0], file=fp)


def make_animation():

    png_fps = ["imgs/" + fn for fn in os.listdir("imgs/") if fn.endswith("png")]

    ani_fp = max(png_fps).replace("png", "mp4")

    if not os.path.exists(ani_fp):

        fig, ax = plt.subplots()
        ax.set_axis_off()
        fig.add_axes(ax)

        imgs = [plt.imread(fp) for fp in png_fps]
        ims = [[ax.imshow(img, animated=True, aspect="equal")] for img in imgs]

        ani = animation.ArtistAnimation(fig, ims, blit=True, repeat=False)
        writer = animation.FFMpegWriter(fps=1)
        ani.save(ani_fp, writer=writer, dpi=300)


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
