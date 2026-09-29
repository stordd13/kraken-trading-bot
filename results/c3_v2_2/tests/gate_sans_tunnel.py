"""Greffon pytest de la porte C3 v2.2 : « suite sans tunnel ». Chargé par `-p gate_sans_tunnel` avant la collecte, il
refuse, pour le seul processus pytest, toute connexion à 127.0.0.1:5432 et :5433 (tunnel SSH vers la base du
serveur, ou Postgres local). Les tests liés à la base s'ignorent alors comme en CI (`_db_reachable()` faux), et aucun
test ne peut lire la base, que le tunnel soit ouvert ou non. Le tunnel lui-même n'est pas touché."""

from __future__ import annotations

import socket

_BLOCKED = {("127.0.0.1", 5432), ("127.0.0.1", 5433), ("localhost", 5432), ("localhost", 5433)}
_create_connection = socket.create_connection
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex


def _blocked(address: object) -> bool:
    return isinstance(address, tuple) and len(address) >= 2 and (address[0], address[1]) in _BLOCKED


def create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
    if _blocked(address):
        raise ConnectionRefusedError(f"porte C3 v2.2 sans tunnel : {address} refusé")
    return _create_connection(address, *args, **kwargs)


def connect(self, address):  # type: ignore[no-untyped-def]
    if _blocked(address):
        raise ConnectionRefusedError(f"porte C3 v2.2 sans tunnel : {address} refusé")
    return _connect(self, address)


def connect_ex(self, address):  # type: ignore[no-untyped-def]
    if _blocked(address):
        return 61  # ECONNREFUSED
    return _connect_ex(self, address)


socket.create_connection = create_connection  # type: ignore[assignment]
socket.socket.connect = connect  # type: ignore[method-assign]
socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
