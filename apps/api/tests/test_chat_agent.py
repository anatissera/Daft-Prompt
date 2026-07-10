from __future__ import annotations

from pydantic import BaseModel

from music_assistant.application.chat_agent import ChatAgent
from music_assistant.application.chat_music import ChatRequest
from music_assistant.application.music_tool_models import ChatAgentDecision, ToolOutput


class FakeStructuredInvoker:
    def __init__(self, decisions: list[ChatAgentDecision]) -> None:
        self.decisions = decisions
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.decisions.pop(0)


class FakeChatModel:
    def __init__(self, decisions: list[ChatAgentDecision]) -> None:
        self.invoker = FakeStructuredInvoker(decisions)

    def with_structured_output(self, schema: type[BaseModel]):
        assert schema is ChatAgentDecision
        return self.invoker


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.enable_web_research = True

    def research_song(self, payload):
        self.calls.append(("research_song", payload))
        return ToolOutput(
            tool="research_song",
            reference_id="ref_researched",
            answer="Research ready.",
            evidence=["source:Fixture"],
        )

    def get_chords(self, payload):
        self.calls.append(("get_chords", payload))
        return ToolOutput(
            tool="get_chords",
            reference_id=payload.reference_id,
            answer="The chorus is probably Ebm7 | Fm7 Bbm7.",
            evidence=["chord_progression:chorus:Fixture:0.8"],
        )

    def get_instrument_summary(self, payload):
        self.calls.append(("get_instrument_summary", payload))
        return ToolOutput(
            tool="get_instrument_summary",
            reference_id=payload.reference_id,
            answer="Bass tab loaded from Songsterr.",
            evidence=["songsterr:part:4:measures=2:notes=3"],
        )

    def request_composition(self, payload):
        self.calls.append(("request_composition", payload))
        return ToolOutput(
            tool="request_composition",
            reference_id=payload.reference_id,
            answer="Composition requested.",
            intent="compose",
        )


def test_chat_agent_researches_when_llm_selects_research_song():
    tools = FakeTools()
    agent = ChatAgent(
        chat_model=FakeChatModel([ChatAgentDecision(tool="research_song", query="Adios by Gustavo Cerati")]),
        tools=tools,
    )

    result = agent.run(ChatRequest(message="Analyze Adios by Gustavo Cerati"))

    assert result.intent == "answer_reference"
    assert result.reference_id == "ref_researched"
    assert result.reply == "Research ready."
    assert tools.calls[0][0] == "research_song"
    assert tools.calls[0][1].query == "Adios by Gustavo Cerati"


def test_chat_agent_uses_explicit_chords_tool_for_profile_chord_question():
    tools = FakeTools()
    agent = ChatAgent(
        chat_model=FakeChatModel([ChatAgentDecision(tool="get_chords", section_name="chorus")]),
        tools=tools,
    )

    result = agent.run(
        ChatRequest(message="What chords are in the chorus?", reference_id="ref_space_cowboy")
    )

    assert result.intent == "answer_reference"
    assert result.reply == "The chorus is probably Ebm7 | Fm7 Bbm7."
    assert tools.calls[0][0] == "get_chords"
    assert tools.calls[0][1].reference_id == "ref_space_cowboy"
    assert tools.calls[0][1].section_name == "chorus"


def test_chat_agent_uses_instrument_summary_for_bass_question():
    tools = FakeTools()
    agent = ChatAgent(
        chat_model=FakeChatModel([ChatAgentDecision(tool="get_instrument_summary", instrument="bass")]),
        tools=tools,
    )

    result = agent.run(ChatRequest(message="What does the bass do?", reference_id="ref_queen"))

    assert result.intent == "answer_reference"
    assert result.reply == "Bass tab loaded from Songsterr."
    assert tools.calls[0][0] == "get_instrument_summary"
    assert tools.calls[0][1].instrument == "bass"


def test_chat_agent_keeps_composition_as_tool_delegation():
    tools = FakeTools()
    agent = ChatAgent(
        chat_model=FakeChatModel([ChatAgentDecision(tool="request_composition", composition_request="make it darker")]),
        tools=tools,
    )

    result = agent.run(ChatRequest(message="Compose something darker", reference_id="ref_queen"))

    assert result.intent == "compose"
    assert result.reply == "Composition requested."
    assert tools.calls[0][0] == "request_composition"
    assert tools.calls[0][1].composition_request == "make it darker"


def test_chat_agent_includes_bounded_session_context_in_its_decision_prompt():
    tools = FakeTools()
    model = FakeChatModel([ChatAgentDecision(tool="get_chords")])
    agent = ChatAgent(chat_model=model, tools=tools)

    agent.run(
        ChatRequest(
            message="What about the chorus?",
            reference_id="ref_space_cowboy",
            conversation_context="User: Compose a funk sketch\nAssistant: I chose a 110 BPM groove.",
        )
    )

    prompt = "\n".join(message["content"] for message in model.invoker.calls[0])
    assert "Recent in-session conversation" in prompt
    assert "I chose a 110 BPM groove" in prompt


def test_chat_agent_hides_song_research_when_offline_mode_is_enabled():
    tools = FakeTools()
    tools.enable_web_research = False
    model = FakeChatModel([ChatAgentDecision(tool="clarify", clarification="Song lookup is unavailable offline.")])
    agent = ChatAgent(chat_model=model, tools=tools)

    agent.run(ChatRequest(message="Look up Get Lucky by Daft Punk"))

    prompt = "\n".join(message["content"] for message in model.invoker.calls[0])
    assert "Do not choose research_song" in prompt
    assert "ENABLE_WEB_RESEARCH=true" in prompt


def test_chat_agent_uses_llm_structured_song_identity_instead_of_genre_keywords():
    tools = FakeTools()
    model = FakeChatModel([
        ChatAgentDecision(
            tool="research_song",
            research_scope="song",
            song_title="Get Lucky",
            song_artist="Daft Punk",
        )
    ])
    agent = ChatAgent(chat_model=model, tools=tools)

    agent.run(ChatRequest(message="Qué acordes usa Get Lucky de Daft Punk"))

    assert tools.calls[0][0] == "research_song"
    assert tools.calls[0][1].query == "Get Lucky by Daft Punk"
    prompt = "\n".join(message["content"] for message in model.invoker.calls[0])
    assert "Daft Punk is an artist, not the punk genre" in prompt


def test_chat_agent_preserves_explicit_featured_artist_credit():
    tools = FakeTools()
    model = FakeChatModel([
        ChatAgentDecision(
            tool="research_song",
            research_scope="song",
            song_title="Uptown Funk",
            song_artist="Mark Ronson",
        )
    ])
    agent = ChatAgent(chat_model=model, tools=tools)

    agent.run(ChatRequest(message="What chords does Uptown Funk by Mark Ronson feat. Bruno Mars use?"))

    assert tools.calls[0][1].query == "Uptown Funk by Mark Ronson featuring Bruno Mars"
