def _is_college_football_related(tweet_text: str, timeout: int = 15) -> bool:
    """Use Gemini AI to classify if a tweet is college football related.
    
    Uses a three-layer approach:
    1. Quick keyword filter to reject obvious non-football content
    2. Positive keyword filter to accept obvious college football content
    3. Gemini AI for nuanced cases
    
    Args:
        tweet_text: The tweet text to classify
        timeout: Request timeout in seconds
    
    Returns:
        True if Gemini determines it's college football related, False otherwise
    """
    if not tweet_text or not tweet_text.strip():
        return False
    
    text_lower = tweet_text.lower()
    
    # Layer 1: Quick keyword filters to reject obvious non-football sports
    # These are terms that indicate basketball, baseball, hockey, etc.
    non_football_keywords = [
        # Basketball
        "basketball", "nba", "nit", "ncaa tournament", "march madness", "hoops", "three-pointer", "dunk", "slam dunk",
        "jazz", "lakers", "celtics", "warriors", "nets", "76ers", "bucks", "heat", "mavericks", "nuggets",
        "suns", "grizzlies", "kings", "pelicans", "spurs", "raptors", "bulls", "cavaliers", "pistons", "pacers",
        "hawks", "hornets", "magic", "knicks", "rockets", "blazers", "clippers", "timberwolves",
        # Baseball
        "baseball", "mlb", "pitcher", "batter", "home run", "strikeout", "world series", "dugout",
        # Hockey
        "hockey", "nhl", "ice hockey", "puck", "goalie", "boarding", "hat trick", "zamboni",
        # Other sports
        "nfl pro", "professional football", "nba draft", "mlb draft", "nhl draft",
        "nfl game", "nfl team", "nfl player", "nfl draft",
        "soccer", "cricket", "rugby", "tennis", "golf", "boxing", "ufc", "mma",
    ]
    
    # Check if any non-football keyword appears in the tweet
    for keyword in non_football_keywords:
        if keyword in text_lower:
            return False
    
    # Layer 2: Quick keyword filters to accept obvious college football content
    # These keywords strongly indicate college football content
    college_football_keywords = [
        "qb", "quarterback", "starting qb", "true freshman",
        "recruiting", "commit", "committed", "commitment", "recruiting class",
        "transfer portal", "portal",
        "ncaa", "fbs", "fcs", "college football", "cfb",
        "offensive line", "defensive line", "linebacker", "cornerback", "safety",
        "running back", "wide receiver", "tight end", "receiver",
        "bowl game", "bowl", "playoff", "cfp", "college football playoff",
        "signing day", "national signing day",
        "coach", "coaching staff",
        "4-star", "5-star", "3-star", "prospect", "prospects",
    ]
    
    # Check if any college football keyword appears in the tweet
    for keyword in college_football_keywords:
        if keyword in text_lower:
            return True
    
    # Layer 3: Use Gemini for final classification on ambiguous cases
    try:
        from toaster.llm_agents.gemini import get_gemini_response_with_key
        
        # Create a very explicit prompt for college football classification
        classification_prompt = f"""You are a college sports expert. Determine if the following tweet is about COLLEGE FOOTBALL.

COLLEGE FOOTBALL includes:
- NCAA Division I FBS (Football Bowl Subdivision) and FCS (Football Championship Subdivision) football
- College football recruiting (players committing to college football programs)
- College football transfer portal and portal updates
- College football games, scores, and results
- Bowl games (January bowl season, etc.)
- College football playoffs (College Football Playoff)
- College football coaches, teams, conferences
- College football players, roster decisions, starting lineups
- College football strategy and analysis

EXPLICITLY EXCLUDE (return "no" for these):
- NBA (basketball), NCAA basketball, March Madness - any basketball at any level
- MLB (baseball), minor league baseball, college baseball
- Hockey (NHL, college hockey, any level)
- NFL (professional football) or NFL draft - ONLY professional, not college
- Soccer, cricket, rugby, tennis, golf, boxing, MMA, UFC
- Any sport OTHER than college football

Tweet: "{tweet_text}"

You must respond with ONLY "yes" or "no" (lowercase, no other text).
Be liberal in including college football content. If you're unsure, respond "yes".
Only respond "no" if it's clearly NOT about college football."""
        
        response, error = get_gemini_response_with_key(
            history="",
            message=classification_prompt,
            config_path="config"
        )
        
        if error or not response:
            # On error, default to True (do post) to avoid false negatives
            return True
        
        # Check if response starts with "yes"
        return response.strip().lower().startswith("yes")
    
    except Exception:
        # If Gemini is not available or errors occur, default to True (be lenient)
        return True
