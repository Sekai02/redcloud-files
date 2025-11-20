class CommandRequest:
    def __init__(self, command_name: str, args: list[str]):
        self.command_name = command_name
        self.args = args

class CommandResponse:
    def __init__(self, success: bool, message: str, action: callable):
        if not callable(action):
            raise TypeError("action must be callable")
        self.success = success
        self.message = message
        self.action = action 

    def execute_action(self):
        return self.action()
    
class AddFileRequest:
    def __init__(self, file_list: list[str], tag_list: list[str], files_paths: list[str]):
        self.file_list = file_list
        self.tag_list = tag_list
        self.files_paths = files_paths

class DeleteFilesRequest:
    def __init__(self, tag_query: list[str]):
        self.tag_query = tag_query

class ListFilesRequest:
    def __init__(self, tag_query: list[str]):
        self.tag_query = tag_query

class AddTagsRequest:
    def __init__(self, tag_query: list[str], tag_list: list[str]):
        self.tag_query = tag_query
        self.tag_list = tag_list

class DeleteTagsRequest:
    def __init__(self, tag_query: list[str], tag_list: list[str]):
        self.tag_query = tag_query
        self.tag_list = tag_list