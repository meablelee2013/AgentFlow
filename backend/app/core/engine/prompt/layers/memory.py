"""Layer 2: Memory — "Who is the user?" """

from app.core.engine.prompt.base import BasePromptLayer, PromptContext


class MemoryLayer(BasePromptLayer):
    """Inject user memories from user_memories table.

    condition() returns True only when user_id is set and memory is enabled.
    render() queries the DB for active memories, deduplicates by key,
    and formats them grouped by category.
    """

    name = "memory"
    priority = 2
    required = False  # Conditional on user_id + memory_enabled

    # ── Configuration ──
    MAX_MEMORIES = 20
    MAX_PER_CATEGORY = 5
    MAX_CONTENT_LENGTH = 100
    MAX_TOTAL_TOKENS = 200

    # Category order for display
    CATEGORY_LABELS = {
        "personal": "Personal Info",
        "preference": "Preferences",
        "project": "Current Projects",
        "relationship": "Relationships",
        "context": "Current Context",
    }

    def condition(self, ctx: PromptContext) -> bool:
        return bool(ctx.user_id and ctx.memory_enabled)

    async def render(self, ctx: PromptContext) -> str:
        """Query memories and format them for system prompt injection.

        Pipeline:
          1. Query active memories from DB
          2. Deduplicate by key (keep highest confidence)
          3. Truncate long content
          4. Sort by confidence, bucket by category
          5. Format as Markdown
        """
        from app.services.memory_service import MemoryService

        memory_service = MemoryService(ctx.extra.get("db"))
        memories = await memory_service.get_active_by_category(ctx.user_id)

        if not memories:
            return ""

        # ── Step 1: Dedup by key, keep highest confidence ──
        seen: dict[str, dict] = {}
        for m in memories:
            key = m.key.lower().strip()
            if key in seen:
                if m.confidence > seen[key]["confidence"]:
                    seen[key] = {"content": m.content, "category": m.category,
                                 "confidence": m.confidence}
            else:
                seen[key] = {"content": m.content, "category": m.category,
                             "confidence": m.confidence}

        # ── Step 2: Truncate + sort by confidence ──
        items = []
        for key, data in seen.items():
            content = data["content"]
            if len(content) > self.MAX_CONTENT_LENGTH:
                content = content[:self.MAX_CONTENT_LENGTH - 3] + "..."
            items.append({
                "key": key,
                "content": content,
                "category": data["category"],
                "confidence": data["confidence"],
            })
        items.sort(key=lambda x: x["confidence"], reverse=True)

        # ── Step 3: Bucket by category ──
        buckets: dict[str, list[str]] = {}
        for item in items:
            cat = item["category"]
            if cat not in buckets:
                buckets[cat] = []
            if len(buckets[cat]) < self.MAX_PER_CATEGORY:
                buckets[cat].append(f"- {item['content']}")

        # ── Step 4: Assemble output ──
        lines: list[str] = []
        for cat in self.CATEGORY_LABELS:
            if cat in buckets and buckets[cat]:
                label = self.CATEGORY_LABELS[cat]
                lines.append(f"**{label}**:")
                lines.extend(buckets[cat][:self.MAX_PER_CATEGORY])
                lines.append("")

        if not lines:
            return ""

        result = "## User Context (from previous conversations)\n" + "\n".join(lines)

        # ── Step 5: Token budget guard (rough: 4 chars ≈ 1 token) ──
        if len(result) // 4 > self.MAX_TOTAL_TOKENS:
            # Trim to fit budget by dropping lowest-confidence items
            trimmed_lines = result.split("\n")
            while len("\n".join(trimmed_lines)) // 4 > self.MAX_TOTAL_TOKENS and len(trimmed_lines) > 3:
                trimmed_lines.pop()
            result = "\n".join(trimmed_lines).rstrip() + "\n(truncated for length)"

        return result.strip()
