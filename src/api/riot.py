"""
Riot Games API Client

Handles all communication with Riot's API including:
- Account lookup by Riot ID
- Summoner data
- Match history
- Match details and timeline
- Rate limiting
"""

import os
import asyncio
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# Regional routing
ACCOUNT_ROUTING = {
    "na1": "americas",
    "br1": "americas", 
    "la1": "americas",
    "la2": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
    "oc1": "sea",
    "ph2": "sea",
    "sg2": "sea",
    "th2": "sea",
    "tw2": "sea",
    "vn2": "sea",
}

@dataclass
class RateLimiter:
    """Simple rate limiter for Riot API"""
    requests_per_second: int = 20
    requests_per_two_minutes: int = 100
    
    _second_requests: list = None
    _two_min_requests: list = None
    
    def __post_init__(self):
        self._second_requests = []
        self._two_min_requests = []
    
    async def acquire(self):
        """Wait until we can make a request"""
        now = datetime.now()
        
        # Clean old requests
        self._second_requests = [t for t in self._second_requests if now - t < timedelta(seconds=1)]
        self._two_min_requests = [t for t in self._two_min_requests if now - t < timedelta(minutes=2)]
        
        # Check limits
        while len(self._second_requests) >= self.requests_per_second:
            await asyncio.sleep(0.1)
            now = datetime.now()
            self._second_requests = [t for t in self._second_requests if now - t < timedelta(seconds=1)]
        
        while len(self._two_min_requests) >= self.requests_per_two_minutes:
            await asyncio.sleep(1)
            now = datetime.now()
            self._two_min_requests = [t for t in self._two_min_requests if now - t < timedelta(minutes=2)]
        
        # Record this request
        self._second_requests.append(now)
        self._two_min_requests.append(now)


class RiotAPIError(Exception):
    """Custom exception for Riot API errors"""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Riot API Error {status_code}: {message}")


class RiotAPI:
    """
    Riot Games API Client
    
    Usage:
        api = RiotAPI()
        account = await api.get_account_by_riot_id("PlayerName", "TAG")
        matches = await api.get_match_history(account["puuid"])
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("RIOT_API_KEY")
        if not self.api_key:
            raise ValueError("RIOT_API_KEY is required")
        
        self.rate_limiter = RateLimiter()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"X-Riot-Token": self.api_key},
                timeout=30.0
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _request(self, url: str) -> dict:
        """Make a rate-limited request to Riot API"""
        await self.rate_limiter.acquire()
        
        client = await self._get_client()
        response = await client.get(url)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            # Rate limited - get retry time from headers
            retry_after = int(response.headers.get("Retry-After", 10))
            await asyncio.sleep(retry_after)
            raise RiotAPIError(429, f"Rate limited, retry after {retry_after}s")
        elif response.status_code == 404:
            raise RiotAPIError(404, "Not found")
        else:
            raise RiotAPIError(response.status_code, response.text)
    
    def _get_regional_url(self, platform: str) -> str:
        """Get the regional routing URL for a platform"""
        region = ACCOUNT_ROUTING.get(platform.lower(), "americas")
        return f"https://{region}.api.riotgames.com"
    
    def _get_platform_url(self, platform: str) -> str:
        """Get the platform-specific URL"""
        return f"https://{platform.lower()}.api.riotgames.com"
    
    # ==================== Account Endpoints ====================
    
    async def get_account_by_riot_id(self, game_name: str, tag_line: str, region: str = "americas") -> dict:
        """
        Get account by Riot ID (name#tag)
        
        Args:
            game_name: The player's name
            tag_line: The tag after the #
            region: Regional routing (americas, europe, asia, sea)
        
        Returns:
            {"puuid": "...", "gameName": "...", "tagLine": "..."}
        """
        url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        return await self._request(url)
    
    # ==================== Summoner Endpoints ====================
    
    async def get_summoner_by_puuid(self, puuid: str, platform: str = "na1") -> dict:
        """
        Get summoner info by PUUID
        
        Returns:
            {"id": "...", "accountId": "...", "puuid": "...", "name": "...", 
             "profileIconId": ..., "summonerLevel": ...}
        """
        url = f"{self._get_platform_url(platform)}/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return await self._request(url)
    
    # ==================== Match Endpoints ====================
    
    async def get_match_history(
        self, 
        puuid: str, 
        region: str = "americas",
        start: int = 0,
        count: int = 20,
        queue: Optional[int] = None,
        match_type: Optional[str] = None
    ) -> list[str]:
        """
        Get list of match IDs for a player
        
        Args:
            puuid: Player's PUUID
            region: Regional routing
            start: Start index
            count: Number of matches (max 100)
            queue: Queue ID filter (420=ranked solo, 440=ranked flex)
            match_type: Match type filter (ranked, normal, tourney, tutorial)
        
        Returns:
            List of match IDs
        """
        params = [f"start={start}", f"count={count}"]
        if queue:
            params.append(f"queue={queue}")
        if match_type:
            params.append(f"type={match_type}")
        
        query = "&".join(params)
        url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?{query}"
        return await self._request(url)
    
    async def get_match(self, match_id: str, region: str = "americas") -> dict:
        """
        Get detailed match data
        
        Returns ~3000 lines of JSON including:
        - metadata: match ID, participants
        - info: game mode, duration, teams, participants with full stats
        """
        url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        return await self._request(url)
    
    async def get_match_timeline(self, match_id: str, region: str = "americas") -> dict:
        """
        Get match timeline with minute-by-minute events
        
        Returns events like:
        - CHAMPION_KILL
        - WARD_PLACED
        - ITEM_PURCHASED
        - LEVEL_UP
        - SKILL_LEVEL_UP
        - etc.
        """
        url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        return await self._request(url)
    
    # ==================== League Endpoints ====================
    
    async def get_league_entries(self, summoner_id: str, platform: str = "na1") -> list[dict]:
        """
        Get ranked info for a summoner
        
        Returns list of queue entries with:
        - queueType: RANKED_SOLO_5x5, RANKED_FLEX_SR
        - tier: IRON, BRONZE, ... CHALLENGER
        - rank: IV, III, II, I
        - leaguePoints: 0-100
        - wins, losses
        """
        url = f"{self._get_platform_url(platform)}/lol/league/v4/entries/by-summoner/{summoner_id}"
        return await self._request(url)
    
    # ==================== Convenience Methods ====================
    
    async def get_player_full_info(self, game_name: str, tag_line: str, platform: str = "na1") -> dict:
        """
        Get complete player info in one call
        
        Returns:
            {
                "account": {...},
                "summoner": {...},
                "league": [...]
            }
        """
        region = ACCOUNT_ROUTING.get(platform.lower(), "americas")
        
        account = await self.get_account_by_riot_id(game_name, tag_line, region)
        summoner = await self.get_summoner_by_puuid(account["puuid"], platform)
        league = await self.get_league_entries(summoner["id"], platform)
        
        return {
            "account": account,
            "summoner": summoner,
            "league": league
        }
    
    async def get_recent_matches_with_details(
        self, 
        puuid: str, 
        region: str = "americas",
        count: int = 20,
        include_timeline: bool = False
    ) -> list[dict]:
        """
        Get recent matches with full details
        
        Args:
            puuid: Player's PUUID
            region: Regional routing
            count: Number of matches
            include_timeline: Whether to fetch timeline data (slower)
        
        Returns:
            List of match data dicts
        """
        match_ids = await self.get_match_history(puuid, region, count=count)
        
        matches = []
        for match_id in match_ids:
            match_data = await self.get_match(match_id, region)
            
            if include_timeline:
                timeline = await self.get_match_timeline(match_id, region)
                match_data["timeline"] = timeline
            
            matches.append(match_data)
        
        return matches


# ==================== CLI for testing ====================

async def main():
    """Test the API client"""
    import sys
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    if len(sys.argv) < 2:
        console.print("[red]Usage: python riot.py 'GameName#TAG'[/red]")
        return
    
    # Parse Riot ID
    riot_id = sys.argv[1]
    if "#" not in riot_id:
        console.print("[red]Invalid format. Use 'GameName#TAG'[/red]")
        return
    
    game_name, tag_line = riot_id.rsplit("#", 1)
    
    console.print(f"\n[bold]Looking up {game_name}#{tag_line}...[/bold]\n")
    
    api = RiotAPI()
    
    try:
        # Get player info
        player = await api.get_player_full_info(game_name, tag_line, "br1")
        
        console.print(f"[green]✓[/green] Found player: {player['account']['gameName']}#{player['account']['tagLine']}")
        console.print(f"  Level: {player['summoner']['summonerLevel']}")
        
        # Show rank
        if player['league']:
            for entry in player['league']:
                if entry['queueType'] == 'RANKED_SOLO_5x5':
                    console.print(f"  Rank: {entry['tier']} {entry['rank']} ({entry['leaguePoints']} LP)")
                    console.print(f"  W/L: {entry['wins']}/{entry['losses']}")
        
        # Get recent matches
        console.print("\n[bold]Fetching recent matches...[/bold]")
        
        region = ACCOUNT_ROUTING.get("br1", "americas")
        matches = await api.get_recent_matches_with_details(
            player['account']['puuid'], 
            region,
            count=5
        )
        
        # Create match table
        table = Table(title="Recent Matches")
        table.add_column("Champion", style="cyan")
        table.add_column("K/D/A", style="green")
        table.add_column("CS", style="yellow")
        table.add_column("Result", style="bold")
        table.add_column("Duration")
        
        puuid = player['account']['puuid']
        
        for match in matches:
            info = match['info']
            
            # Find this player's data
            participant = None
            for p in info['participants']:
                if p['puuid'] == puuid:
                    participant = p
                    break
            
            if participant:
                kda = f"{participant['kills']}/{participant['deaths']}/{participant['assists']}"
                cs = participant['totalMinionsKilled'] + participant.get('neutralMinionsKilled', 0)
                result = "[green]WIN[/green]" if participant['win'] else "[red]LOSS[/red]"
                duration = f"{info['gameDuration'] // 60}:{info['gameDuration'] % 60:02d}"
                
                table.add_row(
                    participant['championName'],
                    kda,
                    str(cs),
                    result,
                    duration
                )
        
        console.print(table)
        
    except RiotAPIError as e:
        console.print(f"[red]API Error: {e.message}[/red]")
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
