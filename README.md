# LoL AI Coach 🎮🤖

An AI-powered coaching system for League of Legends that analyzes your match history and provides personalized improvement recommendations.

## What Makes This Different

This is **NOT** another stats tracker. While apps like Blitz, Mobalytics, and Porofessor show you numbers and recommend builds, LoL AI Coach is a conversational AI that:

- **Understands your patterns** across multiple matches
- **Identifies your specific weaknesses** with concrete examples
- **Creates personalized drills** to address your issues
- **Tracks your improvement** over time
- **Talks to you like a real coach** would

## Example Interaction

```
> analyze "PlayerName#BR1"

🔍 Analyzing last 20 matches for PlayerName#BR1...

📊 Found some patterns:

You died before 10 minutes in 14 of your last 20 games, averaging 2.1 early 
deaths per game. Looking at the timeline data, most of these deaths happen 
between 6-8 minutes when you're pushed up without vision.

In your Jinx game yesterday (loss, 3/8/5), you died at 6:42 to a gank from 
river. You had no wards placed at that point. This same pattern happened in 
your Caitlyn game 3 days ago at 7:15.

🎯 Priority #1: Wave management for safety

When your wave is pushing toward enemy tower, you're vulnerable. Instead of 
walking up for CS, let the wave push back to you.

📝 Exercise: In your next 3 games, focus on one thing - don't walk past the 
middle of the lane if you don't have a ward in river bush. Track how many 
times you catch yourself about to break this rule.

Want me to break down your teamfighting patterns, or focus more on laning?
```

## Quick Start

```bash
# Clone the repo
git clone https://github.com/yourusername/lol-ai-coach.git
cd lol-ai-coach

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run analysis
python scripts/analyze_player.py "YourName#TAG" --region americas
```

## Getting API Keys

### Riot Games API (Free)
1. Go to https://developer.riotgames.com/
2. Sign in with your Riot account
3. Your development API key is on the dashboard
4. Note: Dev keys expire every 24 hours

### Anthropic Claude API
1. Go to https://console.anthropic.com/
2. Create an account and add credits
3. Generate an API key

## Features

### Phase 1 (Current)
- ✅ Fetch player data by Riot ID
- ✅ Analyze last 20 matches
- ✅ Basic pattern detection
- ✅ AI-generated coaching feedback
- ✅ CLI interface

### Phase 2 (In Progress)
- ⏳ Timeline analysis for detailed insights
- ⏳ Lane phase breakdown
- ⏳ Cross-match pattern recognition
- ⏳ Rank-appropriate benchmarks

### Phase 3 (Planned)
- 📋 Knowledge base with coaching content
- 📋 Custom exercise generation
- 📋 Progress tracking

### Phase 4 (Future)
- 📋 Web interface
- 📋 Real-time Overwolf overlay

## Project Structure

```
lol-ai-coach/
├── src/
│   ├── api/           # Riot & Claude API clients
│   ├── analysis/      # Pattern detection
│   ├── coach/         # AI coaching logic
│   └── models/        # Data models
├── knowledge/         # Coaching documents (RAG)
├── scripts/           # CLI tools
└── tests/             # Test suite
```

## Configuration

```bash
# .env
RIOT_API_KEY=RGAPI-xxxxx          # Your Riot API key
ANTHROPIC_API_KEY=sk-ant-xxxxx    # Your Claude API key
RIOT_DEFAULT_REGION=americas       # americas, europe, asia, sea
```

## Supported Regions

| Region Code | Routing | Server |
|-------------|---------|--------|
| na1 | americas | North America |
| br1 | americas | Brazil |
| euw1 | europe | EU West |
| eun1 | europe | EU Nordic & East |
| kr | asia | Korea |
| jp1 | asia | Japan |

## Contributing

Contributions welcome! See AGENT.md for technical details and development guidelines.

## License

MIT

## Disclaimer

LoL AI Coach isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing League of Legends. League of Legends and Riot Games are trademarks or registered trademarks of Riot Games, Inc.
