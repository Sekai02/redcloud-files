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