from deepwrap import Client


class DeepSeekWebProvider:
    def __init__(self, model="default", thinking=True, search=False):
        self.client = Client(agent_mode=False)
        self.model = model
        self.thinking = thinking
        self.search = search

    def create_session(self):
        return self.client.chats.create_session(model=self.model)

    def chat_stream(self, prompt, session=None):
        chat = session or self.create_session()
        for chunk in chat.respond(
            prompt,
            stream=True,
            thinking=self.thinking,
            search=False,
            agent=False,
        ):
            yield chunk

    def chat_once(self, prompt, session=None):
        chat = session or self.create_session()
        return chat.respond(
            prompt,
            stream=False,
            thinking=self.thinking,
            search=self.search,
        )