# LoL AI Coach - Agent Instructions

## Project Overview

Build an AI-powered coaching system for League of Legends that analyzes player match history and provides personalized improvement recommendations. This is NOT another stats tracker - it's a conversational AI coach that understands your specific weaknesses and creates actionable improvement plans.

## Core Philosophy

This project applies the "AI Companion" model from educational contexts to competitive gaming:
- The AI develops contextual understanding of the player over time
- Coaching is personalized, not generic advice
- Focus on pattern recognition across matches, not single-game stats
- Conversational interface, not dashboards

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        LOL AI COACH                             │
│                                                                 │
│  ┌──────────────────┐     ┌──────────────────┐                 │
│  │   Data Layer     │     │   Knowledge Base │                 │
│  │                  │     │                  │                 │
│  │  - Riot API      │     │  - Coaching docs │                 │
│  │  - Match history │     │  - Wave mgmt     │                 │
│  │  - Timeline data │     │  - Trading       │                 │
│  │  - Player stats  │     │  - Macro guides  │                 │
│  └────────┬─────────┘     └────────┬─────────┘                 │
│           │                        │                           │
│           ▼                        ▼                           │
│  ┌─────────────────────────────────────────────┐               │
│  │            Analysis Engine                   │               │
│  │                                              │               │
│  │  - Pattern detection across matches          │               │
│  │  - Weakness identification                   │               │
│  │  - Progress tracking                         │               │
│  │  - Benchmark comparison                      │               │
│  └──────────────────┬──────────────────────────┘               │
│                     │                                          │
│                     ▼                                          │
│  ┌─────────────────────────────────────────────┐               │
│  │            AI Coach (Claude API)             │               │
│  │                                              │               │
│  │  - Conversational interface                  │               │
│  │  - Personalized recommendations              │               │
│  │  - Exercise generation                       │               │
│  │  - Progress celebration                      │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

### Backend
- **Runtime**: Node.js 20+ or Python 3.11+
- **Framework**: FastAPI (Python) or Hono (Node.js)
- **Database**: SQLite for local dev, PostgreSQL for production
- **Cache**: Redis for rate limit management and session data

### APIs
- **Riot Games API**: Match data, player info, timelines
  - Docs: https://developer.riotgames.com/
  - Rate limits: 20/sec, 100/2min (dev key)
- **Anthropic Claude API**: AI coaching conversations
  - Model: claude-sonnet-4-20250514 for analysis
  - Use structured outputs for data extraction

### Frontend (Phase 2)
- **Framework**: React + Vite
- **Styling**: Tailwind CSS
- **State**: Zustand or React Query

### Optional (Phase 3)
- **Overwolf SDK**: Real-time in-game overlay
  - Docs: https://dev.overwolf.com/

## Project Structure

```
lol-ai-coach/
├── AGENT.md                 # This file
├── README.md                # User-facing docs
├── .env.example             # Environment template
│
├── src/
│   ├── api/
│   │   ├── riot.py          # Riot API client
│   │   ├── claude.py        # Claude API client
│   │   └── routes.py        # HTTP endpoints
│   │
│   ├── analysis/
│   │   ├── patterns.py      # Pattern detection
│   │   ├── metrics.py       # Stat calculations
│   │   └── benchmarks.py    # Rank comparisons
│   │
│   ├── coach/
│   │   ├── prompts.py       # System prompts
│   │   ├── memory.py        # Player context
│   │   └── exercises.py     # Practice drills
│   │
│   ├── models/
│   │   ├── player.py        # Player data model
│   │   ├── match.py         # Match data model
│   │   └── session.py       # Coaching session
│   │
│   └── db/
│       ├── schema.sql       # Database schema
│       └── queries.py       # Database operations
│
├── knowledge/               # RAG knowledge base
│   ├── fundamentals/
│   │   ├── wave_management.md
│   │   ├── trading.md
│   │   ├── vision.md
│   │   └── csing.md
│   │
│   ├── macro/
│   │   ├── rotations.md
│   │   ├── objectives.md
│   │   └── win_conditions.md
│   │
│   └── mental/
│       ├── tilt.md
│       ├── vod_review.md
│       └── practice.md
│
├── tests/
│   ├── test_riot_api.py
│   ├── test_analysis.py
│   └── test_coach.py
│
└── scripts/
    ├── fetch_matches.py     # CLI to fetch player data
    ├── analyze_player.py    # CLI to run analysis
    └── seed_knowledge.py    # Populate knowledge base
```

## Implementation Phases

### Phase 1: Core Data Pipeline (MVP)
1. Riot API client with rate limiting
2. Match data fetching and storage
3. Basic pattern detection (deaths before 10min, CS/min, vision score)
4. Simple Claude integration for conversational output

**Deliverable**: CLI tool that takes summoner name and outputs coaching analysis

### Phase 2: Intelligent Analysis
1. Timeline parsing for detailed event analysis
2. Lane phase metrics (trading patterns, recall timing)
3. Macro metrics (objective participation, rotation timing)
4. Cross-match pattern recognition
5. Rank-appropriate benchmarks

**Deliverable**: Detailed weakness identification with specific timestamps

### Phase 3: RAG-Enhanced Coaching
1. Knowledge base with coaching documents
2. Context-aware recommendations
3. Exercise generation based on weaknesses
4. Progress tracking across sessions

**Deliverable**: Full coaching experience with actionable drills

### Phase 4: Web Interface
1. React frontend with authentication
2. Player profile and history
3. Interactive coaching chat
4. Progress dashboard

### Phase 5: Real-Time (Optional)
1. Overwolf integration
2. Live game overlay
3. Post-game auto-analysis

## Riot API Integration Details

### Required Endpoints

```python
# 1. Get account by Riot ID
GET https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}
# Returns: puuid

# 2. Get summoner by PUUID
GET https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}
# Returns: summoner info

# 3. Get match history
GET https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids
# Params: start, count, queue, type
# Returns: list of match IDs

# 4. Get match details
GET https://{region}.api.riotgames.com/lol/match/v5/matches/{matchId}
# Returns: ~3000 lines of match data

# 5. Get match timeline
GET https://{region}.api.riotgames.com/lol/match/v5/matches/{matchId}/timeline
# Returns: minute-by-minute events
```

### Regional Routing

```python
ACCOUNT_REGIONS = {
    "americas": ["na1", "br1", "la1", "la2"],
    "europe": ["euw1", "eun1", "tr1", "ru"],
    "asia": ["kr", "jp1"],
    "sea": ["oc1", "ph2", "sg2", "th2", "tw2", "vn2"]
}

PLATFORM_ROUTING = {
    "na1": "americas",
    "br1": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "kr": "asia",
    # ... etc
}
```

### Rate Limit Handling

```python
# Development API Key limits
RATE_LIMITS = {
    "requests_per_second": 20,
    "requests_per_two_minutes": 100
}

# Implement exponential backoff on 429
# Check X-Rate-Limit-Type header for limit type
# X-App-Rate-Limit: application rate limit
# X-Method-Rate-Limit: method rate limit
```

## Key Metrics to Extract

### Laning Phase (0-14 min)
- CS at 10 min (benchmark: 80 for good, 100 for excellent)
- Deaths before 10 min
- First blood involvement
- CS differential at 10 min
- XP differential at 10 min
- Trading patterns (damage given vs taken)
- Ward placement timing and locations

### Mid Game (14-25 min)
- Objective participation rate
- CS/min maintenance
- Roaming patterns
- Vision score growth
- Death locations (caught out vs teamfight)

### Late Game (25+ min)
- Teamfight positioning
- Objective focus (Baron, Elder)
- Death timing (before vs after objectives)
- Item completion timing

### Cross-Match Patterns
- Consistent early deaths = laning weakness
- Low vision score = map awareness issue
- CS dropoff = macro priority problem
- Same death locations = positional habits

## Claude Coaching Prompts

### System Prompt Template

```
You are an expert League of Legends coach analyzing a player's recent matches. 
Your role is to:

1. Identify specific, actionable weaknesses (not generic advice)
2. Connect weaknesses to concrete examples from their matches
3. Provide exercises to address each weakness
4. Celebrate improvements when you see them
5. Adapt advice to their rank and champion pool

Current player context:
- Summoner: {summoner_name}
- Rank: {rank}
- Main roles: {roles}
- Main champions: {champions}
- Matches analyzed: {match_count}

Analysis data:
{analysis_json}

Respond conversationally, as a coach talking to their student. 
Be specific - reference exact games, timestamps, and situations.
Prioritize the top 2-3 issues, don't overwhelm with everything at once.
```

### Analysis Request Template

```
Based on the following match data, identify:

1. MECHANICAL PATTERNS
- CS consistency
- Trading efficiency (damage dealt vs taken in lane)
- Skill shot accuracy (if available)

2. DECISION PATTERNS  
- Death contexts (solo, teamfight, caught out)
- Objective timing
- Recall timing

3. IMPROVEMENT PRIORITIES
- What's the #1 thing holding this player back?
- What's a quick win they could implement immediately?

Match data:
{match_data}

Respond in JSON format:
{
  "mechanical_issues": [...],
  "decision_issues": [...],
  "top_priority": "...",
  "quick_win": "...",
  "specific_examples": [...]
}
```

## Database Schema

```sql
-- Players table
CREATE TABLE players (
    id TEXT PRIMARY KEY,
    puuid TEXT UNIQUE NOT NULL,
    summoner_name TEXT NOT NULL,
    tag_line TEXT NOT NULL,
    region TEXT NOT NULL,
    rank_tier TEXT,
    rank_division TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Matches table
CREATE TABLE matches (
    id TEXT PRIMARY KEY,
    match_id TEXT UNIQUE NOT NULL,
    player_id TEXT REFERENCES players(id),
    champion TEXT NOT NULL,
    role TEXT,
    win BOOLEAN,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    cs INTEGER,
    cs_per_min REAL,
    vision_score INTEGER,
    damage_dealt INTEGER,
    damage_taken INTEGER,
    gold_earned INTEGER,
    game_duration INTEGER,
    game_version TEXT,
    played_at TIMESTAMP,
    raw_data JSONB,
    timeline_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analysis table
CREATE TABLE analyses (
    id TEXT PRIMARY KEY,
    player_id TEXT REFERENCES players(id),
    match_count INTEGER,
    analysis_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Coaching sessions
CREATE TABLE coaching_sessions (
    id TEXT PRIMARY KEY,
    player_id TEXT REFERENCES players(id),
    messages JSONB,
    context JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_matches_player ON matches(player_id);
CREATE INDEX idx_matches_played_at ON matches(played_at);
CREATE INDEX idx_analyses_player ON analyses(player_id);
```

## Environment Variables

```bash
# .env.example

# Riot API
RIOT_API_KEY=RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
RIOT_DEFAULT_REGION=americas

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Database
DATABASE_URL=sqlite:///./lol_coach.db
# For production: postgresql://user:pass@host:5432/dbname

# Redis (optional, for rate limiting)
REDIS_URL=redis://localhost:6379

# App
APP_ENV=development
LOG_LEVEL=INFO
```

## Testing Strategy

### Unit Tests
- Riot API response parsing
- Metric calculations
- Pattern detection algorithms

### Integration Tests
- Full API flow with mock Riot responses
- Claude API integration
- Database operations

### Sample Test Data
Store sample match JSONs in `tests/fixtures/` for consistent testing without API calls.

## Error Handling

### Riot API Errors
- 401: Invalid API key
- 403: Forbidden (check API key permissions)
- 404: Summoner not found
- 429: Rate limited (implement backoff)
- 500/503: Riot server issues (retry with backoff)

### User-Facing Errors
- Invalid summoner name format
- Player not found in region
- Not enough matches for analysis (minimum 5)
- Private match history

## Success Criteria

### MVP (Phase 1)
- [ ] Fetch player data by Riot ID
- [ ] Retrieve last 20 matches
- [ ] Calculate basic metrics (CS/min, KDA, vision)
- [ ] Generate coaching summary via Claude
- [ ] CLI interface working

### Full Product
- [ ] Pattern detection across 50+ matches
- [ ] Timeline analysis for detailed insights
- [ ] RAG-enhanced recommendations
- [ ] Progress tracking over time
- [ ] Web interface with auth
- [ ] < 5 second response time for analysis

## Notes for Development

1. **Start with the data pipeline** - Get Riot API working reliably first
2. **Cache aggressively** - Match data doesn't change, store it
3. **Rate limits are real** - Build proper queuing from day 1
4. **Timeline data is gold** - That's where the real insights come from
5. **Test with real data** - Use your own account for development
6. **Rank-appropriate advice** - Iron players need different advice than Diamond

## Resources

- Riot API Docs: https://developer.riotgames.com/docs/lol
- Riot API Libraries: https://riot-api-libraries.readthedocs.io/
- Data Dragon (static data): https://developer.riotgames.com/docs/lol#data-dragon
- Community Dragon: https://communitydragon.org/
- Overwolf Docs: https://dev.overwolf.com/
