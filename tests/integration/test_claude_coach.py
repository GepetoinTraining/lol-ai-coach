"""
Integration tests for Claude coaching client.

These tests verify error handling and API interaction.
Uses mocks to avoid actual API calls.
"""

import pytest
from unittest.mock import Mock, patch
import anthropic

from src.coach.claude_coach import (
    CoachingClient,
    MatchSummary,
    extract_match_summary,
)
from src.exceptions import ClaudeAPIError


class TestCoachingClientInit:
    """Tests for CoachingClient initialization"""

    def test_requires_api_key(self, monkeypatch):
        """Test that missing API key raises error"""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            CoachingClient()

    def test_uses_env_api_key(self, mock_env_vars):
        """Test API key is read from environment"""
        with patch('anthropic.Anthropic'):
            client = CoachingClient()
            assert client.api_key == "sk-ant-test-anthropic-key-12345"

    def test_accepts_explicit_api_key(self, mock_env_vars):
        """Test explicit API key overrides environment"""
        with patch('anthropic.Anthropic'):
            client = CoachingClient(api_key="sk-ant-explicit-key")
            assert client.api_key == "sk-ant-explicit-key"

    def test_uses_default_model(self, mock_env_vars):
        """Test default model is used when not specified"""
        with patch('anthropic.Anthropic'):
            client = CoachingClient()
            assert "claude" in client.model.lower()

    def test_accepts_custom_model(self, mock_env_vars):
        """Test custom model can be specified"""
        with patch('anthropic.Anthropic'):
            client = CoachingClient(model="claude-3-opus")
            assert client.model == "claude-3-opus"


class TestAnalyzeMatches:
    """Tests for match analysis"""

    @pytest.fixture
    def coach_client(self, mock_env_vars, mock_anthropic_client):
        """Create a CoachingClient with mocked Anthropic client"""
        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_anthropic.return_value = mock_anthropic_client
            client = CoachingClient()
            client.client = mock_anthropic_client
            return client

    def test_returns_analysis_string(self, coach_client, sample_match_summaries):
        """Test successful analysis returns string"""
        result = coach_client.analyze_matches(
            matches=sample_match_summaries,
            player_name="TestPlayer#TEST",
            rank="Gold II"
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_calls_api_with_correct_params(self, coach_client, sample_match_summaries):
        """Test API is called with expected parameters"""
        coach_client.analyze_matches(
            matches=sample_match_summaries,
            player_name="TestPlayer#TEST",
            rank="Gold II"
        )

        coach_client.client.messages.create.assert_called_once()
        call_kwargs = coach_client.client.messages.create.call_args.kwargs

        assert call_kwargs["max_tokens"] == 1500
        assert len(call_kwargs["messages"]) == 1
        assert "TestPlayer" in call_kwargs["messages"][0]["content"]

    def test_handles_empty_matches(self, coach_client):
        """Test handling of empty match list"""
        result = coach_client.analyze_matches(
            matches=[],
            player_name="TestPlayer#TEST",
            rank="Gold II"
        )

        assert isinstance(result, str)
        # Should not call API for empty matches
        coach_client.client.messages.create.assert_not_called()

    def test_handles_rate_limit_error(self, coach_client, sample_match_summaries):
        """Test rate limit error is properly handled"""
        coach_client.client.messages.create.side_effect = anthropic.RateLimitError(
            message="Rate limited",
            response=Mock(status_code=429),
            body={}
        )

        with pytest.raises(ClaudeAPIError) as exc_info:
            coach_client.analyze_matches(
                matches=sample_match_summaries,
                player_name="TestPlayer#TEST"
            )

        assert exc_info.value.status_code == 429

    def test_handles_auth_error(self, coach_client, sample_match_summaries):
        """Test authentication error is properly handled"""
        coach_client.client.messages.create.side_effect = anthropic.AuthenticationError(
            message="Invalid API key",
            response=Mock(status_code=401),
            body={}
        )

        with pytest.raises(ClaudeAPIError) as exc_info:
            coach_client.analyze_matches(
                matches=sample_match_summaries,
                player_name="TestPlayer#TEST"
            )

        assert exc_info.value.status_code == 401

    def test_handles_overloaded_error(self, coach_client, sample_match_summaries):
        """Test overloaded error (529) is properly handled"""
        coach_client.client.messages.create.side_effect = anthropic.APIStatusError(
            message="Overloaded",
            response=Mock(status_code=529),
            body={}
        )

        with pytest.raises(ClaudeAPIError) as exc_info:
            coach_client.analyze_matches(
                matches=sample_match_summaries,
                player_name="TestPlayer#TEST"
            )

        assert "overloaded" in str(exc_info.value).lower()


class TestChat:
    """Tests for chat functionality"""

    @pytest.fixture
    def coach_client(self, mock_env_vars, mock_anthropic_client):
        """Create a CoachingClient with mocked Anthropic client"""
        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_anthropic.return_value = mock_anthropic_client
            client = CoachingClient()
            client.client = mock_anthropic_client
            return client

    def test_returns_response_string(self, coach_client):
        """Test chat returns response string"""
        result = coach_client.chat(
            player_context="Previous analysis context",
            user_message="How can I improve my CSing?"
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_conversation_history(self, coach_client):
        """Test conversation history is included in messages"""
        history = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"}
        ]

        coach_client.chat(
            player_context="Context",
            user_message="Follow-up question",
            conversation_history=history
        )

        call_kwargs = coach_client.client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]

        # Should include: context, assistant ack, history (2), new message
        assert len(messages) >= 5


class TestGenerateExercise:
    """Tests for exercise generation"""

    @pytest.fixture
    def coach_client(self, mock_env_vars, mock_anthropic_client):
        """Create a CoachingClient with mocked Anthropic client"""
        with patch('anthropic.Anthropic') as mock_anthropic:
            mock_anthropic.return_value = mock_anthropic_client
            client = CoachingClient()
            client.client = mock_anthropic_client
            return client

    def test_returns_exercise_string(self, coach_client):
        """Test exercise generation returns string"""
        result = coach_client.generate_exercise(
            weakness="Dying too much in lane",
            rank="Silver II",
            main_champions=["Jinx", "Caitlyn"]
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_weakness_in_prompt(self, coach_client):
        """Test weakness is included in the prompt"""
        coach_client.generate_exercise(
            weakness="Poor wave management",
            rank="Gold I",
            main_champions=["Ahri"]
        )

        call_kwargs = coach_client.client.messages.create.call_args.kwargs
        prompt = call_kwargs["messages"][0]["content"]

        assert "wave management" in prompt.lower()
        assert "Gold I" in prompt
        assert "Ahri" in prompt


class TestMatchSummary:
    """Tests for MatchSummary dataclass"""

    def test_to_dict_basic(self):
        """Test MatchSummary serialization"""
        summary = MatchSummary(
            champion="Jinx",
            role="BOTTOM",
            win=True,
            kills=8,
            deaths=3,
            assists=10,
            cs=220,
            cs_per_min=7.3,
            vision_score=25,
            damage_dealt=28000,
            game_duration_min=30,
            death_times=[450, 900, 1500]
        )
        result = summary.to_dict()

        assert result["champion"] == "Jinx"
        assert result["role"] == "BOTTOM"
        assert result["win"] is True
        assert result["kda"] == "8/3/10"
        assert result["cs"] == 220
        assert result["cs_per_min"] == 7.3

    def test_early_deaths_calculation(self):
        """Test early deaths (before 10min) are correctly calculated"""
        summary = MatchSummary(
            champion="Test",
            role="MID",
            win=True,
            kills=0,
            deaths=5,
            assists=0,
            cs=100,
            cs_per_min=5.0,
            vision_score=10,
            damage_dealt=10000,
            game_duration_min=20,
            death_times=[300, 500, 700, 900, 1200]  # 4 before 600s (10min)
        )

        result = summary.to_dict()
        assert result["early_deaths"] == 4

    def test_no_early_deaths(self):
        """Test when all deaths are after 10 minutes"""
        summary = MatchSummary(
            champion="Test",
            role="TOP",
            win=False,
            kills=5,
            deaths=3,
            assists=2,
            cs=150,
            cs_per_min=6.0,
            vision_score=15,
            damage_dealt=18000,
            game_duration_min=25,
            death_times=[700, 1000, 1400]  # All after 600s
        )

        result = summary.to_dict()
        assert result["early_deaths"] == 0


class TestExtractMatchSummary:
    """Tests for extract_match_summary function"""

    def test_extracts_correct_data(self, sample_match_data):
        """Test match data is correctly extracted"""
        puuid = "test-puuid-12345"

        result = extract_match_summary(sample_match_data, puuid)

        assert isinstance(result, MatchSummary)
        assert result.champion == "Jinx"
        assert result.role == "BOTTOM"
        assert result.win is True
        assert result.kills == 8
        assert result.deaths == 3
        assert result.assists == 10

    def test_calculates_cs_correctly(self, sample_match_data):
        """Test CS is sum of minions and monsters"""
        puuid = "test-puuid-12345"

        result = extract_match_summary(sample_match_data, puuid)

        # 200 minions + 20 neutral = 220
        assert result.cs == 220

    def test_calculates_cs_per_min(self, sample_match_data):
        """Test CS per minute calculation"""
        puuid = "test-puuid-12345"

        result = extract_match_summary(sample_match_data, puuid)

        # 220 CS / 30 minutes = 7.33
        assert 7.0 < result.cs_per_min < 7.5

    def test_extracts_death_times_from_timeline(self, sample_match_data):
        """Test death times are extracted from timeline"""
        puuid = "test-puuid-12345"

        result = extract_match_summary(sample_match_data, puuid)

        # Timeline has deaths at 300s, 540s, 1450s for participant 1
        assert len(result.death_times) > 0

    def test_raises_for_missing_player(self, sample_match_data):
        """Test error when player not in match"""
        with pytest.raises(ValueError, match="Player not found"):
            extract_match_summary(sample_match_data, "nonexistent-puuid")

    def test_handles_missing_timeline(self):
        """Test handling match data without timeline"""
        match_data = {
            "info": {
                "gameDuration": 1800,
                "participants": [
                    {
                        "puuid": "test-puuid",
                        "participantId": 1,
                        "championName": "Ahri",
                        "teamPosition": "MIDDLE",
                        "win": True,
                        "kills": 5,
                        "deaths": 2,
                        "assists": 8,
                        "totalMinionsKilled": 200,
                        "visionScore": 20,
                        "totalDamageDealtToChampions": 25000,
                    }
                ]
            }
            # No timeline key
        }

        result = extract_match_summary(match_data, "test-puuid")

        assert result.champion == "Ahri"
        assert result.death_times == []  # Empty when no timeline
