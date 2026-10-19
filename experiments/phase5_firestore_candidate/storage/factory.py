from __future__ import annotations

from dataclasses import dataclass,field
from pathlib import Path
import os
import threading
from urllib.parse import urlsplit

from storage.base import validate_lineage
from storage.sqlite_provider import SQLiteProvider
from storage.firestore_provider import FirestoreProvider,GoogleFirestoreGateway

ROOT=Path(__file__).resolve().parents[1]
SDK_LOCK=threading.Lock()


@dataclass(frozen=True)
class Settings:
    backend: str="sqlite"
    sqlite_path: Path=ROOT/"data"/"candidate.sqlite"
    lineage: str="candidate-local"
    project: str=""
    database: str="(default)"
    emulator_host: str=""
    allow_remote: bool=False
    allow_writes: bool=False
    model_path: Path=ROOT/"lnn_heat_index_model.pth"
    auth_mode: str="off"
    device_token: str=field(default="",repr=False)

    @classmethod
    def from_env(cls):
        return cls(backend=os.getenv("STORAGE_BACKEND","sqlite"),sqlite_path=Path(os.getenv("SQLITE_PATH",str(cls.sqlite_path))),
                   lineage=os.getenv("SOURCE_LINEAGE_ID","candidate-local"),project=os.getenv("FIREBASE_PROJECT_ID",""),
                   database=os.getenv("FIRESTORE_DATABASE_ID","(default)"),emulator_host=os.getenv("FIRESTORE_EMULATOR_HOST",""),
                   allow_remote=os.getenv("FIRESTORE_ALLOW_REMOTE","false").lower()=="true",
                   allow_writes=os.getenv("FIRESTORE_ALLOW_WRITES","false").lower()=="true",
                   model_path=Path(os.getenv("MODEL_PATH",str(cls.model_path))),auth_mode=os.getenv("DEVICE_AUTH_MODE","off"),
                   device_token=os.getenv("DEVICE_AUTH_TOKEN",""))


def initialize_client(settings):
    """Called only on an explicit operation, never from module import/app creation."""
    if not settings.project or settings.lineage=="candidate-local":
        raise ValueError("Explicit project and stable non-default lineage are required for Firestore.")
    if settings.emulator_host:
        host=urlsplit("//"+settings.emulator_host)
        if host.hostname not in {"localhost","127.0.0.1","::1"} or not host.port or not settings.project.startswith("demo-"):
            raise ValueError("Emulator must use a loopback host and a demo- project.")
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore
        # Client reads FIRESTORE_EMULATOR_HOST; reject configuration/environment mismatch.
        if os.getenv("FIRESTORE_EMULATOR_HOST")!=settings.emulator_host:
            raise ValueError("Emulator host must match the explicit environment setting.")
        return firestore.Client(project=settings.project,credentials=AnonymousCredentials(),database=settings.database)
    if not settings.allow_remote:
        raise ValueError("Remote Firestore access is disabled by default.")
    if os.getenv("FIRESTORE_EMULATOR_HOST"):
        raise ValueError("Unexpected emulator environment; refusing ambiguous target.")
    import firebase_admin
    from firebase_admin import credentials,firestore
    name="phase5-"+settings.project+"-"+settings.database.replace("/","_")
    with SDK_LOCK:
        try: application=firebase_admin.get_app(name)
        except ValueError:
            application=firebase_admin.initialize_app(credentials.ApplicationDefault(),{"projectId":settings.project},name=name)
    return firestore.client(app=application,database_id=settings.database)


def make_storage(settings):
    validate_lineage(settings.lineage)
    if settings.backend=="sqlite": return SQLiteProvider(settings.sqlite_path,settings.lineage)
    if settings.backend=="firestore":
        return FirestoreProvider(settings.lineage,lambda:GoogleFirestoreGateway(initialize_client(settings)),settings.allow_writes)
    raise ValueError("STORAGE_BACKEND must be sqlite or firestore; no implicit fallback is supported.")
