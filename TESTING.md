# 🧪 Testing FOB - Frusta Oracle Builder

Documentazione completa per testare il sistema FOB Oracle.

## 📋 Test Suite Overview

Il file `tests/test_fob_oracle.py` contiene **13 test** distribuiti in 4 categorie:

### 1. ✅ TestIntentTagger (5 test)
Test dell'estrazione tag da query in linguaggio naturale.

```python
# Test query italiane
test_italian_ice_query()          # "voglio ghiacciare tutto" → cold

# Test query inglesi
test_english_fire_query()         # "I want fire damage" → fire

# Test query complesse
test_slam_hammer_query()          # "martellone slam forte" → mace, melee
test_dot_chaos_query()            # "damage over time chaos" → dot, chaos

# Test estrazione budget
test_budget_extraction()          # "20 divine" → budget_div=20.0
```

**Verifica**: L'IntentTagger riconosce correttamente keyword IT/EN e mappa su tags strutturati.

---

### 2. ⚖️ TestScoringSystem (3 test)
Test del sistema di punteggio per ranking delle build.

```python
test_perfect_match()    # Tutti i tag corrispondono → score alto (≥7)
test_partial_match()    # Match parziale → score medio (≥2)
test_no_match()         # Nessun tag corrisponde → score=0
```

**Sistema di scoring:**
- Element match: **+2 punti**
- Damage type match: **+2 punti**
- Ascendancy match: **+3 punti**
- Weapon pref match: **+1 punto**
- Playstyle match: **+1 punto**
- Budget proximity (<10 div): **+1 punto**

---

### 3. 📦 TestFallbackBuilds (3 test)
Test del catalogo fallback (quando poe.ninja non è disponibile).

```python
test_fallback_catalog_exists()     # Verifica esistenza di 5 build
test_fallback_build_structure()    # Verifica struttura (ID, nome, source, ascendancy)
test_ice_nova_in_fallback()        # Verifica presenza build ice/cold
```

**Build fallback disponibili:**
1. Ice Nova Occultist (cold, spell)
2. Righteous Fire Juggernaut (fire, dot)
3. Lightning Strike Raider (lightning, attack)
4. Earthquake Juggernaut (physical, slam)
5. Toxic Rain Pathfinder (chaos, dot)

---

### 4. 🔄 TestFullOracleFlow (2 test)
Test dell'orchestrazione completa.

```python
test_oracle_query_structure()     # Verifica run_oracle sia callable
test_build_query_construction()   # Verifica costruzione BuildQuery da tags
```

---

## 🚀 Come Eseguire i Test

### Opzione 1: Pytest (Raccomandato)

```bash
# Installa dipendenze
uv sync

# Esegui tutti i test
pytest tests/test_fob_oracle.py -v

# Esegui una singola classe di test
pytest tests/test_fob_oracle.py::TestIntentTagger -v

# Esegui un singolo test
pytest tests/test_fob_oracle.py::TestIntentTagger::test_italian_ice_query -v

# Con output dettagliato
pytest tests/test_fob_oracle.py -v -s
```

### Opzione 2: Esecuzione Diretta

```bash
# Esegui il file direttamente
python tests/test_fob_oracle.py
```

Output atteso:
```
============================================================
🧪 FOB Oracle Test Suite
============================================================

📍 Testing Intent Tagger...
✅ IT Ice query → tags.element=['cold']
✅ EN Fire query → tags.element=['fire']
✅ Slam query → weapon=['mace'], style=['melee']
✅ DoT Chaos → damage_type=['dot'], element=['chaos']
✅ Budget extraction → budget_div=20.0

📍 Testing Scoring System...
✅ Perfect match → score=7
✅ Partial match → score=2
✅ No match → score=0

📍 Testing Fallback Builds...
✅ Fallback catalog → 5 builds
✅ Fallback builds structure valid
✅ Ice builds in fallback → 1 found

📍 Testing Full Oracle Flow...
✅ run_oracle function is callable
✅ BuildQuery constructed → element=['cold'], budget=30.0

============================================================
✅ All tests completed!
============================================================
```

---

## 🔍 Test Manuali dell'API

Per testare l'endpoint API completo:

### 1. Avvia il server

```bash
# Dalla root del progetto
uv run fob
```

Il server sarà disponibile su `http://localhost:8000`

### 2. Test con curl

```bash
# Test query italiana - ghiaccio
curl -X POST http://localhost:8000/fob/oracle \
  -H "Content-Type: application/json" \
  -d '{
    "query": "voglio una build che ghiacci tutto",
    "league": "Settlers"
  }'

# Test query inglese - fire damage
curl -X POST http://localhost:8000/fob/oracle \
  -H "Content-Type: application/json" \
  -d '{
    "query": "I want a fire damage over time build",
    "league": "Settlers"
  }'

# Test con budget specifico
curl -X POST http://localhost:8000/fob/oracle \
  -H "Content-Type: application/json" \
  -d '{
    "query": "lightning strike raider budget 30 divine",
    "league": "Settlers"
  }'
```

### 3. Risposta Attesa

```json
{
  "intent": {
    "damage_type": ["spell"],
    "style": [],
    "budget": "any",
    "playstyle": [],
    "raw_tokens": "voglio una build che ghiacci tutto"
  },
  "builds": [
    {
      "id": "ice_nova_occultist",
      "name": "Ice Nova Occultist",
      "source": "fallback",
      "url": null,
      "pob_output": null,
      "ascendancy": "Occultist",
      "main_skill": "Ice Nova",
      "element": ["cold"],
      "damage_type": ["spell", "cold"],
      "weapon_pref": [],
      "playstyle": ["aoe", "mapping"],
      "est_cost_div": 20.0,
      "league": null,
      "score": 7.0
    }
  ],
  "plan": null,
  "warning": null
}
```

---

## ✅ Checklist Test Completi

### Funzionalità Base
- [x] Intent Tagging (IT/EN)
- [x] Build Query Construction
- [x] Scoring System
- [x] Fallback Builds Catalog
- [x] Full Oracle Orchestration

### Casi d'Uso Reali
- [ ] Test con poe.ninja reale (richiede connessione internet)
- [ ] Test con PoB import reale
- [ ] Test plan progression completo
- [ ] Test pricing con PoE Trade API

### Edge Cases
- [ ] Query vuota
- [ ] Query con solo stopwords
- [ ] Budget negativo o zero
- [ ] League inesistente

---

## 🐛 Debugging

Se i test falliscono:

### 1. Verifica dipendenze

```bash
uv sync
python -c "from backend.services.fob_oracle import run_oracle; print('OK')"
```

### 2. Controlla log

```bash
# Con logging attivo
LOGLEVEL=DEBUG pytest tests/test_fob_oracle.py -v -s
```

### 3. Test singolo modulo

```python
# Test manuale dell'Intent Tagger
from backend.services.intent import IntentTagger

tagger = IntentTagger()
tags = tagger.tag("voglio ghiacciare tutto")
print(f"Tags estratti: {tags}")
print(f"Element: {tags.element}")
print(f"Damage type: {tags.damage_type}")
```

---

## 📊 Coverage Report

Per generare report di coverage:

```bash
# Installa pytest-cov
uv add --dev pytest-cov

# Genera report
pytest tests/test_fob_oracle.py --cov=backend.services.fob_oracle --cov-report=html

# Apri report
open htmlcov/index.html  # Mac/Linux
start htmlcov/index.html # Windows
```

---

## 🎯 Prossimi Passi

1. **Integrare CI/CD**: Automatizzare i test su GitHub Actions
2. **Test E2E**: Aggiungere test end-to-end con server reale
3. **Performance Tests**: Misurare latenza dell'oracle con grandi query
4. **Load Testing**: Verificare comportamento sotto carico
5. **Integration Tests**: Testare integrazione con poe.ninja e PoE Trade API

---

## 📚 Riferimenti

- **Test File**: `tests/test_fob_oracle.py`
- **Main Module**: `backend/services/fob_oracle.py`
- **Intent Tagger**: `backend/services/intent.py`
- **API Routes**: `backend/api/routes.py`
- **Dependencies**: `pyproject.toml`
