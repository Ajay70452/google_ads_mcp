"""
Seed client_accounts table from the live MCC.
Run once: .venv/Scripts/python.exe -m scripts.seed_accounts
"""
import asyncio
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

load_dotenv()

from backend.database import engine
from backend.google_ads.auth import get_google_ads_client
from backend.google_ads.reporting import list_child_accounts


async def seed():
    client = get_google_ads_client()
    accounts = list_child_accounts(client)
    print(f"Fetched {len(accounts)} accounts from MCC")

    now = datetime.now(timezone.utc)

    async with engine.begin() as conn:
        for acc in accounts:
            stmt = insert(text.__class__).values()  # use raw upsert below
            await conn.execute(
                text("""
                    INSERT INTO client_accounts (customer_id, name, is_active, created_at)
                    VALUES (:customer_id, :name, TRUE, :created_at)
                    ON CONFLICT (customer_id) DO UPDATE
                        SET name = EXCLUDED.name,
                            is_active = TRUE
                """),
                {
                    "customer_id": acc["customer_id"],
                    "name": acc["name"],
                    "created_at": now,
                },
            )

        result = await conn.execute(text("SELECT COUNT(*) FROM client_accounts"))
        count = result.scalar()

    print(f"Done — {count} accounts in client_accounts table")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
