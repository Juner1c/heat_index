from datetime import datetime,timezone
import socket
import sqlite3

import pytest

from storage.base import Reading


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args,**kwargs):raise AssertionError("Candidate automated tests must not use the network.")
    monkeypatch.setattr(socket.socket,"connect",deny)
    monkeypatch.setattr(socket,"create_connection",deny)


@pytest.fixture
def reading():
    return Reading("synthetic-test-v1",None,"test-device",30,70,35.25,36.75,"TEST ADVISORY",None,None,
                   datetime(2026,10,14,0,0,tzinfo=timezone.utc),None,"esp32")


@pytest.fixture
def legacy_db(tmp_path):
    path=tmp_path/"synthetic-legacy.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sensor_readings(id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp TEXT NOT NULL,temperature REAL NOT NULL,humidity REAL NOT NULL,heat_index REAL NOT NULL,forecast_3hr_hi REAL NOT NULL,pagasa_advisory TEXT NOT NULL)")
        db.executemany("INSERT INTO sensor_readings(timestamp,temperature,humidity,heat_index,forecast_3hr_hi,pagasa_advisory) VALUES(?,?,?,?,?,?)",
                       [("2024-08-01 12:00:00",30,70,35,36,"TEST ONLY"),("2024-08-01 12:00:16",31,71,36,37,"TEST ONLY"),("2024-08-01 12:00:32",32,72,37,38,"TEST ONLY")])
    return path
