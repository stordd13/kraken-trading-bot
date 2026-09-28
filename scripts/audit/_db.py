"""Couche base partagée des scripts d'audit — lecture seule garantie par Postgres.

Brief : ``agent/AGENT_C3B_PRODUCTEUR.md`` § « Lot 2 » ; module séparé de ``_common.py`` par décision du
2026-09-27 (liste close amendée). C'est le seul module partagé de ``scripts/audit`` qui importe
``krakenbot.core.database`` et ``sqlalchemy`` : ``_common`` reste pur, et la chaîne C3 (``c3_common``)
n'importe jamais ce module.
"""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from krakenbot.core.database import DatabaseManager  # noqa: E402


class ReadOnlyDatabaseManager(DatabaseManager):
    """Le ``DatabaseManager`` des chargeurs du moteur, en lecture seule **côté Postgres** : chaque connexion pose
    ``default_transaction_read_only = on``, donc toute transaction ouverte par ce moteur est ``READ ONLY`` — une
    écriture lèverait, elle n'est pas seulement évitée."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self._engine = create_async_engine(
            url, connect_args={"server_settings": {"default_transaction_read_only": "on"}}
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        self._initialized = True
