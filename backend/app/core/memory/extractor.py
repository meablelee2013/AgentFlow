"""MemoryExtractor — async LLM-based extraction of user facts from conversation"""
import json
import uuid

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
import structlog

from app.config import settings
from app.services.memory_service import MemoryService

logger = structlog.get_logger()

EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction system. Your job is to read the latest
exchange in a conversation and extract durable facts about the user that should
be remembered for future conversations.

Extract facts in these categories:
- personal: name, location, job, role, company, experience level, background
- preference: likes, dislikes, preferred tools/languages/frameworks, communication style, workflow habits
- project: ongoing projects, goals, tasks the user is working on, features they're building
- relationship: team context, who they work with, reporting structure
- context: environment, constraints, their system setup, anything else relevant to future interactions

DO NOT extract:
- One-time requests or questions (e.g., "what is the capital of France", "write me a function")
- Opinions about specific code or technical decisions that are clearly situational/temporary
- Irrelevant small talk or chatter
- Information that is obviously transient (e.g., "I'm on my phone right now")
- Information the user explicitly asked not to remember

For each fact, provide:
1. category: one of the above (personal, preference, project, relationship, context)
2. key: a short 3-8 word label in the user's language (e.g., "User's name", "Preferred language", "Current project")
3. content: the full fact as a complete sentence (e.g., "User's name is Alice, a senior backend engineer at Acme Corp")
4. confidence: 0.0-1.0, how certain you are this is a durable fact about the user (not a transient preference)

Return ONLY a JSON array with no other text. Format:
[
  {"category": "personal", "key": "User's name", "content": "User's name is Alice, a senior backend engineer", "confidence": 0.95},
  {"category": "preference", "key": "Preferred language", "content": "User prefers Python for backend and TypeScript for frontend", "confidence": 0.9}
]

If no new durable facts are found in this exchange, return an empty array [].
Do NOT repeat facts that were already covered in previous exchanges — only extract NEW information."""


class MemoryExtractor:
    """Extract user facts from conversation asynchronously.

    Runs via FastAPI BackgroundTasks after the chat response is sent,
    so the user never waits for this to complete.

    Usage:
        extractor = MemoryExtractor()
        await extractor.extract_and_persist(
            thread_id="abc-123",
            conversation_id=UUID("..."),
            user_id=UUID("..."),
            db_session_factory=AsyncSessionLocal,
        )
    """

    def __init__(self, model: str | None = None):
        self.model = model or settings.MEMORY_EXTRACTION_MODEL

    async def extract_and_persist(
        self,
        thread_id: str,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        messages: list[dict],
        db_session,
    ) -> list[dict]:
        """Run extraction on recent messages and persist extracted facts.

        Args:
            thread_id: the LangGraph thread identifier
            conversation_id: the Conversation UUID in PostgreSQL
            user_id: the user identifier for memory scoping
            messages: recent conversation messages (last N exchanges)
            db_session: an async SQLAlchemy session (dedicated for background task)

        Returns:
            List of extracted facts (for logging/debugging)
        """
        if not settings.MEMORY_EXTRACTION_ENABLED:
            logger.debug("memory_extraction_disabled")
            return []

        if not messages:
            logger.debug("memory_extraction_no_messages", thread_id=thread_id)
            return []

        try:
            # Build conversation text for the extraction LLM
            conversation_text = self._format_conversation(messages)

            # Call LLM for extraction
            facts = await self._extract_facts(conversation_text)

            if not facts:
                logger.debug("memory_extraction_no_facts", thread_id=thread_id)
                return []

            # Upsert each fact
            service = MemoryService(db_session)
            saved = []
            for fact in facts:
                mem = await service.upsert_memory(
                    user_id=user_id,
                    category=fact["category"],
                    key=fact["key"],
                    content=fact["content"],
                    confidence=fact.get("confidence", 1.0),
                    source_conversation_id=conversation_id,
                )
                if mem:
                    saved.append(fact)

            logger.info(
                "memory_extraction_complete",
                thread_id=thread_id,
                extracted_count=len(facts),
                saved_count=len(saved),
            )
            return saved

        except Exception:
            logger.exception(
                "memory_extraction_failed",
                thread_id=thread_id,
            )
            return []

    async def _extract_facts(self, conversation_text: str) -> list[dict]:
        """Call the extraction LLM and parse the JSON response."""
        llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model=self.model,
            temperature=0.1,  # Low temperature for consistent, factual extraction
        )

        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=f"Conversation:\n{conversation_text}"),
        ]

        response = await llm.ainvoke(messages)
        content = (response.content or "").strip()

        # Parse JSON — the LLM may wrap it in markdown code fences
        if content.startswith("```"):
            # Strip code fence
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])

        try:
            facts = json.loads(content)
            if isinstance(facts, list):
                # Validate each fact has required fields
                return [
                    f for f in facts
                    if isinstance(f, dict)
                    and "category" in f
                    and "key" in f
                    and "content" in f
                ]
        except json.JSONDecodeError:
            logger.warning(
                "memory_extraction_json_parse_failed",
                raw_content=content[:500],
            )

        return []

    @staticmethod
    def _format_conversation(messages: list[dict]) -> str:
        """Format messages as a conversation transcript for the extraction LLM."""
        lines = []
        for m in messages:
            role = m["role"].capitalize()
            content = m.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)
