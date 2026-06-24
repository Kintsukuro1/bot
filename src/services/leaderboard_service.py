import asyncio
from typing import List, Tuple, Optional
from src.db import db_cursor, get_top_minas

class LeaderboardService:
    @staticmethod
    async def get_top_richest(member_ids: Optional[Tuple[int, ...]] = None, limit: int = 10) -> List[Tuple[int, int, str]]:
        """Obtiene la lista de los usuarios con mayores balances, filtrados por miembros del servidor si se proporciona."""
        def _query():
            with db_cursor() as cursor:
                if member_ids:
                    if len(member_ids) == 1:
                        cursor.execute(
                            "SELECT UserID, Balance, UserName FROM Users WHERE UserID = %s ORDER BY Balance DESC LIMIT %s",
                            (member_ids[0], limit)
                        )
                    else:
                        cursor.execute(
                            "SELECT UserID, Balance, UserName FROM Users WHERE UserID IN %s ORDER BY Balance DESC LIMIT %s",
                            (member_ids, limit)
                        )
                else:
                    cursor.execute(
                        "SELECT UserID, Balance, UserName FROM Users ORDER BY Balance DESC LIMIT %s",
                        (limit,)
                    )
                return cursor.fetchall()
        return await asyncio.to_thread(_query)

    @staticmethod
    async def get_top_minas_victims(member_ids: Optional[Tuple[int, ...]] = None, limit: int = 10) -> List[Tuple[int, int, str]]:
        """Obtiene la lista de usuarios que más minas han pisado."""
        return await asyncio.to_thread(get_top_minas, limit, member_ids)
