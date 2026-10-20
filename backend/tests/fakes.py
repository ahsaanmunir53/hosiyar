"""A scripted stand-in for a chat model, so the AI paths can be tested without API keys."""

from langchain_core.messages import AIMessage

from app.ai.signals import AISignals


class _Structured:
    def __init__(self, llm, value):
        self.llm = llm
        self.value = value

    async def ainvoke(self, messages):
        self.llm.structured_calls += 1
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


class _Bound:
    def __init__(self, llm, tool_name):
        self.llm = llm
        self.tool_name = tool_name

    async def ainvoke(self, messages):
        self.llm.tool_calls_seen.append((self.tool_name, messages))
        plan = self.llm.tool_plans.get(self.tool_name)
        if plan:
            return plan.pop(0)
        return AIMessage(content="Done.")


class FakeLLM:
    def __init__(
        self,
        signals: AISignals | Exception | None = None,
        tool_plans: dict[str, list[AIMessage]] | None = None,
        broken_tools: bool = False,
        explanation: str = "Yeh message fraud lagta hai kyunke is mein code manga gaya hai.",
        followup: str = "Link na kholein aur bank ko call karein.",
        json_reply: str | None = None,
        broken: bool = False,
        model_name: str = "fake-model",
        error: Exception | None = None,
    ):
        self.json_reply = json_reply
        self.broken = broken or error is not None
        self.error = error or RuntimeError("Error code: 429 - rate limit reached")
        self.plain_calls = 0
        self.model_name = model_name
        self.signals = signals or AISignals(claimed_identity="none", summary="A message.")
        self.tool_plans = {k: list(v) for k, v in (tool_plans or {}).items()}
        self.broken_tools = broken_tools
        self.bound_tool_names: list[str] = []
        self.structured_calls = 0
        self.explanation = explanation
        self.followup = followup
        self.tool_calls_seen: list = []

    def with_structured_output(self, schema):
        return _Structured(self, self.error if self.broken else self.signals)

    def bind_tools(self, tools):
        if self.broken or self.broken_tools:
            raise self.error
        self.bound_tool_names += [t.name for t in tools]
        return _Bound(self, tools[0].name)

    async def ainvoke(self, messages):
        self.plain_calls += 1
        if self.broken:
            raise self.error
        system = str(messages[0].content)
        if "rule book of a scam checker" in system:
            return AIMessage(content=self.json_reply or "{}")
        if "JSON schema" in system:
            return AIMessage(content=self.json_reply or "Sorry, I cannot help with that.")
        if "follow-up question" in system:
            return AIMessage(content=self.followup)
        return AIMessage(content=self.explanation)
