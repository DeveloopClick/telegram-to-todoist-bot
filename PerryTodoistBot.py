import configparser
import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, MessageHandler, CommandHandler, CallbackQueryHandler, Filters

from APIHandler import APIHandler

DEFAULT_PREFERENCE = False


class TodoistBot:

    def __init__(self):
        # Read Configs from file
        self.config = configparser.ConfigParser()
        self.config.read("config.ini")

        # set Telegram bot token
        bot_token = self.config['bot_token']

        # initiate a Telegram updater instance
        self.updater = Updater(bot_token)

    def button(self, update, context):
        query = update.callback_query
        user_id = update.effective_user.id
        project_id = query.data
        if self.get_user_next_action(context, user_id) == "update_project":
            context.bot.edit_message_text(text=f"Project updated.",
                                          chat_id=query.message.chat_id,
                                          message_id=query.message.message_id)
            self.set_user_project_id(context, user_id, project_id)
            self.set_user_next_action(context, user_id, "")


    def start_command(self, update, context):
        user_id = update.effective_user.id
        if not context.user_data.get(user_id, {}):
            context.user_data[user_id] = {}  # Initialize an empty dictionary for the user
            self.set_user_preference(context, user_id, DEFAULT_PREFERENCE)
            self.set_user_next_action(context, user_id, "insert_token")


        # Check if the user has already provided an API token
        if 'api_token' in context.user_data[user_id]:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Welcome back to the Todoist Bot! Use /help to see all commands.")
        else:
            # If not, ask the user to send their Todoist API token
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Welcome to the Todoist Bot! To get started, please send me your Todoist API token.")
            self.set_user_next_action(context, user_id, "insert_token")

    def set_project_command(self, update, context):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not context.user_data.get(user_id, {}) or \
                self.get_user_next_action(context, user_id) == "insert_token":
            self.start_command(update, context)
            return
        user_api = context.user_data[user_id].get('api')
        project_list = user_api.get_project_list()
        keyboard = []
        for project in project_list:
            keyboard.append(
                [InlineKeyboardButton(project.name, callback_data=project.id)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        self.set_user_next_action(context, user_id, "update_project")

        context.bot.send_message(chat_id=chat_id, text="Choose a project to forward to:", reply_markup=reply_markup)

    def toggle_time_command(self, update, context):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        if not context.user_data.get(user_id, {}):  # If skipped /start
            self.start_command(update, context)
        toggled_preference = not self.get_user_preference(context, user_id)
        self.set_user_preference(context, user_id, toggled_preference)
        time = "according to the original message" if toggled_preference else "according to when it was forwarded"
        context.bot.send_message(chat_id=chat_id, text="Updated successfully. time is now " + time)

    def change_token_command(self, update, context):
        user_id = update.effective_user.id
        if not context.user_data.get(user_id, {}):  # If skipped /start
            self.start_command(update, context)
        context.user_data[user_id].pop('api_token', None)
        self.start_command(update, context)

    def undo_command(self, update, context):
        user_id = update.effective_user.id
        if not context.user_data.get(user_id, {}):  # If skipped /start
            self.start_command(update, context)
        last_action = self.get_user_next_action(context, user_id)

        if last_action:
            # Undo the last action based on the stored action type
            if last_action == "insert_token":
                # If the last action was inserting the token, remove the token from user_data
                context.user_data[user_id].pop('api_token', None)
                self.set_user_next_action(context, user_id, "")
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text="Undo successful. Token insertion undone.")
            elif last_action == "update_project":
                # If the last action was updating the project, reset the next action
                self.set_user_next_action(context, user_id, "")
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text="Undo successful. Project update undone.")
        else:
            task_id = context.user_data[user_id].get('last_task_id')
            if task_id:
                # Remove the task from Todoist
                user_api = context.user_data[user_id].get('api')
                user_api.delete_task(task_id)
                context.user_data[user_id]['last_task_id'] = ""
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text="Undo successful. Task canceled and removed from Todoist.")
            else:
                context.bot.send_message(chat_id=update.effective_chat.id,
                                         text="No task to undo.")

    def help_command(self, update, context):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not context.user_data.get(user_id, {}):  # If skipped /start
            self.start_command(update, context)

        is_original_time = self.get_user_preference(context, user_id)
        time = "Original → forwarded" if is_original_time else "Original ← forwarded"
        help_text = "Available commands:\n" \
                    "/start - start the bot \n" \
                    "/set_project - Choose a project to forward the tasks to\n" \
                    "/toggle_time - " + time + "\n" \
                    "/undo - undo last change \n" \
                    "/change_token - self explanatory \n" \
                    "/help - List of commands"
        context.bot.send_message(chat_id=chat_id, text=help_text)

    def general_handler(self, update, context):
        print(update)
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if not context.user_data.get(user_id, {}):  # If skipped /start
            self.start_command(update, context)

        self.dev_get_and_set_users_data(chat_id, context, update)

        if self.get_user_next_action(context, user_id) == "insert_token":
            if self.handle_api_token(update, context):
                self.set_user_next_action(context, user_id, "")
                self.set_project_command(update,context)
        else:
            project_id = self.get_user_project_id(context, user_id)
            is_original_time = self.get_user_preference(context, user_id)
            user_api = context.user_data[user_id].get('api')
            new_task = user_api.create_task(update.message, project_id, is_original_time)
            if new_task:
                context.bot.send_message(chat_id=chat_id, text="Task added.")
                context.user_data[user_id]['last_task_id'] = new_task.id
            else:
                context.bot.send_message(chat_id=chat_id, text="Problem occurred, task was not added.")

    def dev_get_and_set_users_data(self, chat_id, context, update):
        if update.message.text and update.message.text.startswith('!get_data'):
            # Exclude the 'api' field when sending user data
            user_data_without_api = {
                user_id: {key: value for key, value in user_data.items() if key != 'api'}
                for user_id, user_data in context.user_data.items()
            }
            data_str = json.dumps(user_data_without_api, indent=2)
            context.bot.send_message(chat_id=chat_id, text=data_str)
        if update.message.text and update.message.text.startswith('!set_data'):
            try:
                json_data = update.message.text.strip('!set_data ')
                data_str = json.loads(json_data)
                print(data_str)
                # Iterate over each user_id and update their dictionary
                for user_id, new_data in data_str.items():
                    user_id = int(user_id) # check
                    if user_id in context.user_data:
                        # Update the user's dictionary
                        context.user_data[user_id] = new_data
                        context.user_data[user_id]['api'] = APIHandler(context.user_data[user_id].get('api_token'))
                        print(1)
                print(context.user_data)
                context.bot.send_message(chat_id=update.effective_chat.id, text="User data set successfully.")
            except json.JSONDecodeError as e:
                context.bot.send_message(chat_id=update.effective_chat.id, text=f"Error setting user data: {str(e)}")

    def handle_api_token(self, update, context):
        user_id = update.effective_user.id
        api_token = update.message.text.strip()

        # Perform validation of the Todoist API token (you may want to implement this function)
        if self.is_valid_api_token(api_token):
            # Save the valid API token in user_data
            context.user_data[user_id]['api_token'] = api_token
            # initiate a Todoist API handler
            context.user_data[user_id]['api'] = APIHandler(api_token)
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Great! Your Todoist API token has been successfully set.")
            return True
        else:
            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text="Invalid Todoist API token. Please provide a valid token.")
            return False

    def is_valid_api_token(self, token):
        try:
            # Execute the provided code block
            from todoist_api_python.api import TodoistAPI
            TodoistAPI(token).get_projects()
            return True  # No exception was thrown
        except Exception as e:
            return False


    def set_user_project_id(self, context, user_id, project_id):
        # Ensure the user_id key exists in context.user_data
        if user_id not in context.user_data:
            context.user_data[user_id] = {}

        # Store project_id for the user
        context.user_data[user_id]['project_id'] = project_id

    def get_user_project_id(self, context, user_id):
        # Retrieve project_id for the user
        return context.user_data[user_id].get('project_id')

    def set_user_preference(self, context, user_id, is_original_time):
        # Ensure the user_id key exists in context.user_data
        if user_id not in context.user_data:
            context.user_data[user_id] = {}

        # Store project_id for the user
        context.user_data[user_id]['preference'] = is_original_time

    def get_user_preference(self, context, user_id):
        # Retrieve preference of the user
        return context.user_data[user_id].get('preference')

    def set_user_next_action(self, context, user_id, action):
        # Ensure the user_id key exists in context.user_data
        if user_id not in context.user_data:
            context.user_data[user_id] = {}

        # Store project_id for the user
        context.user_data[user_id]['next_action'] = action

    def get_user_next_action(self, context, user_id):
        # Retrieve preference of the user
        return context.user_data[user_id].get('next_action')

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


# Instantiate and run the bot
if __name__ == "__main__":
    todoist_bot = TodoistBot()
    todoist_bot.main()
