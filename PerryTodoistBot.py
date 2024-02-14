import configparser

import enum
from datetime import datetime

import Utility

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, MessageHandler, CommandHandler, CallbackQueryHandler, Filters

from APIHandler import APIHandler


class Action(enum.Enum):
    INSERT_TOKEN = 'INSERT_TOKEN'
    UPDATE_PROJECT = 'UPDATE_PROJECT'


DEFAULT_PREFERENCE = False
FILE_NAME = "data"


class TodoistBot:

    def __init__(self):
        # Read Configs from file
        self.config = configparser.ConfigParser()
        self.config.read("config.ini")

        self.data = Utility.read_data(FILE_NAME)
        self.all_apis = None
        self.get_apis_from_data()

        # set Telegram bot token
        bot_token = self.config['telegram']['bot_token']

        # initiate a Telegram updater instance
        self.updater = Updater(bot_token)

    def button(self, update, context):
        query = update.callback_query
        user_id = str(update.effective_user.id)
        project_id = query.data
        if self.get_user_next_action(user_id) == Action.UPDATE_PROJECT.name:
            context.bot.edit_message_text(text=f"Project updated.",
                                          chat_id=query.message.chat_id,
                                          message_id=query.message.message_id)
            self.set_user_project_id(user_id, project_id)
            self.set_user_next_action(user_id, "")

    def start_command(self, update, context):
        user_id = str(update.effective_user.id)

        # Check if the user has already provided an API token
        if user_id in self.data.keys() and not self.get_user_next_action(user_id) == Action.INSERT_TOKEN.name:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Welcome back to the Todoist Bot! Use /help to see all commands.")
        else:
            if not user_id in self.data.keys():
                self.data[user_id] = {}  # Initialize an empty dictionary for the user
                Utility.write_data(FILE_NAME, self.data)
            # If not, ask the user to send their Todoist API token
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Welcome to the Todoist Bot! To get started, please send me your Todoist API token.")

    def set_project_command(self, update, context):
        chat_id = update.effective_chat.id
        user_id = str(update.effective_user.id)

        if not user_id in self.data.keys() or \
                self.get_user_next_action(user_id) == Action.INSERT_TOKEN.name:
            self.start_command(update, context)
            return
        user_api = self.all_apis[user_id]
        project_list = user_api.get_project_list()
        keyboard = []
        for project in project_list:
            keyboard.append(
                [InlineKeyboardButton(project.name, callback_data=project.id)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        self.set_user_next_action(user_id, Action.UPDATE_PROJECT.name)

        context.bot.send_message(chat_id=chat_id, text="Choose a project to forward to:", reply_markup=reply_markup)

    def toggle_time_command(self, update, context):
        chat_id = update.effective_chat.id
        user_id = str(update.effective_user.id)
        if not user_id in self.data.keys():  # If skipped /start
            self.start_command(update, context)
        toggled_preference = not self.get_user_preference(user_id)
        self.set_user_preference(user_id, toggled_preference)
        time = "according to the time of the sent message" if toggled_preference else "off"
        context.bot.send_message(chat_id=chat_id, text="Updated successfully. due time is now " + time)

    def change_token_command(self, update, context):
        user_id = str(update.effective_user.id)
        if not user_id in self.data.keys():  # If skipped /start
            self.start_command(update, context)
        self.set_user_next_action(user_id, Action.INSERT_TOKEN.name)
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="To change the token, please send me a valid Todoist API token.")

    def undo_command(self, update, context):
        user_id = str(update.effective_user.id)
        if not user_id in self.data.keys():  # If skipped /start
            self.start_command(update, context)

        task_id = self.get_user_last_task(user_id)
        if task_id:
            # Remove the task from Todoist
            user_api = self.all_apis[user_id]
            user_api.delete_task(task_id)
            self.set_user_last_task(user_id, "")
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Undo successful. Task canceled and removed from Todoist.")
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="No task to undo.")

    def help_command(self, update, context):
        chat_id = update.effective_chat.id
        user_id = str(update.effective_user.id)

        if not user_id in self.data.keys():  # If skipped /start
            self.start_command(update, context)

        show_time = self.get_user_preference(user_id)
        time = "On → Off" if show_time else "On ← Off"
        help_text = "Available commands:\n" \
                    "/start - Start the bot \n" \
                    "/set_project - Choose project to forward to\n" \
                    "/toggle_time - " + time + "\n" \
                    "/undo - Cancel last task \n" \
                    "/change_token - Change API token \n" \
                    "/help - List of commands \n\n" \
                    "NEW! reply on last task with a new due time.\n" \
                    "Use time formats and English phrases like \"19:32 next Wednesday\". "
        context.bot.send_message(chat_id=chat_id, text=help_text)

    def general_handler(self, update, context):
        chat_id = update.effective_chat.id
        user_id = str(update.effective_user.id)

        if not user_id in self.data.keys():  # If skipped /start
            self.start_command(update, context)
        if self.get_user_next_action(user_id) == Action.INSERT_TOKEN.name:
            if self.handle_api_token(update, context):
                self.set_user_next_action(user_id, "")
                self.set_project_command(update, context)
        elif update.message.reply_to_message:
            if not self.update_due_time_for_last_task(update, context):
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text="Failed to update due time.")

        else:
            project_id = self.get_user_project_id(user_id)
            is_original_time = self.get_user_preference(user_id)
            user_api = self.all_apis[user_id]
            new_task = user_api.create_task(update.message, project_id, is_original_time)
            if new_task:
                context.bot.send_message(chat_id=chat_id, text="Task added.")
                self.set_user_last_task(user_id, new_task.id)
            else:
                context.bot.send_message(chat_id=chat_id, text="Problem occurred, task was not added.")

    def handle_api_token(self, update, context):
        user_id = str(str(update.effective_user.id))
        api_token = update.message.text.strip()

        # Perform validation of the Todoist API token (you may want to implement this function)
        if Utility.is_valid_api_token(api_token):
            self.set_user_todoist_api(user_id, api_token)
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Great! Your Todoist API token has been successfully set.")
            return True
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Invalid Todoist API token. Please provide a valid token.")
            return False

    def set_user_project_id(self, user_id, project_id):
        # Ensure the user_id key exists in data
        if user_id not in self.data.keys():
            self.data[user_id] = {}

        # Store project_id for the user
        self.data[user_id].update({'project': project_id})
        Utility.write_data(FILE_NAME, self.data)

    def get_user_project_id(self, user_id):
        # Retrieve project_id for the user
        return self.data[user_id].get('project')

    def set_user_preference(self, user_id, is_original_time):
        # Ensure the user_id key exists in data
        if user_id not in self.data.keys():
            self.data[user_id] = {}

        # Store project_id for the user
        self.data[user_id].update({'preference': is_original_time})
        Utility.write_data(FILE_NAME, self.data)

    def get_user_preference(self, user_id):
        # Retrieve preference of the user
        if 'preference' in self.data[user_id].keys():
            return self.data[user_id].get('preference')
        else:
            return DEFAULT_PREFERENCE

    def set_user_next_action(self, user_id, action):
        # Ensure the user_id key exists in data
        if user_id not in self.data.keys():
            self.data[user_id] = {}

        # Store project_id for the user
        self.data[user_id].update({'next_action': action})
        Utility.write_data(FILE_NAME, self.data)

    def get_user_next_action(self, user_id):
        # Retrieve preference of the user
        if 'next_action' in self.data[user_id].keys():
            return self.data[user_id].get('next_action')
        else:
            return Action.INSERT_TOKEN.name

    def set_user_last_task(self, user_id, task_id):
        # Ensure the user_id key exists in data
        if user_id not in self.data.keys():
            self.data[user_id] = {}

        # Store project_id for the user
        self.data[user_id].update({'task_id': task_id})
        Utility.write_data(FILE_NAME, self.data)

    def get_user_last_task(self, user_id):
        # Retrieve preference of the user
        if 'task_id' in self.data[user_id].keys():
            return self.data[user_id].get('task_id')
        else:
            return None

    def set_user_todoist_api(self, user_id, api_token):
        # Ensure the user_id key exists in data
        if user_id not in self.data.keys():
            self.data[user_id] = {}

        # Save the valid API token in user_data
        self.data[user_id] = {'token': api_token}
        Utility.write_data(FILE_NAME, self.data)
        # initiate a Todoist API handler
        self.all_apis[user_id] = APIHandler(api_token)

    def main(self):
        updater = self.updater
        dp = updater.dispatcher

        # Add command handlers
        dp.add_handler(CommandHandler('start', self.start_command))
        dp.add_handler(CommandHandler('set_project', self.set_project_command))
        dp.add_handler(CommandHandler('toggle_time', self.toggle_time_command))
        dp.add_handler(CommandHandler('change_token', self.change_token_command))
        dp.add_handler(CommandHandler('undo', self.undo_command))
        dp.add_handler(CommandHandler('help', self.help_command))

        # Add callback handlers for buttons
        updater.dispatcher.add_handler(CallbackQueryHandler(self.button))

        # general message handler
        updater.dispatcher.add_handler(MessageHandler(Filters.all, self.general_handler))

        updater.start_polling()
        updater.idle()

    def get_apis_from_data(self):
        self.all_apis = {}
        for user_id in self.data.keys():
            self.all_apis[user_id] = APIHandler(self.data[user_id].get('token'))

    def update_due_time_for_last_task(self, update, context):
        user_id = str(update.effective_user.id)
        if not user_id in self.data.keys():  # If skipped /start
            self.start_command(update, context)

        task_id = self.get_user_last_task(user_id)
        if task_id:
            # Update due time of the task from Todoist
            user_api = self.all_apis[user_id]
            if not user_api.update_task_due_time(task_id, update.message.text):
                return False
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Due time was updated successfully.")
            return True
        else:
            return False


# Instantiate and run the bot
if __name__ == "__main__":
    todoist_bot = TodoistBot()
    todoist_bot.main()
