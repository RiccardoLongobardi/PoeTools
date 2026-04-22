"""Test suite per FOB - Frusta Oracle Builder."""
import pytest
from backend.services.intent import IntentTagger
from backend.services.fob_oracle import (
    BuildQuery,
    Build,
    BuildCandidate,
    _tag_match_score,
    _fallback_builds,
)


class TestIntentTagger:
    """Test dell'Intent Tagger per estrazione tag da query NL."""

    def test_italian_ice_query(self):
        """Test query italiana: 'voglio ghiacciare tutto'."""
        tagger = IntentTagger()
        tags = tagger.tag("voglio ghiacciare tutto")
        
        assert "cold" in tags.element, "Dovrebbe estrarre 'cold' da 'ghiacciare'"
        print(f"✅ IT Ice query → tags.element={tags.element}")

    def test_english_fire_query(self):
        """Test query inglese: 'I want fire damage'."""
        tagger = IntentTagger()
        tags = tagger.tag("I want fire damage")
        
        assert "fire" in tags.element, "Dovrebbe estrarre 'fire'"
        print(f"✅ EN Fire query → tags.element={tags.element}")

    def test_slam_hammer_query(self):
        """Test query: 'martellone slam forte'."""
        tagger = IntentTagger()
        tags = tagger.tag("martellone slam forte")
        
        assert "mace" in tags.weapon_pref or "2h" in tags.weapon_pref
        assert "melee" in tags.playstyle or "slam" in tags.damage_type
        print(f"✅ Slam query → weapon={tags.weapon_pref}, style={tags.playstyle}")

    def test_dot_chaos_query(self):
        """Test query: 'damage over time chaos'."""
        tagger = IntentTagger()
        tags = tagger.tag("damage over time chaos")
        
        assert "dot" in tags.damage_type or "chaos" in tags.element
        print(f"✅ DoT Chaos → damage_type={tags.damage_type}, element={tags.element}")

    def test_budget_extraction(self):
        """Test estrazione budget: '20 divine'."""
        tagger = IntentTagger()
        tags = tagger.tag("build con budget 20 divine")
        
        assert tags.budget_div is not None
        assert 15 <= tags.budget_div <= 25  # range ragionevole
        print(f"✅ Budget extraction → budget_div={tags.budget_div}")


class TestScoringSystem:
    """Test del sistema di scoring delle build."""

    def test_perfect_match(self):
        """Test match perfetto: tutti i tag corrispondono."""
        query = BuildQuery(
            description="cold spell occultist",
            league="Settlers",
            element=["cold"],
            damage_type=["spell"],
            ascendancy=["Occultist"],
        )
        
        build = Build(
            id="test_cold",
            name="Cold Spell Build",
            source="test",
            element=["cold"],
            damage_type=["spell"],
            ascendancy="Occultist",
        )
        
        score = _tag_match_score(build, query)
        assert score >= 7, f"Match perfetto dovrebbe dare score alto, got {score}"
        print(f"✅ Perfect match → score={score}")

    def test_partial_match(self):
        """Test match parziale: solo alcuni tag corrispondono."""
        query = BuildQuery(
            description="fire melee",
            league="Settlers",
            element=["fire"],
            playstyle=["melee"],
        )
        
        build = Build(
            id="test_fire",
            name="Fire Ranged Build",
            source="test",
            element=["fire"],  # match
            playstyle=["ranged"],  # no match
        )
        
        score = _tag_match_score(build, query)
        assert score >= 2, f"Match parziale dovrebbe dare score > 0, got {score}"
        print(f"✅ Partial match → score={score}")

    def test_no_match(self):
        """Test nessun match: tag completamente diversi."""
        query = BuildQuery(
            description="lightning spell",
            league="Settlers",
            element=["lightning"],
            damage_type=["spell"],
        )
        
        build = Build(
            id="test_phys",
            name="Physical Attack Build",
            source="test",
            element=["physical"],
            damage_type=["attack"],
        )
        
        score = _tag_match_score(build, query)
        assert score == 0, f"No match dovrebbe dare score=0, got {score}"
        print(f"✅ No match → score={score}")


class TestFallbackBuilds:
    """Test del catalogo fallback builds."""

    def test_fallback_catalog_exists(self):
        """Verifica che esistano build di fallback."""
        query = BuildQuery(
            description="any build",
            league="Settlers",
        )
        
        builds = _fallback_builds(query)
        
        assert len(builds) > 0, "Dovrebbero esserci build di fallback"
        assert len(builds) == 5, f"Dovrebbero esserci 5 build fallback, trovate {len(builds)}"
        print(f"✅ Fallback catalog → {len(builds)} builds")

    def test_fallback_build_structure(self):
        """Verifica struttura delle build fallback."""
        query = BuildQuery(description="test", league="Settlers")
        builds = _fallback_builds(query)
        
        for build in builds:
            assert build.id, "Build deve avere ID"
            assert build.name, "Build deve avere nome"
            assert build.source == "fallback", "Source deve essere 'fallback'"
            assert build.ascendancy, "Build deve avere ascendancy"
        
        print(f"✅ Fallback builds structure valid")

    def test_ice_nova_in_fallback(self):
        """Verifica presenza Ice Nova Occultist nel fallback."""
        query = BuildQuery(description="test", league="Settlers")
        builds = _fallback_builds(query)
        
        ice_builds = [b for b in builds if "ice" in b.name.lower() or "cold" in b.element]
        assert len(ice_builds) > 0, "Dovrebbe esserci almeno una build ice/cold"
        print(f"✅ Ice builds in fallback → {len(ice_builds)} found")


class TestFullOracleFlow:
    """Test dell'orchestrazione completa (mock)."""

    @pytest.mark.asyncio
    async def test_oracle_query_structure(self):
        """Test struttura risposta oracle (senza chiamata reale)."""
        # Questo test verifica solo che le funzioni siano importabili
        # e che la struttura sia corretta
        from backend.services.fob_oracle import run_oracle
        
        # Verifica che run_oracle sia async e callable
        assert callable(run_oracle), "run_oracle deve essere callable"
        print("✅ run_oracle function is callable")

    def test_build_query_construction(self):
        """Test costruzione BuildQuery da tags."""
        tagger = IntentTagger()
        tags = tagger.tag("voglio una build con ghiaccio budget 30 divine")
        
        bq = BuildQuery(
            description="voglio una build con ghiaccio budget 30 divine",
            league="Settlers",
            element=tags.element,
            damage_type=tags.damage_type,
            weapon_pref=tags.weapon_pref,
            playstyle=tags.playstyle,
            ascendancy=tags.ascendancy,
            budget_div=tags.budget_div,
        )
        
        assert bq.description, "BuildQuery deve avere description"
        assert bq.league, "BuildQuery deve avere league"
        assert "cold" in bq.element, "Dovrebbe contenere 'cold'"
        if bq.budget_div:
            assert 25 <= bq.budget_div <= 35, f"Budget dovrebbe essere ~30, got {bq.budget_div}"
        
        print(f"✅ BuildQuery constructed → element={bq.element}, budget={bq.budget_div}")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 FOB Oracle Test Suite")
    print("="*60 + "\n")
    
    # Run tests manually
    import asyncio
    
    # Intent Tagger Tests
    print("\n📍 Testing Intent Tagger...")
    intent_tests = TestIntentTagger()
    intent_tests.test_italian_ice_query()
    intent_tests.test_english_fire_query()
    intent_tests.test_slam_hammer_query()
    intent_tests.test_dot_chaos_query()
    intent_tests.test_budget_extraction()
    
    # Scoring System Tests
    print("\n📍 Testing Scoring System...")
    scoring_tests = TestScoringSystem()
    scoring_tests.test_perfect_match()
    scoring_tests.test_partial_match()
    scoring_tests.test_no_match()
    
    # Fallback Builds Tests
    print("\n📍 Testing Fallback Builds...")
    fallback_tests = TestFallbackBuilds()
    fallback_tests.test_fallback_catalog_exists()
    fallback_tests.test_fallback_build_structure()
    fallback_tests.test_ice_nova_in_fallback()
    
    # Full Oracle Flow Tests
    print("\n📍 Testing Full Oracle Flow...")
    oracle_tests = TestFullOracleFlow()
    asyncio.run(oracle_tests.test_oracle_query_structure())
    oracle_tests.test_build_query_construction()
    
    print("\n" + "="*60)
    print("✅ All tests completed!")
    print("="*60 + "\n")
