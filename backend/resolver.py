"""
Name-to-customer_id resolver.
Lets Claude pass clinic names like 'Apex Dental' instead of '8785895348'.
"""
from difflib import SequenceMatcher
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text


async def resolve_customer_id(identifier: str, db: AsyncSession) -> tuple[str, str]:
    """
    Given a customer_id (digits) or a partial clinic name, return
    (customer_id, account_name).

    Raises ValueError with helpful message if no match found.
    """
    identifier = identifier.strip()

    # If it looks like a numeric ID, validate it exists
    if identifier.replace("-", "").isdigit():
        cid = identifier.replace("-", "")
        result = await db.execute(
            text("SELECT customer_id, name FROM client_accounts WHERE customer_id = :cid"),
            {"cid": cid},
        )
        row = result.fetchone()
        if row:
            return row.customer_id, row.name
        raise ValueError(f"No account found with customer_id '{cid}'")

    # Fuzzy name match — fetch all, score, return best
    result = await db.execute(
        text("SELECT customer_id, name FROM client_accounts WHERE is_active = TRUE")
    )
    rows = result.fetchall()

    if not rows:
        raise ValueError("No accounts in the registry. Run seed_accounts first.")

    query = identifier.lower()

    def score(name: str) -> float:
        name_lower = name.lower()
        # Exact substring match gets top score
        if query in name_lower:
            return 1.0
        # Fuzzy ratio for partial matches
        return SequenceMatcher(None, query, name_lower).ratio()

    scored = [(score(row.name), row.customer_id, row.name) for row in rows]
    scored.sort(reverse=True)

    best_score, best_id, best_name = scored[0]

    if best_score < 0.4:
        top5 = [name for _, _, name in scored[:5]]
        raise ValueError(
            f"No account found matching '{identifier}'. "
            f"Did you mean one of: {', '.join(top5)}?"
        )

    return best_id, best_name


async def list_all_accounts(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        text("SELECT customer_id, name, city, is_active FROM client_accounts ORDER BY name")
    )
    return [
        {"customer_id": r.customer_id, "name": r.name, "city": r.city, "is_active": r.is_active}
        for r in result.fetchall()
    ]
