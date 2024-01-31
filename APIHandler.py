import rfc3339
from todoist_api_python.api import TodoistAPI


class APIHandler:

    def __init__(self, api_token):
        self.api = TodoistAPI(api_token)
        self.api_token = api_token

    def get_project_list(self):
        project_list = self.api.get_projects()
        return project_list

    def create_task(self, message, project_id, show_time):
        if message.photo:
            task_content = message.caption or 'Photo Task'
        else:
            task_content = message.text

        forward_from = f"{message.forward_from.first_name or ''} {message.forward_from.last_name or ''}"\
            if message.forward_from else ""
        due_date = self.get_due_date(message) if show_time else ""

        task = self.api.add_task(content=task_content,
                                 description=forward_from,
                                 project_id=project_id,
                                 due_datetime=due_date)
        if message.photo:
            attachment = {
                "resource_type": "file",
                "file_url": message.photo[-1].get_file().file_path,
                "file_type": "image/png",
                "file_name": f"photo_{task.id}.png"
            }
            self.api.add_comment(task_id=task.id, content=message.photo[-1].get_file().file_path, attachment=attachment)

        return task

    def get_due_date(self, message):
        return rfc3339.rfc3339(message.date)


    def delete_task(self, task_id):
        self.api.delete_task(task_id=task_id)

