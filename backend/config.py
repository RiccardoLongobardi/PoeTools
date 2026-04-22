"""Application settings, loaded from env vars and/or a .env file.

Tutto viene qui dentro: niente valori magici sparsi nel codice.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Radice del progetto: faustus-dashboard/
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Runtime settings.

    Override con variabili d'ambiente `FAUSTUS_<NAME>` o tramite file `.env`
    nella root del progetto.
    """

    # -- Generale --
    app_name: str = "Faustus Dashboard"
    debug: bool = False

    # -- Lega target --
    # Default su Mirage perché è l'attuale softcore (3.28).
    # Quando la lega cambia, aggiornare qui o via env FAUSTUS_LEAGUE.
    league: str = "Mirage"

    # -- Data source --
    # URL base dell'API poe.ninja. Estratto come costante così i test
    # possono mockarlo.
    poe_ninja_base_url: str = "https://poe.ninja/api/data"

    # User-Agent che mandiamo a poe.ninja. Educato includere identificazione.
    http_user_agent: str = (
        "faustus-dashboard/0.1 (+personal use; ric.longobardi@outlook.it)"
    )

    # Timeout delle richieste HTTP in secondi.
    http_timeout_s: float = 20.0

    # -- Fetcher --
    # Ogni quanto rieseguiamo il fetch periodico.
    # poe.ninja aggiorna i dati ogni ~10-30min, quindi 15min è un buon compromesso.
    fetch_interval_minutes: int = 15

    # -- DB --
    # Path del file SQLite. Override con FAUSTUS_DB_URL se vuoi spostarlo.
    db_url: str = Field(
        default_factory=lambda: f"sqlite:///{DATA_DIR / 'faustus.db'}"
    )

    # -- API server --
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    model_config = SettingsConfigDict(
        env_prefix="FAUSTUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Istanza singleton. Importala ovunque serva configurazione.
settings = Settings()

# Assicura che data/ esista — così non dobbiamo preoccuparci altrove.
DATA_DIR.mkdir(parents=True, exist_ok=True)
