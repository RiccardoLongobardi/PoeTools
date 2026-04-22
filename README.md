# PoeTools

Monorepo di tool per **Path of Exile 1** — market intelligence, build planning e automazione.

Ogni tool vive nel proprio branch dedicato e viene integrato su `master` quando è stabile.

---

## Tool disponibili

| Tool | Branch | Stato | Descrizione |
|------|--------|-------|-------------|
| **Faustus Dashboard** | `feature/faustus-dashboard` | 🔧 In sviluppo | Market intelligence per Currency Exchange: cicli triangolari, spread watchlist, trend storici via poe.ninja |
| **FOB — Frusta Oracle Builder** | `fob-frusta-oracle-builder` | 🔧 In sviluppo | Build planner AI: interpreta richieste in linguaggio naturale (IT/EN), suggerisce build da poe.ninja/Maxroll, genera progressione 1→100 con costi reali |

---

## Stack comune

- **Backend**: Python 3.12 · FastAPI · SQLAlchemy · APScheduler
- **Dati**: poe.ninja API · GGG Trade API · Maxroll · PoE Forum
- **Package manager**: uv

---

## Struttura repo

```
PoeTools/
├── README.md          ← questo file
├── .gitignore
└── (ogni tool aggiunge la propria directory quando mergiato)
```

---

## Setup rapido

Vedi il README del branch specifico del tool che vuoi usare.

---

## Roadmap

- [ ] Faustus Dashboard — UI React + alert desktop
- [ ] FOB Oracle Builder — frontend UI + test coverage
- [ ] Integrazione comune autenticazione / config
- [ ] CI/CD pipeline (GitHub Actions)
