#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Standard modules """
import logging
import subprocess
import signal
import json
import re
from io import BytesIO

""" Local modules """
import config

""" 3th party modules """
from telegram import *
from telegram.ext import * 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=config.LOG_LEVEL)
log = logging.getLogger(__name__)

class PleaseWaitMessage:

    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
        self.msg = None

    def send(self):
        self.msg = self.bot.send_message(chat_id=self.chat_id, text='<i>... please wait ...</i>', parse_mode=ParseMode.HTML)

    def revoke(self):
        self.bot.delete_message(chat_id=self.chat_id, message_id=self.msg.message_id)

class AudioFile:

    def __init__(self, url):
        self.url = url
        self.info = None
        self.binary_data = None

    def check_url(self):
        try:
            resp = subprocess.check_output(['youtube-dl', \
                '-f bestaudio', \
                '-sq', # simulate + quiet \ 
                self.url])

            return True
        except subprocess.CalledProcessError as e:
            log.error(e)
            return False

    def get_info(self):
        resp = subprocess.check_output(['youtube-dl', \
            '--dump-single-json', \
            '-f bestaudio', \
            self.url])

        self.info = json.loads(resp)
    
    def download(self):
        if self.binary_data is not None:
            print('Skipping download because binary_data is already present.')
            return

        resp = subprocess.check_output(['youtube-dl', \
            '-f mp3', \
            '-q', # quiet \ 
            '-o', '-', # stdout \
            self.url])

        self.binary_data = resp

    def cut_audio(self, start=0, end=0):
        p = subprocess.Popen(['ffmpeg', \
            '-i', 'pipe:0', \
            '-ss', start, # quiet \ 
            '-to', end, \
            '-f', 'mp3', \
            '-'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        print('Binary data on stdin of ffmpeg: %s' % self.binary_data[:50])
        stdout = p.communicate(input=BytesIO(self.binary_data).read())[0]
        self.binary_data = stdout
        print('Binary data on stdout of ffmpeg: %s' % self.binary_data[:50])

    def html_preview(self):
        return '<strong>%s</strong>\n<i>uploaded by %s</> (%s)' % (self.info['title'], self.info['uploader'], self.info['duration'])

def handle_cancel(update, context):
    return ConversationHandler.END

def handle_start(bot, update):
    """ Handle /start command """
    update.message.reply_text(
        text='<strong>How to start?</strong>\nshare a link !', 
        parse_mode=ParseMode.HTML)

def handle_incoming_url(bot, update, chat_data):
    """ Handle incoming url """
    url = update.message.text
    chat_id = update.message.chat.id
    log.info('Incoming url "%s"' % url)

    # display wait message
    please_wait = PleaseWaitMessage(bot, chat_id)
    please_wait.send()

    audio = AudioFile(url)

    if not audio.check_url():
        update.message.reply_text(
                text='<strong>Error:</strong> <i>%s</i> is not a valid url.' % url, 
                    parse_mode=ParseMode.HTML)
        please_wait.revoke()
        return ConversationHandler.END
    

    audio.get_info()
    chat_data.update({'audio': audio})

    please_wait.revoke()
    # reply keyboard
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('Download', callback_data='download')],
            [InlineKeyboardButton('Settings', callback_data='settings')],
            [InlineKeyboardButton('Cancle', callback_data='cancle')]
        ])

    update.message.reply_text(
        text=audio.html_preview(), 
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard)

    return MENU

def handle_settings(bot, update, chat_data):
    """ Handle menu """
    query = update.callback_query
    chat_id = query.message.chat.id

    cmd = query.data

    if cmd == 'back':
        keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('Download', callback_data='download')],
            [InlineKeyboardButton('Settings', callback_data='settings')],
            [InlineKeyboardButton('Cancle', callback_data='cancle')]
        ])

        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=query.message.message_id,
            reply_markup=keyboard)

        return MENU

    if cmd == 'cut':
        bot.send_message(text='Enter in format: hh:mm:ss-hh:mm:ss', chat_id=chat_id)

        return SETTINGS_CUT

    else:
        bot.send_message(text='<strong>Error: </strong> unknown command "%s"' % cmd, 
                chat_id=chat_id, parse_mode=ParseMode.HTML)

        return ConversationHandler.END

def handle_settings_cut(bot, update, chat_data):
    cut = update.message.text
    chat_id = update.message.chat.id

    if re.match('[0-5][0-9]:[0-5][0-9]:[0-5][0-9]-[0-5][0-9]:[0-5][0-9]:[0-5][0-9]', cut) is None:
        bot.send_message(text='%s does not match the required format' % cut, chat_id=chat_id)
        return SETTINGS_CUT

    cut = cut.split('-')

    audio = chat_data['audio']
    audio.download()
    audio.cut_audio(start=cut[0], end=cut[1])

    keyboard = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton('Download', callback_data='download')],
        [InlineKeyboardButton('Settings', callback_data='settings')],
        [InlineKeyboardButton('Cancle', callback_data='cancle')]
    ])

    update.message.reply_text(text='again?', reply_markup=keyboard)

    return MENU

def handle_menu(bot, update, chat_data):
    """ Handle menu """
    query = update.callback_query
    chat_id = query.message.chat.id

    cmd = query.data

    # remove download btn after click
    bot.edit_message_reply_markup(chat_id, query.message.message_id)
    
    if cmd == 'cancle':
        return ConversationHandler.END

    elif cmd == 'download':
        # display wait message
        please_wait = PleaseWaitMessage(bot, chat_id)
        please_wait.send()

        audio = chat_data['audio']
        audio.download()

        bot.send_audio(chat_id=chat_id, 
                audio=BytesIO(audio.binary_data), 
                title=audio.info['title'],
                performer=audio.info['uploader'],
                thumb=audio.info['thumbnail'],
                timeout=1000)

        please_wait.revoke()

        return ConversationHandler.END

    elif cmd == 'settings':
        
        keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton('Cut', callback_data='cut')],
            [InlineKeyboardButton('Go back', callback_data='back')],
        ])

        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=query.message.message_id,
            reply_markup=keyboard)

        return SETTINGS
    
    else:
        bot.send_message(text='<strong>Error: </strong> unknown command "%s"' % cmd, 
                chat_id=chat_id, parse_mode=ParseMode.HTML)

        return ConversationHandler.END

def handle_error(bot, update, error):
    log.warning('Update "%s" caused error "%s"', update, error)


MENU, SETTINGS, SETTINGS_CUT = range(3)

def initialize():
    log.info('Initialize Telegram Bot...')

    updater = Updater(config.BOT_TOKEN)
    updater.dispatcher.add_error_handler(handle_error)

    updater.dispatcher.add_handler(CommandHandler('start', handle_start))

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(Filters.all, handle_incoming_url, pass_chat_data=True)],

        states={
            MENU: [CallbackQueryHandler(handle_menu, pass_chat_data=True)],
            SETTINGS: [CallbackQueryHandler(handle_settings, pass_chat_data=True)],
            SETTINGS_CUT: [MessageHandler(Filters.all, handle_settings_cut, pass_chat_data=True)]
        },

        fallbacks=[CommandHandler('cancel', handle_cancel)]
    )

    updater.dispatcher.add_handler(conv_handler)


    # Start the Bot
    log.info('Start polling...')
    updater.start_polling()

    # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    log.info('Initialize Telegram Bot...DONE. switching to idle mode.')
    updater.idle()

def on_exit(sig, func=None):
    print("exit handler triggered")
    sys.exit(1)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, on_exit)
    initialize()
