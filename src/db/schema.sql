-- LoL AI Coach Database Schema
-- SQLite database for tracking deaths, patterns, missions, and coaching sessions

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ============================================================
-- PLAYERS TABLE
-- Links Discord users to Riot accounts
-- ============================================================
CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id INTEGER UNIQUE NOT NULL,
    riot_id TEXT NOT NULL,
    puuid TEXT,
    platform TEXT DEFAULT 'br1',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_players_discord ON players(discord_id);
CREATE INDEX IF NOT EXISTS idx_players_puuid ON players(puuid);

-- ============================================================
-- MATCHES TABLE
-- Cache match data to avoid re-fetching and link deaths to games
-- ============================================================
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT UNIQUE NOT NULL,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    champion TEXT NOT NULL,
    role TEXT,
    win BOOLEAN,
    kills INTEGER DEFAULT 0,
    deaths INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    cs INTEGER DEFAULT 0,
    vision_score INTEGER DEFAULT 0,
    game_duration_sec INTEGER,
    played_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_matches_player ON matches(player_id);
CREATE INDEX IF NOT EXISTS idx_matches_played_at ON matches(played_at DESC);
CREATE INDEX IF NOT EXISTS idx_matches_match_id ON matches(match_id);

-- ============================================================
-- DEATHS TABLE
-- Rich context for each death event
-- ============================================================
CREATE TABLE IF NOT EXISTS deaths (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_db_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,

    -- Timing
    game_timestamp_ms INTEGER NOT NULL,
    game_phase TEXT NOT NULL CHECK(game_phase IN ('early', 'mid', 'late')),

    -- Position (Riot uses ~0-15000 coordinate system)
    position_x INTEGER,
    position_y INTEGER,
    map_zone TEXT,

    -- Kill context
    killer_champion TEXT,
    killer_participant_id INTEGER,
    assisting_champions TEXT,  -- JSON array

    -- Player state at death
    had_ward_nearby BOOLEAN DEFAULT FALSE,
    gold_diff INTEGER DEFAULT 0,
    cs_diff INTEGER DEFAULT 0,
    level_diff INTEGER DEFAULT 0,
    player_gold INTEGER DEFAULT 0,
    player_champion TEXT,

    -- Classification
    death_type TEXT CHECK(death_type IN ('gank', 'solo_kill', 'teamfight', 'caught', 'tower_dive', 'unknown')),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deaths_player ON deaths(player_id);
CREATE INDEX IF NOT EXISTS idx_deaths_match ON deaths(match_db_id);
CREATE INDEX IF NOT EXISTS idx_deaths_timestamp ON deaths(game_timestamp_ms);
CREATE INDEX IF NOT EXISTS idx_deaths_zone ON deaths(map_zone);
CREATE INDEX IF NOT EXISTS idx_deaths_phase ON deaths(game_phase);

-- ============================================================
-- PATTERNS TABLE
-- Detected recurring behaviors/failure modes
-- ============================================================
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,

    -- Pattern identification
    pattern_key TEXT NOT NULL,
    pattern_category TEXT NOT NULL,
    description TEXT NOT NULL,

    -- Tracking
    occurrences INTEGER DEFAULT 1,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_match_id INTEGER REFERENCES matches(id),
    games_since_last INTEGER DEFAULT 0,

    -- Status tracking
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'improving', 'broken')),
    improvement_streak INTEGER DEFAULT 0,

    -- Sample deaths that exhibit this pattern (JSON array of death IDs)
    sample_death_ids TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(player_id, pattern_key)
);

CREATE INDEX IF NOT EXISTS idx_patterns_player ON patterns(player_id);
CREATE INDEX IF NOT EXISTS idx_patterns_status ON patterns(status);
CREATE INDEX IF NOT EXISTS idx_patterns_key ON patterns(pattern_key);

-- ============================================================
-- MISSIONS TABLE
-- Persistent missions linked to patterns
-- ============================================================
CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    pattern_id INTEGER REFERENCES patterns(id) ON DELETE SET NULL,

    -- Mission content
    description TEXT NOT NULL,
    focus_area TEXT NOT NULL,
    success_criteria TEXT,
    tips TEXT,  -- JSON array

    -- Status tracking
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'failed', 'skipped')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Match tracking
    target_match_id INTEGER REFERENCES matches(id),
    result_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_missions_player ON missions(player_id);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_pattern ON missions(pattern_id);

-- ============================================================
-- VOD_MOMENTS TABLE
-- Deaths flagged for VOD review
-- ============================================================
CREATE TABLE IF NOT EXISTS vod_moments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    death_id INTEGER NOT NULL REFERENCES deaths(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    pattern_id INTEGER REFERENCES patterns(id) ON DELETE SET NULL,

    -- VOD review status
    reviewed BOOLEAN DEFAULT FALSE,
    review_started_at TIMESTAMP,
    review_completed_at TIMESTAMP,

    -- Player response during review
    player_response TEXT,
    player_analysis TEXT,

    -- Coach insights
    coach_question TEXT,
    coach_insight TEXT,

    -- Breakthrough tracking
    had_breakthrough BOOLEAN DEFAULT FALSE,
    breakthrough_insight TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vod_moments_player ON vod_moments(player_id);
CREATE INDEX IF NOT EXISTS idx_vod_moments_reviewed ON vod_moments(reviewed);
CREATE INDEX IF NOT EXISTS idx_vod_moments_death ON vod_moments(death_id);

-- ============================================================
-- COACHING_SESSIONS TABLE
-- Track sessions for continuity
-- ============================================================
CREATE TABLE IF NOT EXISTS coaching_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,

    -- Session context
    focus_area TEXT,
    patterns_discussed TEXT,  -- JSON array of pattern_keys
    insights TEXT,  -- JSON array of insights

    -- Timestamps
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,

    -- For session opener generation
    matches_analyzed INTEGER DEFAULT 0,
    opener_generated TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_player ON coaching_sessions(player_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON coaching_sessions(started_at DESC);

-- ============================================================
-- TRIGGERS for updated_at timestamps
-- ============================================================
CREATE TRIGGER IF NOT EXISTS update_players_timestamp
    AFTER UPDATE ON players
BEGIN
    UPDATE players SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS update_patterns_timestamp
    AFTER UPDATE ON patterns
BEGIN
    UPDATE patterns SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
