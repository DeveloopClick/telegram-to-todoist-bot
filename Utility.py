import json

def read_data(filename):
    try:
        with open(f"./{filename}.json", 'r') as file:
            data = json.load(file)
        return data
    except FileNotFoundError:
        return {}

def write_data(filename, data):
    with open(f"{filename}.json", 'w') as file:
        json.dump(data, file, indent=2)

def is_valid_api_token(token):
    try:
        # Execute the provided code block
        from todoist_api_python.api import TodoistAPI
        TodoistAPI(token).get_projects()
        return True  # No exception was thrown
    except Exception as e:
        return False
