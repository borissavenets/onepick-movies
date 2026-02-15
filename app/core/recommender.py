"""Real recommendation engine with epsilon-greedy selection and learning."""

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.core.anti_repeat import get_excluded_item_ids
from app.core.learning import calculate_weight_bonus, get_user_weight
from app.core.rationale import (
    generate_delta_explainer,
    generate_rationale,
    generate_when_to_watch,
)
from app.core.tagging import (
    context_key,
    get_tone_bucket,
    hint_match_score,
    match_score,
    normalize_pace,
    parse_hint,
    parse_tags,
    translate_hint_keywords,
)
from app.logging import get_logger
from app.storage import EventsRepo, ItemsRepo, RecsRepo, UsersRepo
from app.storage.json_utils import safe_json_dumps
from app.storage.models import Item

logger = get_logger(__name__)


@dataclass
class RecommendationResult:
    """Result from recommendation engine."""

    rec_id: str
    item_id: str
    title: str
    rationale: str
    when_to_watch: str
    poster_url: str | None = None
    rating: float | None = None
    delta_explainer: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredCandidate:
    """Item with computed score."""

    item: Item
    score: float
    tags: dict[str, Any] | None
    match_score: float
    weight_bonus: float
    novelty_bonus: float


def _deterministic_seed(user_id: str, mode: str, salt: str = "") -> int:
    """Generate deterministic seed from user/date/mode.

    Args:
        user_id: User ID
        mode: Recommendation mode
        salt: Optional additional salt

    Returns:
        Integer seed
    """
    today = date.today().isoformat()
    combined = f"{user_id}:{today}:{mode}:{salt}"
    hash_bytes = hashlib.sha256(combined.encode()).digest()
    return int.from_bytes(hash_bytes[:4], "big")


def _seeded_random(seed: int) -> random.Random:
    """Create seeded Random instance.

    Args:
        seed: Random seed

    Returns:
        Seeded Random instance
    """
    rng = random.Random()
    rng.seed(seed)
    return rng


def _compute_novelty_bonus(item: Item, rng: random.Random) -> float:
    """Compute small novelty bonus for scoring variation.

    Args:
        item: Item instance
        rng: Seeded random generator

    Returns:
        Novelty bonus (0.0 to 0.2)
    """
    # Small random bonus seeded per item
    item_seed = hash(item.item_id) % 10000
    rng_item = random.Random(item_seed)
    return rng_item.uniform(0.0, 0.2)


def _flip_pace(pace: str) -> str:
    """Flip pace value."""
    return "fast" if pace == "slow" else "slow"


def _flip_format(fmt: str) -> str:
    """Flip format value."""
    return "series" if fmt == "movie" else "movie"


async def get_recommendation(
    session: AsyncSession,
    user_id: str,
    answers: dict[str, str],
    mode: Literal["normal", "another", "miss_recover"] = "normal",
    exclude_item_ids: set[str] | None = None,
    last_context: dict[str, Any] | None = None,
) -> RecommendationResult | None:
    """Get a recommendation based on user answers.

    Uses epsilon-greedy selection with tag matching and user weight learning.

    Args:
        session: Database session
        user_id: User ID
        answers: User answers dict with state, pace, format keys
        mode: Recommendation mode
        exclude_item_ids: Additional item IDs to exclude
        last_context: Previous recommendation context (for "another" mode)

    Returns:
        RecommendationResult or None if no items available
    """
    items_repo = ItemsRepo(session)
    recs_repo = RecsRepo(session)
    users_repo = UsersRepo(session)
    events_repo = EventsRepo(session)

    # Ensure user exists and update last_seen
    await users_repo.ensure_user(user_id)

    # Parse hint and apply overrides (hint has priority over button answers)
    hint_text = answers.get("hint")
    hint_result = parse_hint(hint_text)

    # LLM-translate UA hint to EN keywords for TMDB matching
    if hint_text:
        en_keywords = await translate_hint_keywords(hint_text)
        if en_keywords:
            hint_result.search_words.extend(en_keywords)

    if hint_result.overrides:
        answers = {**answers, **hint_result.overrides}

    # Get item type from format
    item_type = answers.get("format", "movie")
    if item_type not in ("movie", "series"):
        item_type = "movie"

    # Handle "another-but-different" mode
    delta_info: dict[str, Any] = {}
    delta_explainer: str | None = None
    effective_answers = answers.copy()

    if mode == "another" and last_context:
        delta_info, effective_answers, delta_explainer = _apply_another_delta(
            answers, last_context, session
        )
        # Update item_type if format was flipped
        if delta_info.get("format_flipped"):
            item_type = effective_answers.get("format", item_type)

    # Build exclusion set
    excluded = await get_excluded_item_ids(
        session, user_id, additional_excludes=exclude_item_ids
    )

    # Get candidates
    candidates = await _get_candidates(
        items_repo, item_type, excluded, effective_answers
    )

    if not candidates:
        logger.warning(f"No candidates for user={user_id}, type={item_type}")
        return None

    # Score candidates
    seed = _deterministic_seed(user_id, mode)
    rng = _seeded_random(seed)

    user_weight = await get_user_weight(session, user_id, effective_answers)

    scored = await _score_candidates(
        candidates, effective_answers, user_weight, rng, hint_result
    )

    if not scored:
        logger.warning(f"No valid scored candidates for user={user_id}")
        return None

    # Epsilon-greedy selection
    epsilon = config.recs_epsilon
    selected = _epsilon_greedy_select(scored, epsilon, rng)

    # Build context
    context = {
        **effective_answers,
        "mode": mode,
        "epsilon_used": epsilon,
        "candidate_count": len(scored),
        "selected_score": selected.score,
        "tone_bucket": get_tone_bucket(selected.tags, effective_answers.get("state", "escape")),
    }
    if hint_text:
        context["hint"] = hint_text
    if delta_info:
        context["delta"] = delta_info

    # Create recommendation record
    rec_id = await recs_repo.create_rec(
        user_id=user_id,
        item_id=selected.item.item_id,
        context=context,
    )

    # Generate rationale and when_to_watch
    rationale = generate_rationale(rec_id, effective_answers, selected.tags)
    when_to_watch = generate_when_to_watch(rec_id, effective_answers)

    # Log recommendation created
    await events_repo.log_event(
        event_name="rec_created",
        user_id=user_id,
        rec_id=rec_id,
        payload={
            "item_id": selected.item.item_id,
            "title": selected.item.title,
            "mode": mode,
            "score": selected.score,
            "match_score": selected.match_score,
            "weight_bonus": selected.weight_bonus,
        },
    )

    logger.info(
        f"Created recommendation rec_id={rec_id[:8]} "
        f"item={selected.item.item_id} score={selected.score:.2f} "
        f"for user={user_id} mode={mode}"
    )

    # Build source mix info
    curated_count = sum(1 for s in scored if s.item.source == "curated")
    tmdb_count = len(scored) - curated_count

    return RecommendationResult(
        rec_id=rec_id,
        item_id=selected.item.item_id,
        title=selected.item.title,
        rationale=rationale,
        when_to_watch=when_to_watch,
        poster_url=getattr(selected.item, "poster_url", None),
        rating=getattr(selected.item, "vote_average", None),
        delta_explainer=delta_explainer,
        meta={
            "mode": mode,
            "epsilon_used": epsilon,
            "candidate_count": len(scored),
            "source_mix": {"curated": curated_count, "tmdb": tmdb_count},
            "score": selected.score,
        },
    )


def _apply_another_delta(
    answers: dict[str, str],
    last_context: dict[str, Any],
    session: AsyncSession,
) -> tuple[dict[str, Any], dict[str, str], str | None]:
    """Apply 'another-but-different' delta to answers.

    Exactly one dimension changes:
    1. Flip pace (preferred)
    2. Shift tone (if pace already flipped)
    3. Flip format (last resort, if same format twice)

    Args:
        answers: Current answers
        last_context: Previous recommendation context

    Returns:
        Tuple of (delta_info, modified_answers, delta_explainer)
    """
    effective = answers.copy()
    delta_info: dict[str, Any] = {}

    last_pace = last_context.get("pace")
    last_delta = last_context.get("delta", {})

    # Check if pace was already flipped recently
    pace_recently_flipped = last_delta.get("pace_flipped", False)

    current_pace = answers.get("pace", "slow")

    if not pace_recently_flipped:
        # Option 1: Flip pace
        new_pace = _flip_pace(current_pace)
        effective["pace"] = new_pace
        delta_info["pace_flipped"] = True
        explainer = generate_delta_explainer("pace_flipped", new_pace, "delta")
        return delta_info, effective, explainer

    # Option 2: Shift tone (implicit - we don't change answers, just scoring will vary)
    # For now, just mark tone_shifted
    delta_info["tone_shifted"] = True
    explainer = generate_delta_explainer("tone_shifted", "", "delta")

    return delta_info, effective, explainer


async def _get_candidates(
    items_repo: ItemsRepo,
    item_type: str,
    excluded: set[str],
    answers: dict[str, str],
) -> list[Item]:
    """Get candidate items for recommendation.

    Handles curated preference and quality gates.

    Args:
        items_repo: Items repository
        item_type: Item type filter
        excluded: Item IDs to exclude
        answers: User answers

    Returns:
        List of candidate items
    """
    limit = config.recs_max_candidates

    # If prefer curated, try curated first
    if config.recs_prefer_curated:
        curated = await items_repo.list_candidates(
            item_type=item_type,
            source_preference="curated",
            exclude_ids=excluded if excluded else None,
            limit=limit,
        )

        if curated and len(curated) >= 5:
            # Have enough curated items
            return curated

        # Supplement with TMDB items
        needed = limit - len(curated)
        curated_ids = {c.item_id for c in curated}
        all_excluded = excluded | curated_ids

        tmdb = await items_repo.list_candidates(
            item_type=item_type,
            source_preference="tmdb",
            exclude_ids=all_excluded if all_excluded else None,
            limit=needed,
        )

        return curated + tmdb

    # No preference, get any items
    return await items_repo.list_candidates(
        item_type=item_type,
        exclude_ids=excluded if excluded else None,
        limit=limit,
    )


async def _score_candidates(
    candidates: list[Item],
    answers: dict[str, str],
    user_weight: int,
    rng: random.Random,
    hint_result=None,
) -> list[ScoredCandidate]:
    """Score all candidates.

    Score formula:
    - base_score (from item)
    - + match_score (tag matching)
    - + weight_bonus (user learning)
    - + novelty_bonus (small random variation)
    - + hint_bonus (keyword matching from user hint)

    Args:
        candidates: List of candidate items
        answers: User answers
        user_weight: User's weight for this context
        rng: Seeded random generator
        hint_result: Parsed hint data (optional)

    Returns:
        List of scored candidates, sorted by score descending
    """
    scored: list[ScoredCandidate] = []
    require_tags = config.recs_require_tags

    for item in candidates:
        tags = parse_tags(item.tags_json)

        # Calculate match score
        m_score = match_score(tags, answers, require_tags=require_tags)

        # Skip items with -inf score (missing required tags)
        if m_score == float("-inf"):
            continue

        # Calculate weight bonus
        w_bonus = calculate_weight_bonus(user_weight)

        # Calculate novelty bonus
        n_bonus = _compute_novelty_bonus(item, rng)

        # Calculate hint bonus
        h_bonus = 0.0
        if hint_result:
            h_bonus = hint_match_score(
                item.title,
                tags,
                hint_result,
                overview=getattr(item, "overview", None),
                genres_json=getattr(item, "genres_json", None),
                credits_json=getattr(item, "credits_json", None),
            )

        # Total score
        total = item.base_score + m_score + w_bonus + n_bonus + h_bonus

        scored.append(
            ScoredCandidate(
                item=item,
                score=total,
                tags=tags,
                match_score=m_score,
                weight_bonus=w_bonus,
                novelty_bonus=n_bonus,
            )
        )

    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)

    return scored


def _epsilon_greedy_select(
    scored: list[ScoredCandidate],
    epsilon: float,
    rng: random.Random,
) -> ScoredCandidate:
    """Select candidate using epsilon-greedy strategy.

    With probability (1-epsilon): select best scoring item (exploit)
    With probability epsilon: select random from top 20 (explore)

    Args:
        scored: Sorted list of scored candidates
        epsilon: Exploration probability
        rng: Random generator

    Returns:
        Selected candidate
    """
    if not scored:
        raise ValueError("No candidates to select from")

    # Explore vs exploit
    if rng.random() < epsilon:
        # Explore: random from top 20
        top_k = min(20, len(scored))
        return rng.choice(scored[:top_k])
    else:
        # Exploit: best score
        return scored[0]


def epsilon_greedy_select_deterministic(
    scored: list[ScoredCandidate],
    epsilon: float,
    seed: int,
) -> ScoredCandidate:
    """Deterministic epsilon-greedy for testing.

    Args:
        scored: Sorted candidates
        epsilon: Exploration probability
        seed: Random seed

    Returns:
        Selected candidate
    """
    rng = _seeded_random(seed)
    return _epsilon_greedy_select(scored, epsilon, rng)
