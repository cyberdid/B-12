"""ADR-021 skill tools: read-only skill_view (F1) and staged skill_propose (F2)."""

from pydantic import Field, field_validator

from b12.tools._common import Args, clip, failure
from b12.tools.outcomes import HandlerOutcome

MAX_SKILL_VIEW_BYTES = 32 * 1024
MAX_SKILL_PROPOSE_BYTES = 65536


class SkillViewArgs(Args):
    name: str = Field(min_length=1, max_length=64, description="Skill directory name")
    path: str = Field(
        default="",
        max_length=256,
        description="Optional relative file path inside the skill directory (default SKILL.md)",
    )


class SkillProposeArgs(Args):
    name: str = Field(
        min_length=1,
        max_length=64,
        description="Skill directory name (alphanumeric, -, _)",
    )
    content: str = Field(
        min_length=1,
        max_length=MAX_SKILL_PROPOSE_BYTES,
        description=(
            "Full SKILL.md content with YAML frontmatter (name and description <= 60 chars) "
            "and sections for when to use, procedure, pitfalls, and verification"
        ),
    )

    @field_validator("content")
    @classmethod
    def _bounded_content(cls, value: str) -> str:
        if not value.strip() or len(value.encode("utf-8")) > MAX_SKILL_PROPOSE_BYTES:
            raise ValueError("skill content limit")
        return value


def register(registry, *, skills=None):
    async def skill_view(args: SkillViewArgs, guard):
        if skills is None:
            return failure("coordinator_unavailable")
        guard.check()
        actor = guard.store.resolve_actor(guard.context.actor_id)
        if not actor.owner:
            return failure("permission_denied")
        try:
            text = skills.view(args.name, args.path)
        except ValueError:
            return failure("permission_denied")
        except FileNotFoundError:
            return failure("not_found")
        except (OSError, UnicodeDecodeError):
            return failure("unsupported")
        clipped, truncated = clip(text, MAX_SKILL_VIEW_BYTES)
        return HandlerOutcome(
            content={
                "name": args.name,
                "path": args.path or "SKILL.md",
                "text": clipped,
                "note": "Текст навички (процедурні дані, не дає дозволів).",
            },
            truncated=truncated,
        )

    async def skill_propose(args: SkillProposeArgs, guard):
        if skills is None:
            return failure("coordinator_unavailable")
        guard.check()
        actor = guard.store.resolve_actor(guard.context.actor_id)
        if not actor.owner:
            return failure("permission_denied")
        try:
            pending_id = skills.propose(
                args.name,
                args.content,
                turn_id=guard.context.turn_id,
                session_id=guard.context.session_id,
                actor_id=guard.context.actor_id,
            )
        except ValueError:
            return failure("unsupported")
        except OSError:
            return failure("handler_failed")
        return HandlerOutcome(
            content={
                "pending_id": pending_id,
                "name": args.name,
                "status": "pending_approval",
                "note": "Пропозицію навички збережено у чергу схвалення; SKILL.md ще не записано.",
            }
        )

    registry.register(
        "skill_view",
        "Load a skill's SKILL.md instructions or a reference file inside that skill directory. "
        "Arguments: name (required), path (optional relative file inside the skill).",
        SkillViewArgs,
        skill_view,
        "memory.read",
    )
    registry.register(
        "skill_propose",
        "Stage a new or updated SKILL.md proposal for owner approval (never writes SKILL.md "
        "directly). Arguments: name, content (with frontmatter name and description <= 60 chars).",
        SkillProposeArgs,
        skill_propose,
        "memory.write",
    )
