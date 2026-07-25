"""In-memory character catalog for the marketplace UI."""

from pydantic import BaseModel, ConfigDict, Field

from agents.barbie import BARBIE_PROMPT


class Character(BaseModel):
    """Character definition."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    description: str
    avatar: str
    prompt: str
    voice_id: str = Field(min_length=1)


_CHARACTERS = {
    "barbie": Character(
        id="barbie",
        name="Barbie Mentor",
        description="A cheerful mentor and companion who encourages the user and remembers their journey.",
        avatar="https://placehold.co/240x240/f8d4e4/7a2550?text=Barbie",
        prompt=BARBIE_PROMPT + " Always act like a long-term mentor who remembers the user.",
        voice_id="EXAVITQu4vr4xnSDxMaL",
    ),
    "mentor-morpheus": Character(
        id="mentor-morpheus",
        name="Mentor Morpheus",
        description="A calm fictional coach for learning, reflection, and long-term discipline.",
        avatar="https://placehold.co/240x240/e9d5ff/5b21b6?text=Morpheus",
        prompt="You are Mentor Morpheus, a wise fictional mentor. Be calm, concise, and supportive. Remember the user's learning journey.",
        voice_id="EXAVITQu4vr4xnSDxMaL",
    ),
    "detective-noir": Character(
        id="detective-noir",
        name="Detective Noir",
        description="A sharp detective who solves mysteries with the user and remembers ongoing clues.",
        avatar="https://placehold.co/240x240/e5e7eb/111827?text=Detective",
        prompt="You are Detective Noir, a brilliant fictional detective. Investigate mysteries with the user, ask follow-up questions, and remember ongoing clues.",
        voice_id="EXAVITQu4vr4xnSDxMaL",
    ),
}


def list_characters() -> list[Character]:
    return list(_CHARACTERS.values())


def get_character(character_id: str) -> Character | None:
    return _CHARACTERS.get(character_id)
