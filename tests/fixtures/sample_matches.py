"""
Sample match data for testing.

Based on actual Riot API response structure.
"""

SAMPLE_MATCH_RESPONSE = {
    "metadata": {
        "matchId": "BR1_123456789",
        "participants": [
            "test-puuid-12345", "puuid-2", "puuid-3", "puuid-4", "puuid-5",
            "puuid-6", "puuid-7", "puuid-8", "puuid-9", "puuid-10"
        ]
    },
    "info": {
        "gameDuration": 1800,  # 30 minutes
        "gameMode": "CLASSIC",
        "queueId": 420,  # Ranked Solo
        "participants": [
            {
                "puuid": "test-puuid-12345",
                "participantId": 1,
                "championName": "Jinx",
                "teamPosition": "BOTTOM",
                "win": True,
                "kills": 8,
                "deaths": 3,
                "assists": 10,
                "totalMinionsKilled": 200,
                "neutralMinionsKilled": 20,
                "visionScore": 25,
                "totalDamageDealtToChampions": 28000,
            },
            {
                "puuid": "puuid-2",
                "participantId": 2,
                "championName": "Thresh",
                "teamPosition": "UTILITY",
                "win": True,
                "kills": 1,
                "deaths": 4,
                "assists": 18,
                "totalMinionsKilled": 30,
                "neutralMinionsKilled": 0,
                "visionScore": 65,
                "totalDamageDealtToChampions": 8000,
            },
            {
                "puuid": "puuid-3",
                "participantId": 3,
                "championName": "Ahri",
                "teamPosition": "MIDDLE",
                "win": True,
                "kills": 10,
                "deaths": 2,
                "assists": 8,
                "totalMinionsKilled": 220,
                "neutralMinionsKilled": 15,
                "visionScore": 20,
                "totalDamageDealtToChampions": 32000,
            },
        ]
    },
    "timeline": {
        "info": {
            "frameInterval": 60000,  # 1 minute
            "frames": [
                {
                    "timestamp": 0,
                    "events": []
                },
                {
                    "timestamp": 300000,  # 5 min
                    "events": [
                        {
                            "type": "CHAMPION_KILL",
                            "timestamp": 300000,
                            "killerId": 2,
                            "victimId": 1,
                            "assistingParticipantIds": []
                        }
                    ]
                },
                {
                    "timestamp": 600000,  # 10 min
                    "events": [
                        {
                            "type": "CHAMPION_KILL",
                            "timestamp": 540000,
                            "killerId": 3,
                            "victimId": 1,
                            "assistingParticipantIds": [2]
                        }
                    ]
                },
                {
                    "timestamp": 900000,  # 15 min
                    "events": [
                        {
                            "type": "CHAMPION_KILL",
                            "timestamp": 850000,
                            "killerId": 1,
                            "victimId": 6,
                            "assistingParticipantIds": [2]
                        }
                    ]
                },
                {
                    "timestamp": 1200000,  # 20 min
                    "events": []
                },
                {
                    "timestamp": 1500000,  # 25 min
                    "events": [
                        {
                            "type": "CHAMPION_KILL",
                            "timestamp": 1450000,
                            "killerId": 6,
                            "victimId": 1,
                            "assistingParticipantIds": [7, 8]
                        }
                    ]
                },
                {
                    "timestamp": 1800000,  # 30 min (end)
                    "events": []
                }
            ]
        }
    }
}


SAMPLE_PLAYER_RESPONSE = {
    "puuid": "test-puuid-12345",
    "gameName": "TestPlayer",
    "tagLine": "TEST"
}


SAMPLE_SUMMONER_RESPONSE = {
    "id": "summoner-id-123",
    "accountId": "account-id-456",
    "puuid": "test-puuid-12345",
    "name": "TestPlayer",
    "profileIconId": 1234,
    "summonerLevel": 150
}


SAMPLE_LEAGUE_RESPONSE = [
    {
        "queueType": "RANKED_SOLO_5x5",
        "tier": "GOLD",
        "rank": "II",
        "leaguePoints": 50,
        "wins": 100,
        "losses": 90
    },
    {
        "queueType": "RANKED_FLEX_SR",
        "tier": "SILVER",
        "rank": "I",
        "leaguePoints": 75,
        "wins": 30,
        "losses": 25
    }
]


SAMPLE_MATCH_IDS = [
    "BR1_123456789",
    "BR1_123456790",
    "BR1_123456791",
    "BR1_123456792",
    "BR1_123456793",
]
