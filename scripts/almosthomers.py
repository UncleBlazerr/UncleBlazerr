from pybaseball import statcast, playerid_reverse_lookup
from datetime import datetime, timedelta
import pandas as pd
import os
import requests
import time
import json

#make os dir
os.makedirs("../almosthomers", exist_ok=True)

# Multi-day tracking functions
def load_historical_data():
    """Load historical elite contact data from JSON file"""
    data_file = "../almosthomers/elite_contact_history.json"
    if os.path.exists(data_file):
        with open(data_file, 'r') as f:
            return json.load(f)
    return {}

def save_historical_data(data):
    """Save historical elite contact data to JSON file"""
    data_file = "../almosthomers/elite_contact_history.json"
    with open(data_file, 'w') as f:
        json.dump(data, f, indent=2)

def update_rolling_data(historical_data, today_data, current_date):
    """Update rolling 4-day data with today's elite contact hits"""
    # Convert date to string for JSON keys
    date_str = current_date
    
    # Add today's data
    if date_str not in historical_data:
        historical_data[date_str] = {}
    
    # Clear today's data first (in case script runs multiple times same day)
    historical_data[date_str] = {}
    
    # Add today's elite contact hits grouped by player
    for _, row in today_data.iterrows():
        player_name = row['Batter']
        if player_name not in historical_data[date_str]:
            historical_data[date_str][player_name] = {
                'count': 0,
                'best_exit_velo': 0,
                'best_distance': 0,
                'best_event': 'field_out',
                'hits': []
            }
        
        # Update player's stats for today
        historical_data[date_str][player_name]['count'] += 1
        historical_data[date_str][player_name]['best_exit_velo'] = max(
            historical_data[date_str][player_name]['best_exit_velo'], 
            row['Exit Velo']
        )
        historical_data[date_str][player_name]['best_distance'] = max(
            historical_data[date_str][player_name]['best_distance'], 
            row['Distance (ft)']
        )
        
        # Track best event (prioritize triple > double > single > others)
        current_event = historical_data[date_str][player_name]['best_event']
        new_event = row['Event']
        event_priority = {'triple': 3, 'double': 2, 'single': 1}
        if event_priority.get(new_event, 0) > event_priority.get(current_event, 0):
            historical_data[date_str][player_name]['best_event'] = new_event
        
        # Store individual hit details
        historical_data[date_str][player_name]['hits'].append({
            'exit_velo': row['Exit Velo'],
            'distance': row['Distance (ft)'],
            'event': row['Event']
        })
    
    # Keep only last 4 days of data
    all_dates = sorted(historical_data.keys())
    if len(all_dates) > 4:
        # Remove oldest dates
        for old_date in all_dates[:-4]:
            del historical_data[old_date]
    
    return historical_data

def create_rolling_leaderboard(historical_data):
    """Create 4-day rolling leaderboard from historical data"""
    player_totals = {}
    
    # Sum up all players across all days
    for date_str, daily_data in historical_data.items():
        for player_name, player_data in daily_data.items():
            if player_name not in player_totals:
                player_totals[player_name] = {
                    'total_count': 0,
                    'best_exit_velo': 0,
                    'best_distance': 0,
                    'best_event': 'field_out',
                    'days_active': 0,
                    'batter_info': player_name  # Keep the batter info with logos
                }
            
            player_totals[player_name]['total_count'] += player_data['count']
            player_totals[player_name]['best_exit_velo'] = max(
                player_totals[player_name]['best_exit_velo'], 
                player_data['best_exit_velo']
            )
            player_totals[player_name]['best_distance'] = max(
                player_totals[player_name]['best_distance'], 
                player_data['best_distance']
            )
            player_totals[player_name]['days_active'] += 1
            
            # Update best event
            current_event = player_totals[player_name]['best_event']
            new_event = player_data['best_event']
            event_priority = {'triple': 3, 'double': 2, 'single': 1}
            if event_priority.get(new_event, 0) > event_priority.get(current_event, 0):
                player_totals[player_name]['best_event'] = new_event
    
    # Convert to list and sort by total count
    leaderboard = []
    for player_name, stats in player_totals.items():
        leaderboard.append({
            'Batter': stats['batter_info'],
            'Total_Count': stats['total_count'],
            'Best_Exit_Velo': stats['best_exit_velo'],
            'Best_Distance': stats['best_distance'],
            'Best_Event': stats['best_event'],
            'Days_Active': stats['days_active']
        })
    
    # Sort by total count (descending), then by best exit velo (descending)
    leaderboard.sort(key=lambda x: (x['Total_Count'], x['Best_Exit_Velo']), reverse=True)
    
    return leaderboard

# Hybrid MLB API functions for real-time data
def get_todays_game_ids(date_str):
    """Get all MLB game IDs for a specific date"""
    import requests
    
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}'
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'dates' in data and len(data['dates']) > 0:
                games = data['dates'][0].get('games', [])
                # Only return completed games
                completed_games = [
                    game['gamePk'] for game in games 
                    if game.get('status', {}).get('detailedState') in ['Final', 'Game Over']
                ]
                return completed_games
    except Exception as e:
        print(f"Error getting game IDs: {e}")
    return []

def fetch_game_statcast_data(game_pk):
    """Fetch Statcast data from a specific game using MLB API"""
    import requests
    
    # First get game info including team abbreviations
    game_info_url = f'https://statsapi.mlb.com/api/v1/game/{game_pk}/linescore'
    try:
        info_response = requests.get(game_info_url, timeout=10)
        if info_response.status_code == 200:
            game_info = info_response.json()
            home_team_abbr = game_info.get('teams', {}).get('home', {}).get('team', {}).get('abbreviation', 'UNK')
            away_team_abbr = game_info.get('teams', {}).get('away', {}).get('team', {}).get('abbreviation', 'UNK')
        else:
            home_team_abbr = away_team_abbr = 'UNK'
    except:
        home_team_abbr = away_team_abbr = 'UNK'
    
    url = f'https://statsapi.mlb.com/api/v1/game/{game_pk}/playByPlay'
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            
            
            statcast_hits = []
            if 'allPlays' in data:
                for play in data['allPlays']:
                    if 'playEvents' in play:
                        for event in play['playEvents']:
                            if 'hitData' in event:
                                hit_data = event['hitData']
                                if 'launchSpeed' in hit_data and 'launchAngle' in hit_data:
                                    # Extract batter info
                                    batter_id = None
                                    batter_name = None
                                    if 'player' in event and 'id' in event['player']:
                                        batter_id = event['player']['id']
                                        batter_name = event['player'].get('fullName')
                                        # If no fullName, try other name fields
                                        if not batter_name:
                                            batter_name = event['player'].get('firstName', '') + ' ' + event['player'].get('lastName', '')
                                            batter_name = batter_name.strip()
                                        # If still no name, use the batter ID as fallback
                                        if not batter_name or batter_name == ' ':
                                            batter_name = f"Player {batter_id}"
                                        
                                    
                                    # Extract team info
                                    team = None
                                    if 'about' in play and 'inning' in play['about']:
                                        # Home team bats in bottom, away in top
                                        if play['about']['halfInning'] == 'bottom':
                                            team = home_team_abbr
                                        else:
                                            team = away_team_abbr
                                    
                                    # Extract event type
                                    event_type = event.get('details', {}).get('event', 'field_out')
                                    
                                    statcast_hit = {
                                        'batter': batter_id,
                                        'player_name': batter_name,
                                        'team': team,
                                        'launch_speed': hit_data['launchSpeed'],
                                        'launch_angle': hit_data['launchAngle'],
                                        'hit_distance_sc': hit_data.get('totalDistance', 0),
                                        'events': event_type,
                                        'bat_speed': hit_data.get('batSpeed', None),
                                        'game_date': data.get('gameData', {}).get('datetime', {}).get('originalDate', ''),
                                        'home_team': home_team_abbr,
                                        'away_team': away_team_abbr
                                    }
                                    statcast_hits.append(statcast_hit)
            
            return statcast_hits
    except Exception as e:
        print(f"Error fetching game {game_pk}: {e}")
    return []

def get_realtime_statcast_data(date_str):
    """Get real-time Statcast data for a date using MLB API"""
    import pandas as pd
    
    print(f"Fetching real-time data for {date_str}...")
    
    # Get today's game IDs
    game_ids = get_todays_game_ids(date_str)
    print(f"Found {len(game_ids)} completed games")
    
    if not game_ids:
        return pd.DataFrame()
    
    # Fetch data from all games
    all_hits = []
    for game_id in game_ids:
        print(f"Fetching game {game_id}...")
        hits = fetch_game_statcast_data(game_id)
        all_hits.extend(hits)
    
    if not all_hits:
        return pd.DataFrame()
    
    # Convert to DataFrame and format like pybaseball
    df = pd.DataFrame(all_hits)
    
    # Rename columns to match pybaseball format
    df = df.rename(columns={
        'launch_speed': 'launch_speed',
        'launch_angle': 'launch_angle', 
        'hit_distance_sc': 'hit_distance_sc',
        'events': 'events',
        'bat_speed': 'bat_speed',
        'team': 'team'
    })
    
    print(f"Retrieved {len(df)} total batted balls from MLB API")
    return df

# Elite player analysis functions (defined here for use later)
def extract_player_name_from_batter(batter_text):
    """Extract clean player name from batter column (which may contain HTML)"""
    if pd.isna(batter_text):
        return "Unknown Player"
    
    batter_str = str(batter_text)
    
    # If it contains HTML with img tag, extract the text after it
    if '<img' in batter_str and '>' in batter_str:
        # Find the last > of the img tag and get text after it
        last_gt = batter_str.rfind('>')
        if last_gt != -1:
            name = batter_str[last_gt + 1:].strip()
            # If we get 'nan', try to find a better name
            if name == 'nan' or name == '':
                return "Unknown Player"
            return name
    
    # If it contains HTML span, extract the text content
    if '<span class="leaderboard-player-name">' in batter_str:
        import re
        match = re.search(r'<span class="leaderboard-player-name">(.*?)</span>', batter_str)
        if match:
            name = match.group(1)
            if name == 'nan':
                return "Unknown Player"
            return name
    
    # If it's already clean text, return as is
    result = batter_str.strip()
    if result == 'nan':
        return "Unknown Player"
    return result

def calculate_player_elite_metrics(player_data):
    """Calculate elite metrics for a player based on their batted balls"""
    # Import is_barrel locally to avoid circular dependency
    def is_barrel_local(exit_velo, launch_angle):
        if exit_velo < 98:
            return False
        
        # Barrel qualification ranges based on exit velocity
        barrel_ranges = {
            98: (26, 30), 99: (25, 31), 100: (24, 33), 101: (23, 34),
            102: (22, 36), 103: (21, 37), 104: (20, 38), 105: (19, 39), 106: (18, 41)
        }
        
        # For 107+ mph, use the widest range
        if exit_velo >= 107:
            min_angle, max_angle = 8, 50
        else:
            # Find the appropriate range for this exit velocity
            ev_floor = int(exit_velo)
            if ev_floor in barrel_ranges:
                min_angle, max_angle = barrel_ranges[ev_floor]
            else:
                # For speeds between defined ranges, use the lower speed's range
                for speed in sorted(barrel_ranges.keys(), reverse=True):
                    if exit_velo >= speed:
                        min_angle, max_angle = barrel_ranges[speed]
                        break
                else:
                    return False
        
        return min_angle <= launch_angle <= max_angle
    
    if len(player_data) == 0:
        return None
    
    total_batted_balls = len(player_data)
    
    # Barrel rate: % of batted balls that are barrels (98+ mph + optimal launch angle)
    barrels = player_data.apply(lambda row: is_barrel_local(row['Exit Velo'], row['Launch Angle']), axis=1).sum()
    barrel_rate = (barrels / total_batted_balls) * 100 if total_batted_balls > 0 else 0
    
    # Hard hit rate: % of batted balls 95+ mph
    hard_hits = (player_data['Exit Velo'] >= 95).sum()
    hard_hit_rate = (hard_hits / total_batted_balls) * 100 if total_batted_balls > 0 else 0
    
    # Fly ball rate: % of batted balls with launch angle suggesting fly ball (10+ degrees)
    fly_balls = (player_data['Launch Angle'] >= 10).sum()
    fly_ball_rate = (fly_balls / total_batted_balls) * 100 if total_batted_balls > 0 else 0
    
    # Additional elite metrics
    avg_exit_velo = player_data['Exit Velo'].mean()
    max_exit_velo = player_data['Exit Velo'].max()
    avg_distance = player_data['Distance (ft)'].mean()
    max_distance = player_data['Distance (ft)'].max()
    
    # Home run rate (if any HRs in the data)
    home_runs = (player_data['Event'] == 'home_run').sum()
    hr_rate = (home_runs / total_batted_balls) * 100 if total_batted_balls > 0 else 0
    
    return {
        'total_batted_balls': total_batted_balls,
        'barrel_rate': round(barrel_rate, 1),
        'hard_hit_rate': round(hard_hit_rate, 1),
        'fly_ball_rate': round(fly_ball_rate, 1),
        'avg_exit_velo': round(avg_exit_velo, 1),
        'max_exit_velo': round(max_exit_velo, 1),
        'avg_distance': round(avg_distance, 1),
        'max_distance': round(max_distance, 1),
        'hr_rate': round(hr_rate, 1),
        'barrels': barrels,
        'hard_hits': hard_hits,
        'fly_balls': fly_balls,
        'home_runs': home_runs
    }

def create_elite_players_table(combined_data, min_batted_balls=10):
    """Create table of elite players with 15%+ barrel rate"""
    if len(combined_data) == 0:
        return []
    
    # Group by player and calculate metrics
    elite_players = []
    total_players_checked = 0
    players_with_enough_batted_balls = 0
    
    # Create a clean player name column for grouping
    combined_data['Clean_Player_Name'] = combined_data['Batter'].apply(extract_player_name_from_batter)
    
    
    for player_name in combined_data['Clean_Player_Name'].unique():
        player_data = combined_data[combined_data['Clean_Player_Name'] == player_name]
        total_players_checked += 1
        
        # Skip players with too few batted balls
        if len(player_data) < min_batted_balls:
            continue
            
        players_with_enough_batted_balls += 1
        metrics = calculate_player_elite_metrics(player_data)
        
        
        if metrics and metrics['barrel_rate'] >= 15.0:  # Elite threshold: 15%+ barrel rate
            # Get player info with team logo
            first_hit = player_data.iloc[0]
            elite_players.append({
                'Batter': player_name,  # This is already the clean name from the loop
                'Team': first_hit['Team'],
                **metrics
            })
    
    
    # Sort by barrel rate (descending)
    elite_players.sort(key=lambda x: x['barrel_rate'], reverse=True)
    
    return elite_players

# Use yesterday's date as "today" since Statcast data has delays
# This ensures we get the most recent complete day of data
today = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')  # 8/18 when run on 8/19
yesterday = (datetime.today() - timedelta(days=2)).strftime('%Y-%m-%d')  # 8/17 when run on 8/19

print(f"Pulling Statcast data for: {today}")

# Pull Statcast data for today - try pybaseball first, then real-time API
data = statcast(start_dt=today, end_dt=today)

# If no data from pybaseball, skip real-time API for now (has issues with team/player names)
if len(data) == 0:
    print("No data from pybaseball, using yesterday's data as primary...")
    # realtime_data = get_realtime_statcast_data(today)  # Disabled due to team/player issues
    realtime_data = pd.DataFrame()
    if len(realtime_data) > 0:
        print(f"Successfully retrieved {len(realtime_data)} hits from MLB API")
        
        # Add missing columns to match pybaseball format
        realtime_data['game_pk'] = 0  # Placeholder
        realtime_data['inning_topbot'] = 'top'  # Placeholder
        realtime_data['game_year'] = 2025
        realtime_data['estimated_ba_using_speedangle'] = float('nan')
        realtime_data['estimated_woba_using_speedangle'] = float('nan')
        realtime_data['woba_value'] = float('nan')
        realtime_data['babip_value'] = float('nan')
        realtime_data['iso_value'] = float('nan')
        
        data = realtime_data
    else:
        print("No real-time data available either")

print(f"Pulling Statcast data for day before: {yesterday}")

# Pull Statcast data for yesterday  
data_day_before = statcast(start_dt=yesterday, end_dt=yesterday)

print(f"Total batted balls found today: {len(data)}")
print(f"Total batted balls found day before: {len(data_day_before)}")

# Filter valid batted-ball data for today, exclude home runs, require exit velo >= 93, exclude null events
filtered = data[
    (data['launch_speed'].notna()) &
    (data['launch_angle'].notna()) &
    (data['hit_distance_sc'].notna()) &
    (data['events'].notna()) &
    (data['events'] != 'home_run') &
    (data['launch_speed'] >= 93)
]

# Filter valid batted-ball data for day before
filtered_day_before = data_day_before[
    (data_day_before['launch_speed'].notna()) &
    (data_day_before['launch_angle'].notna()) &
    (data_day_before['hit_distance_sc'].notna()) &
    (data_day_before['events'].notna()) &
    (data_day_before['events'] != 'home_run') &
    (data_day_before['launch_speed'] >= 93)
]

print(f"Bat speed column available: {'bat_speed' in data.columns}")
print(f"Available columns: {list(data.columns)}")
print(f"HR/Park columns: {[col for col in data.columns if 'park' in col.lower() or 'hr' in col.lower()]}")
print(f"Estimated probability columns: {[col for col in data.columns if 'estimated' in col.lower() or 'prob' in col.lower() or 'exp' in col.lower()]}")

print(f"Filtered batted balls today (no HRs): {len(filtered)}")
print(f"Filtered batted balls day before (no HRs): {len(filtered_day_before)}")


# Select useful columns (include bat_speed and estimated_slg if available)
columns_to_select = [
    'batter', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'game_pk',
    'events', 'inning_topbot', 'home_team', 'away_team'
]

if 'bat_speed' in filtered.columns:
    columns_to_select.insert(4, 'bat_speed')

subset = filtered[columns_to_select].copy()

# Add placeholder columns if missing
if 'bat_speed' not in subset.columns:
    subset['bat_speed'] = float('nan')

# Lookup batter names
batter_ids = subset['batter'].unique()
print(f"\nLooking up names for {len(batter_ids)} unique batter IDs...")
batter_names = playerid_reverse_lookup(batter_ids, key_type='mlbam')[['key_mlbam', 'name_first', 'name_last']]
# Properly capitalize names
batter_names['name_first'] = batter_names['name_first'].str.title()
batter_names['name_last'] = batter_names['name_last'].str.title()
batter_names['batter_name'] = batter_names['name_first'] + ' ' + batter_names['name_last']

print(f"Found names for {len(batter_names)} batters")


# Merge names, but preserve original names from MLB API if lookup fails
merged = subset.merge(
    batter_names[['key_mlbam', 'batter_name']],
    left_on='batter',
    right_on='key_mlbam',
    how='left'
)

# If we have original batter names from MLB API (hybrid data), preserve them when lookup fails
if 'player_name' in subset.columns:
    # Fill missing batter_name with original player_name from MLB API
    merged['batter_name'] = merged['batter_name'].fillna(merged['player_name'])

# Infer batting team from inning
merged['team_abbr'] = merged.apply(
    lambda row: row['away_team'] if row['inning_topbot'] == 'Top' else row['home_team'],
    axis=1
)


# Map logos from ESPN CDN
def get_logo_url(team_abbr):
    return f"https://a.espncdn.com/i/teamlogos/mlb/500/{team_abbr.lower()}.png"

merged['team_logo'] = merged['team_abbr'].apply(get_logo_url)

# Build batter+logo display
merged['batter_with_logo'] = merged.apply(
    lambda row: f'<img src="{row["team_logo"]}" width="24" style="vertical-align:middle"> {row["batter_name"]}',
    axis=1
)

# Final selection
final = merged[[
    'batter_with_logo', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'bat_speed', 'game_pk', 'events', 'team_abbr'
]].sort_values(by='hit_distance_sc', ascending=False).reset_index(drop=True)

# Rename for clarity
final.columns = ['Batter', 'Exit Velo', 'Launch Angle', 'Distance (ft)', 'Bat Speed', 'Game PK', 'Event', 'Team']

# Function to estimate HR/Park based on distance and exit velocity
def estimate_hr_parks(distance, exit_velo, launch_angle):
    """
    Estimate how many MLB parks this would be a HR in based on distance and contact quality
    """
    # Basic park factor estimates based on distance
    if distance >= 420:  # Deep shots
        return "30/30"  # HR in all parks
    elif distance >= 400:
        return "28/30"  # HR in most parks
    elif distance >= 380:
        return "20/30"  # HR in about 2/3 of parks
    elif distance >= 360:
        return "12/30"  # HR in hitter-friendly parks
    elif distance >= 340:
        return "6/30"   # HR in very few parks
    elif distance >= 320:
        return "2/30"   # HR only in Fenway/Yankees
    else:
        return "0/30"   # Not a HR anywhere

# Add HR/Park estimation
print("Calculating HR/Park estimates...")
final['HR_Parks'] = final.apply(
    lambda row: estimate_hr_parks(row['Distance (ft)'], row['Exit Velo'], row['Launch Angle']), 
    axis=1
)

# Reorder columns to include HR_Parks
final = final[['Batter', 'Exit Velo', 'Launch Angle', 'Distance (ft)', 'Bat Speed', 'HR_Parks', 'Event', 'Team']]

# Process day-before data using same pipeline
print("Processing day-before data...")
if len(filtered_day_before) > 0:
    # Select useful columns for day-before data
    columns_to_select_day_before = [
        'batter', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'game_pk',
        'events', 'inning_topbot', 'home_team', 'away_team'
    ]

    if 'bat_speed' in filtered_day_before.columns:
        columns_to_select_day_before.insert(4, 'bat_speed')

    subset_day_before = filtered_day_before[columns_to_select_day_before].copy()

    # Add placeholder columns if missing
    if 'bat_speed' not in subset_day_before.columns:
        subset_day_before['bat_speed'] = float('nan')

    # Lookup batter names for day-before data
    batter_ids_day_before = subset_day_before['batter'].unique()
    print(f"Looking up names for {len(batter_ids_day_before)} unique batter IDs from day before...")
    batter_names_day_before = playerid_reverse_lookup(batter_ids_day_before, key_type='mlbam')[['key_mlbam', 'name_first', 'name_last']]
    # Properly capitalize names
    batter_names_day_before['name_first'] = batter_names_day_before['name_first'].str.title()
    batter_names_day_before['name_last'] = batter_names_day_before['name_last'].str.title()
    batter_names_day_before['batter_name'] = batter_names_day_before['name_first'] + ' ' + batter_names_day_before['name_last']

    print(f"Found names for {len(batter_names_day_before)} batters from day before")

    # Merge names for day-before data
    merged_day_before = subset_day_before.merge(
        batter_names_day_before[['key_mlbam', 'batter_name']],
        left_on='batter',
        right_on='key_mlbam',
        how='left'
    )

    # Infer batting team from inning for day-before data
    merged_day_before['team_abbr'] = merged_day_before.apply(
        lambda row: row['away_team'] if row['inning_topbot'] == 'Top' else row['home_team'],
        axis=1
    )

    merged_day_before['team_logo'] = merged_day_before['team_abbr'].apply(get_logo_url)

    # Build batter+logo display for day-before data
    merged_day_before['batter_with_logo'] = merged_day_before.apply(
        lambda row: f'<img src="{row["team_logo"]}" width="24" style="vertical-align:middle"> {row["batter_name"]}',
        axis=1
    )

    # Final selection for day-before data
    final_day_before = merged_day_before[[
        'batter_with_logo', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'bat_speed', 'game_pk', 'events', 'team_abbr'
    ]].sort_values(by='hit_distance_sc', ascending=False).reset_index(drop=True)

    # Rename for clarity
    final_day_before.columns = ['Batter', 'Exit Velo', 'Launch Angle', 'Distance (ft)', 'Bat Speed', 'Game PK', 'Event', 'Team']

    # Add HR/Park estimation for day-before data
    print("Calculating HR/Park estimates for day-before...")
    final_day_before['HR_Parks'] = final_day_before.apply(
        lambda row: estimate_hr_parks(row['Distance (ft)'], row['Exit Velo'], row['Launch Angle']), 
        axis=1
    )

    # Reorder columns for day-before data
    final_day_before = final_day_before[['Batter', 'Exit Velo', 'Launch Angle', 'Distance (ft)', 'Bat Speed', 'HR_Parks', 'Event', 'Team']]
else:
    final_day_before = pd.DataFrame()

# Create elite contact leaderboard for today
print("Creating elite contact leaderboard...")
elite_criteria = final[(final['Exit Velo'] > 95) & (final['Distance (ft)'] > 200)].copy()

# Count occurrences per player to determine sort order
player_counts = elite_criteria.groupby('Batter').size().reset_index(name='Count')

# Add count to each row for sorting
elite_criteria = elite_criteria.merge(player_counts, on='Batter', how='left')

# Sort by count (descending), then by exit velocity (descending)
elite_leaderboard = elite_criteria.sort_values(['Count', 'Exit Velo'], ascending=[False, False]).reset_index(drop=True)

# Create elite contact leaderboard for day before
print("Creating day-before elite contact leaderboard...")
if len(final_day_before) > 0:
    elite_criteria_day_before = final_day_before[(final_day_before['Exit Velo'] > 95) & (final_day_before['Distance (ft)'] > 200)].copy()
    
    # Count occurrences per player to determine sort order
    player_counts_day_before = elite_criteria_day_before.groupby('Batter').size().reset_index(name='Count')
    
    # Add count to each row for sorting
    elite_criteria_day_before = elite_criteria_day_before.merge(player_counts_day_before, on='Batter', how='left')
    
    # Sort by count (descending), then by exit velocity (descending)
    elite_leaderboard_day_before = elite_criteria_day_before.sort_values(['Count', 'Exit Velo'], ascending=[False, False]).reset_index(drop=True)
else:
    elite_leaderboard_day_before = pd.DataFrame()

# Multi-day tracking
print("Updating multi-day tracking data...")
historical_data = load_historical_data()
historical_data = update_rolling_data(historical_data, elite_criteria, today)
save_historical_data(historical_data)

# Create rolling 4-day leaderboard
rolling_leaderboard = create_rolling_leaderboard(historical_data)
print(f"Rolling 4-day leaderboard has {len(rolling_leaderboard)} players")

# Create Elite Players table (15%+ barrel rate)
print("Creating Elite Players table...")
# Pull additional days of data for comprehensive barrel rate analysis
try:
    print("Pulling additional Statcast data for comprehensive Elite analysis...")
    # Get data from the last 4 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=4)
    
    additional_data = pybaseball.statcast(
        start_dt=start_date.strftime('%Y-%m-%d'),
        end_dt=end_date.strftime('%Y-%m-%d')
    )
    
    if len(additional_data) > 0:
        # Filter for batted balls and add required columns
        additional_filtered = additional_data[
            (additional_data['type'] == 'X') & 
            (additional_data['events'].notna()) & 
            (additional_data['launch_speed'].notna()) & 
            (additional_data['launch_angle'].notna())
        ].copy()
        
        # Rename columns to match our format
        additional_filtered['Exit Velo'] = additional_filtered['launch_speed']
        additional_filtered['Launch Angle'] = additional_filtered['launch_angle']
        additional_filtered['Distance (ft)'] = additional_filtered['hit_distance_sc']
        additional_filtered['Event'] = additional_filtered['events']
        additional_filtered['Batter'] = additional_filtered['player_name']
        
        # Lookup team info
        team_mapping = {}
        for _, row in additional_filtered.iterrows():
            if row['home_team'] not in team_mapping:
                team_mapping[row['home_team']] = f"https://a.espncdn.com/i/teamlogos/mlb/500/{row['home_team'].lower()}.png"
            if row['away_team'] not in team_mapping:
                team_mapping[row['away_team']] = f"https://a.espncdn.com/i/teamlogos/mlb/500/{row['away_team'].lower()}.png"
        
        # Add team logos (simplified)
        def get_team_logo(home_team, away_team, inning_topbot):
            team = home_team if inning_topbot == 'Bot' else away_team
            return f'<img src="https://a.espncdn.com/i/teamlogos/mlb/500/{team.lower()}.png" width="24" style="vertical-align:middle">'
        
        additional_filtered['Team'] = additional_filtered.apply(
            lambda row: get_team_logo(row['home_team'], row['away_team'], row['inning_topbot']), axis=1
        )
        
        combined_data = additional_filtered
        print(f"Using {len(combined_data)} batted balls from 4-day Statcast data for Elite analysis")
    else:
        # Fallback to today/yesterday if no additional data
        combined_data = pd.concat([final, final_day_before], ignore_index=True) if len(final) > 0 or len(final_day_before) > 0 else pd.DataFrame()
        print(f"Using {len(combined_data)} batted balls from today/yesterday for Elite analysis")

except Exception as e:
    print(f"Could not pull additional data: {e}")
    # Fallback to today/yesterday data
    combined_data = pd.concat([final, final_day_before], ignore_index=True) if len(final) > 0 or len(final_day_before) > 0 else pd.DataFrame()
    print(f"Using {len(combined_data)} batted balls from today/yesterday for Elite analysis")

elite_players = create_elite_players_table(combined_data, min_batted_balls=8)  # Adjusted threshold for recent data
print(f"Found {len(elite_players)} elite players with 15%+ barrel rate")

# Get date range for display
date_keys = sorted(historical_data.keys())
if date_keys:
    start_date = datetime.strptime(date_keys[0], '%Y-%m-%d').strftime('%B %d')
    end_date = datetime.strptime(date_keys[-1], '%Y-%m-%d').strftime('%B %d, %Y')
    date_range = f"{start_date} - {end_date}" if len(date_keys) > 1 else end_date
else:
    date_range = "No data available"

# Function to get exit velocity color with enhanced 98+ mph highlighting
def get_exit_velo_color(velo):
    if velo > 98:
        return 'background-color: #8B0000; color: #FFD700; font-weight: bold; box-shadow: 0 0 10px #FFD700; border: 2px solid #FFD700'  # Dark red with gold glow
    elif velo > 94:
        return 'background-color: #FF0000'  # Red
    else:
        return 'background-color: #FFB6C1'  # Light red

# Function to get launch angle color
def get_launch_angle_color(angle):
    if 18 <= angle <= 30:
        return 'background-color: #00FF00'  # Bright green
    else:
        return 'background-color: #FFFF00'  # Yellow

# Function to format bat speed with lightning bolt
def format_bat_speed(speed):
    if pd.isna(speed):
        return 'N/A'
    elif speed > 75:
        return f'⚡ {speed:.1f}'
    else:
        return f'{speed:.1f}'

# Function to check if a ball qualifies as a barrel
def is_barrel(exit_velo, launch_angle):
    if exit_velo < 98:
        return False
    
    # Barrel qualification ranges based on exit velocity
    barrel_ranges = {
        98: (26, 30),
        99: (25, 31),
        100: (24, 33),
        101: (23, 34),
        102: (22, 36),
        103: (21, 37),
        104: (20, 38),
        105: (19, 39),
        106: (18, 41)
    }
    
    # For 107+ mph, use the widest range
    if exit_velo >= 107:
        min_angle, max_angle = 8, 50
    else:
        # Find the appropriate range for this exit velocity
        ev_floor = int(exit_velo)
        if ev_floor in barrel_ranges:
            min_angle, max_angle = barrel_ranges[ev_floor]
        else:
            # For speeds between defined ranges, use the lower speed's range
            for speed in sorted(barrel_ranges.keys(), reverse=True):
                if exit_velo >= speed:
                    min_angle, max_angle = barrel_ranges[speed]
                    break
            else:
                return False
    
    return min_angle <= launch_angle <= max_angle


# Updated launch angle color function with detailed ranges
def get_launch_angle_color(angle, exit_velo):
    if is_barrel(exit_velo, angle):
        return 'background-color: #FF6B35'  # Orange for barrel
    elif 31 <= angle <= 35:
        return 'background-color: #006400'  # Dark green
    elif 20 <= angle <= 30:
        return 'background-color: #00FF00'  # Green
    elif 14 <= angle <= 19:
        return 'background-color: #90EE90'  # Light green
    elif 8 <= angle <= 13:
        return 'background-color: #FFFF00'  # Yellow
    else:  # Below 8
        return 'background-color: #FF0000'  # Red

# Apply exit velocity coloring and add barrel qualification
if len(final) > 0:
    final['Exit Velo Style'] = final['Exit Velo'].apply(lambda x: get_exit_velo_color(x))
    final['Is_Barrel'] = final.apply(lambda row: is_barrel(row['Exit Velo'], row['Launch Angle']), axis=1)
else:
    final['Exit Velo Style'] = []
    final['Is_Barrel'] = []

# Apply same processing to day-before data
if len(final_day_before) > 0:
    final_day_before['Exit Velo Style'] = final_day_before['Exit Velo'].apply(lambda x: get_exit_velo_color(x))
    final_day_before['Is_Barrel'] = final_day_before.apply(lambda row: is_barrel(row['Exit Velo'], row['Launch Angle']), axis=1)
else:
    final_day_before['Exit Velo Style'] = []
    final_day_before['Is_Barrel'] = []

def format_barrel(is_barrel_bool):
    return '🛢️' if is_barrel_bool else ''

# Function to format HR/Park data
def format_hr_parks(hr_parks_str):
    if pd.isna(hr_parks_str) or hr_parks_str == '0/30':
        return '0/30'
    elif hr_parks_str in ['28/30', '30/30']:
        return f'🔥 {hr_parks_str}'
    elif hr_parks_str in ['20/30', '12/30']:
        return f'⚡ {hr_parks_str}'
    else:
        return hr_parks_str

# Group by team
teams = final['Team'].unique()

# Calculate team statistics
team_stats = {}
for team in final['Team'].unique():
    team_data = final[final['Team'] == team]
    team_stats[team] = {
        'count': len(team_data),
        'avg_distance': team_data['Distance (ft)'].mean(),
        'max_distance': team_data['Distance (ft)'].max(),
        'avg_exit_velo': team_data['Exit Velo'].mean()
    }

# Group by team for day-before data
teams_day_before = final_day_before['Team'].unique() if len(final_day_before) > 0 else []

# Calculate team statistics for day-before data
team_stats_day_before = {}
if len(final_day_before) > 0:
    for team in final_day_before['Team'].unique():
        team_data = final_day_before[final_day_before['Team'] == team]
        team_stats_day_before[team] = {
            'count': len(team_data),
            'avg_distance': team_data['Distance (ft)'].mean(),
            'max_distance': team_data['Distance (ft)'].max(),
            'avg_exit_velo': team_data['Exit Velo'].mean()
        }

# Generate timestamp
timestamp = datetime.now().strftime('%B %d, %Y at %I:%M %p')

# Generate HTML with team tables
html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Almost Homers by Team</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
            min-height: 100vh;
            padding: 20px;
            color: #e0e0e0;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(40, 40, 40, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            padding: 40px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .top-hitters {
            margin-bottom: 40px;
            background: rgba(50, 50, 50, 0.9);
            border-radius: 15px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .top-hitters-title {
            color: #ffffff;
            font-size: 1.8rem;
            font-weight: 600;
            margin-bottom: 20px;
            text-align: center;
            border-bottom: 2px solid #ffffff;
            padding-bottom: 15px;
        }

        /* Elite Table Special Styling */
        .elite-table {
            background: linear-gradient(135deg, #2c1810 0%, #1a1a1a 100%);
            border: 2px solid #FFD700;
            box-shadow: 0 0 20px rgba(255, 215, 0, 0.3);
        }

        .elite-table .top-hitters-title {
            background: linear-gradient(45deg, #FFD700, #FFA500);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            color: #FFD700;
            font-size: 2rem;
            text-shadow: 0 0 10px rgba(255, 215, 0, 0.5);
        }

        .top-hitters-subtitle {
            text-align: center;
            color: #b0b0b0;
            font-size: 0.9rem;
            margin-bottom: 25px;
        }

        .top-hitters-table {
            max-height: 400px;
            overflow-y: auto;
            background: rgba(60, 60, 60, 0.5);
            border-radius: 10px;
        }

        .top-hitters-table::-webkit-scrollbar {
            width: 8px;
        }

        .top-hitters-table::-webkit-scrollbar-track {
            background: rgba(40, 40, 40, 0.5);
            border-radius: 4px;
        }

        .top-hitters-table::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.3);
            border-radius: 4px;
        }

        .top-hitters-table table {
            width: 100%;
            border-collapse: collapse;
        }

        .top-hitters-table th {
            background: linear-gradient(135deg, #3a3a3a, #2a2a2a);
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
            color: #ffffff;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            position: sticky;
            top: 0;
        }

        .top-hitters-table td {
            padding: 10px 15px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            color: #e0e0e0;
        }

        .top-hitters-table tr:hover td {
            background-color: rgba(80, 80, 80, 0.3);
        }

        .team-tables {
            width: 100%;
        }


        .extra-base-hit {
            background-color: rgba(0, 255, 0, 0.2) !important;
            border-left: 3px solid #00FF00;
        }

        .single-hit {
            background-color: rgba(255, 255, 0, 0.2) !important;
            border-left: 3px solid #FFFF00;
        }

        .header {
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 3px solid #ffffff;
        }

        h1 {
            font-size: 2.5rem;
            color: #ffffff;
            margin-bottom: 10px;
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
        }

        .subtitle {
            font-size: 1.1rem;
            color: #b0b0b0;
            font-weight: 300;
        }

        .filters {
            margin: 20px 0;
            text-align: center;
        }

        .filter-dropdown {
            background: rgba(60, 60, 60, 0.9);
            color: #e0e0e0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            padding: 10px 15px;
            font-size: 1rem;
            cursor: pointer;
            transition: all 0.3s ease;
        }

        .filter-dropdown:hover {
            background: rgba(80, 80, 80, 0.9);
            border-color: rgba(255, 255, 255, 0.4);
        }

        .filter-dropdown option {
            background: #3c3c3c;
            color: #e0e0e0;
        }

        .team-section {
            margin-bottom: 50px;
            background: rgba(50, 50, 50, 0.9);
            border-radius: 15px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
            overflow: hidden;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .team-section:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.4);
        }

        .team-header {
            background: linear-gradient(135deg, #1a1a1a, #000000);
            color: white;
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }

        .team-name {
            font-size: 1.5rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .team-stats {
            display: flex;
            gap: 20px;
            font-size: 0.9rem;
        }

        .stat-item {
            text-align: center;
        }

        .stat-value {
            font-weight: bold;
            font-size: 1.1rem;
        }

        .stat-label {
            opacity: 0.8;
            font-size: 0.8rem;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            background: rgba(60, 60, 60, 0.5);
        }

        th {
            background: linear-gradient(135deg, #3a3a3a, #2a2a2a);
            padding: 15px 20px;
            text-align: left;
            font-weight: 600;
            color: #ffffff;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        td {
            padding: 15px 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            transition: background-color 0.2s ease;
            color: #e0e0e0;
        }

        tr:hover td {
            background-color: rgba(80, 80, 80, 0.3);
        }

        .exit-velo {
            color: white;
            font-weight: bold;
            padding: 8px 12px;
            border-radius: 6px;
            text-align: center;
            font-size: 0.9rem;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.3);
        }

        .launch-angle {
            color: black;
            font-weight: bold;
            padding: 8px 12px;
            border-radius: 6px;
            text-align: center;
            font-size: 0.9rem;
            text-shadow: 1px 1px 2px rgba(255, 255, 255, 0.3);
        }

        .batter-cell {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .batter-cell img {
            border-radius: 50%;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }

        .player-name {
            font-weight: 600;
            letter-spacing: 0.5px;
            background: linear-gradient(135deg, #ffffff 0%, #e0e0e0 100%);
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.3);
        }

        .leaderboard-player-name {
            font-weight: 600;
            letter-spacing: 0.3px;
            background: linear-gradient(135deg, #ffffff 0%, #d0d0d0 100%);
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-size: 0.85rem;
        }

        .distance-cell {
            font-weight: 600;
            color: #ffffff;
        }

        .bat-speed-cell {
            font-weight: 600;
            color: #ffffff;
            text-align: center;
        }

        .barrel-cell {
            font-size: 1.2rem;
            text-align: center;
        }

        .hr-prob-cell {
            font-weight: 600;
            color: #ffffff;
            text-align: center;
        }

        .event-cell {
            padding: 6px 12px;
            border-radius: 20px;
            background: #e3f2fd;
            color: #1976d2;
            font-size: 0.85rem;
            font-weight: 500;
            text-align: center;
        }

        .no-data {
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
            font-style: italic;
        }

        /* Favorites Sidebar */
        .favorites-sidebar {
            background: rgba(45, 52, 54, 0.95);
            border: 1px solid #34495e;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            max-width: 100%;
        }

        .favorites-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .favorites-header h3 {
            margin: 0;
            color: #f39c12;
            font-size: 1.2rem;
        }

        #clear-favorites {
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 5px;
            padding: 5px 10px;
            cursor: pointer;
            font-size: 0.8rem;
            transition: background 0.3s;
        }

        #clear-favorites:hover {
            background: #c0392b;
        }

        .favorites-list {
            min-height: 50px;
        }

        .favorite-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: rgba(52, 73, 94, 0.7);
            border-radius: 8px;
            padding: 10px;
            margin: 8px 0;
            border-left: 3px solid #f39c12;
        }

        .favorite-player {
            display: flex;
            align-items: center;
            flex: 1;
        }

        .remove-favorite {
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 50%;
            width: 25px;
            height: 25px;
            cursor: pointer;
            font-size: 0.8rem;
            transition: background 0.3s;
        }

        .remove-favorite:hover {
            background: #c0392b;
        }

        .no-favorites {
            color: #95a5a6;
            font-style: italic;
            text-align: center;
            padding: 20px;
            margin: 0;
        }

        /* Heart Button */
        .heart-btn {
            background: none;
            border: none;
            font-size: 1.2rem;
            cursor: pointer;
            color: #95a5a6;
            transition: all 0.3s;
            padding: 5px;
            border-radius: 50%;
        }

        .heart-btn:hover {
            color: #e74c3c;
            background: rgba(231, 76, 60, 0.1);
        }

        .heart-btn.favorited {
            color: #e74c3c;
            background: rgba(231, 76, 60, 0.1);
        }

        @media (max-width: 768px) {
            .container {
                padding: 15px;
                margin: 5px;
            }
            
            h1 {
                font-size: 1.8rem;
            }
            
            .top-hitters-subtitle {
                font-size: 0.8rem;
            }
            
            /* Mobile responsive table design */
            .top-hitters-table table,
            .team-section table {
                border: 0;
            }
            
            .top-hitters-table thead,
            .team-section thead {
                display: none;
            }
            
            .top-hitters-table tr,
            .team-section tr {
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 10px;
                display: block;
                margin-bottom: 10px;
                background: rgba(40, 40, 40, 0.8);
            }
            
            .top-hitters-table td,
            .team-section td {
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                display: block;
                padding: 8px 10px;
                text-align: left !important;
                font-size: 0.9rem;
            }
            
            .top-hitters-table td:before,
            .team-section td:before {
                content: attr(data-label) ": ";
                font-weight: bold;
                color: #b0b0b0;
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .top-hitters-table td:last-child,
            .team-section td:last-child {
                border-bottom: none;
            }
            
            /* Mobile specific styling for batter cells */
            .batter-cell {
                flex-direction: row !important;
                align-items: center;
                gap: 8px;
                text-align: left !important;
            }
            
            .batter-cell img {
                width: 16px;
                height: 16px;
            }
            
            /* Hide team filter on very small screens */
            .filters {
                margin-bottom: 20px;
            }
            
            .filter-dropdown {
                width: 100%;
                max-width: none;
                font-size: 0.9rem;
                padding: 8px;
            }
            
            /* Mobile team headers */
            .team-header {
                flex-direction: column;
                gap: 10px;
                text-align: center;
                padding: 15px;
            }
            
            .team-stats {
                flex-wrap: wrap;
                justify-content: center;
                gap: 8px;
            }
            
            .team-stat {
                font-size: 0.8rem;
                padding: 4px 8px;
            }
            
            /* Reduce top hitters table height on mobile */
            .top-hitters-table {
                max-height: 400px;
            }
        }
        
        @media (max-width: 480px) {
            .container {
                padding: 10px;
                margin: 0;
            }
            
            h1 {
                font-size: 1.6rem;
            }
            
            .top-hitters-title {
                font-size: 1.5rem;
            }
            
            .team-name {
                font-size: 1.3rem;
            }
            
            .top-hitters-table td,
            .team-section td {
                padding: 6px 8px;
                font-size: 0.85rem;
            }
            
            .batter-cell img {
                width: 14px;
                height: 14px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Almost Homers by Team</h1>
            <p class="subtitle">Latest games' closest calls that didn't leave the yard</p>
            <p style="font-size: 0.9rem; color: #95a5a6; margin-top: 10px;">Last updated: """ + timestamp + """</p>
        </div>
        
        <div id="favorites-sidebar" class="favorites-sidebar">
            <div class="favorites-header">
                <h3>⭐ My Favorites</h3>
                <button id="clear-favorites" onclick="clearAllFavorites()">Clear All</button>
            </div>
            <div id="favorites-list" class="favorites-list">
                <p class="no-favorites">Click the ♡ button next to any player to add them to your favorites!</p>
            </div>
        </div>
        
        <div class="filters">
            <select id="teamFilter" class="filter-dropdown" onchange="filterTeams()">
                <option value="">All Teams</option>
"""

# Add team options to dropdown
for team in sorted(teams):
    html_content += f'                <option value="{team}">{team}</option>\n'

html_content += """            </select>
        </div>
        
        <div class="top-hitters elite-table">
            <div class="top-hitters-title">🏆 Elite Hitters</div>
            <p class="top-hitters-subtitle">Players with 15%+ Barrel Rate (minimum 8 batted balls)</p>
            <div class="top-hitters-table">
                <table>
                    <thead>
                        <tr>
                            <th>♥</th>
                            <th>Player</th>
                            <th>Barrel %</th>
                            <th>Hard Hit %</th>
                            <th>Fly Ball %</th>
                            <th>Avg EV</th>
                            <th>Max EV</th>
                            <th>Avg Dist</th>
                            <th>Max Dist</th>
                            <th>AB</th>
                        </tr>
                    </thead>
                    <tbody>
"""

# Add Elite Players rows
for player_data in elite_players:
    # Extract player info (with team logo)
    batter_with_logo = str(player_data['Batter'])
    player_name = batter_with_logo.split('> ')[-1] if '> ' in batter_with_logo else batter_with_logo
    
    # Extract team logo
    team_logo = ""
    if 'src="' in batter_with_logo:
        start = batter_with_logo.find('src="') + 5
        end = batter_with_logo.find('"', start)
        logo_url = batter_with_logo[start:end]
        team_logo = f'<img src="{logo_url}" width="20" style="vertical-align:middle; margin-right: 8px;">'
    
    # Style the player name
    styled_player_name = f'<span class="leaderboard-player-name">{player_name}</span>'
    
    # Color code barrel rate - elite highlighting for 20%+
    barrel_style = ""
    if player_data['barrel_rate'] >= 25.0:
        barrel_style = 'style="background-color: #FFD700; color: #000; font-weight: bold;"'  # Gold for 25%+
    elif player_data['barrel_rate'] >= 20.0:
        barrel_style = 'style="background-color: #8B0000; color: #FFD700; font-weight: bold;"'  # Dark red with gold text for 20%+
    elif player_data['barrel_rate'] >= 15.0:
        barrel_style = 'style="background-color: #4CAF50; color: white; font-weight: bold;"'  # Green for 15%+
    
    # Color code avg exit velocity
    avg_ev_style = get_exit_velo_color(player_data['avg_exit_velo'])
    max_ev_style = get_exit_velo_color(player_data['max_exit_velo'])
    
    html_content += f"""
                        <tr>
                            <td data-label="♥" style="text-align: center;"><button class="heart-btn" data-player="{player_name}" data-logo="{team_logo.replace('"', '&quot;')}" onclick="toggleFavoriteBtn(this)">♡</button></td>
                            <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                            <td data-label="Barrel %" {barrel_style} style="text-align: center;">{player_data['barrel_rate']}%</td>
                            <td data-label="Hard Hit %" style="text-align: center; font-weight: bold;">{player_data['hard_hit_rate']}%</td>
                            <td data-label="Fly Ball %" style="text-align: center;">{player_data['fly_ball_rate']}%</td>
                            <td data-label="Avg EV" style="text-align: center; {avg_ev_style}">{player_data['avg_exit_velo']} mph</td>
                            <td data-label="Max EV" style="text-align: center; {max_ev_style}">{player_data['max_exit_velo']} mph</td>
                            <td data-label="Avg Dist" style="text-align: center;">{int(player_data['avg_distance'])} ft</td>
                            <td data-label="Max Dist" style="text-align: center;">{int(player_data['max_distance'])} ft</td>
                            <td data-label="AB" style="text-align: center; color: #95a5a6;">{player_data['total_batted_balls']}</td>
                        </tr>
    """

if not elite_players:
    html_content += """
                        <tr>
                            <td colspan="10" style="text-align: center; color: #7f8c8d; font-style: italic; padding: 20px;">
                                No players currently meet the elite 15% barrel rate threshold with minimum batted balls
                            </td>
                        </tr>
    """

html_content += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="top-hitters">
            <div class="top-hitters-title">4-Day Rolling Leaders</div>
            <p class="top-hitters-subtitle">Exit Velo >95 mph & Distance >200 ft (""" + date_range + """)</p>
            <div class="top-hitters-table">
                <table>
                    <thead>
                        <tr>
                            <th>♥</th>
                            <th>Player</th>
                            <th># Times Elite Contact</th>
                            <th>Best Exit Velo</th>
                            <th>Best Distance</th>
                            <th>Best Event</th>
                            <th>Days Active</th>
                        </tr>
                    </thead>
                    <tbody>
"""

# Add rolling leaderboard rows
for player_data in rolling_leaderboard[:25]:  # Show top 25 players
    # Extract player info (with team logo)
    batter_with_logo = str(player_data['Batter'])
    player_name = batter_with_logo.split('> ')[-1] if '> ' in batter_with_logo else batter_with_logo
    
    # Extract team logo
    team_logo = ""
    if 'src="' in batter_with_logo:
        start = batter_with_logo.find('src="') + 5
        end = batter_with_logo.find('"', start)
        logo_url = batter_with_logo[start:end]
        team_logo = f'<img src="{logo_url}" width="20" style="vertical-align:middle; margin-right: 8px;">'
    
    event_text = str(player_data['Best_Event']).replace('_', ' ').title()
    
    # Determine event styling based on best event
    row_class = ""
    star_prefix = ""
    if player_data['Best_Event'] == 'triple':
        row_class = 'style="background-color: rgba(0, 255, 0, 0.2); border-left: 3px solid #00FF00;"'
        star_prefix = "⭐ "
    elif player_data['Best_Event'] == 'double':
        row_class = 'style="background-color: rgba(0, 200, 0, 0.2); border-left: 3px solid #00AA00;"'
        star_prefix = "⭐ "
    elif player_data['Best_Event'] == 'single':
        row_class = 'style="background-color: rgba(255, 255, 0, 0.2); border-left: 3px solid #FFFF00;"'
    
    # Style the player name
    styled_player_name = f'<span class="leaderboard-player-name">{player_name}</span>'
    
    html_content += f"""
                        <tr {row_class}>
                            <td data-label="♥" style="text-align: center;"><button class="heart-btn" data-player="{player_name}" data-logo="{team_logo.replace('"', '&quot;')}" onclick="toggleFavoriteBtn(this)">♡</button></td>
                            <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                            <td data-label="# Times Elite Contact" style="text-align: center; font-weight: bold; color: #4CAF50;">{player_data['Total_Count']}</td>
                            <td data-label="Best Exit Velo" style="text-align: center; {get_exit_velo_color(player_data['Best_Exit_Velo'])}">{player_data['Best_Exit_Velo']} mph</td>
                            <td data-label="Best Distance" style="text-align: center;">{int(player_data['Best_Distance'])} ft</td>
                            <td data-label="Best Event" style="text-align: center;">{star_prefix}{event_text}</td>
                            <td data-label="Days Active" style="text-align: center; color: #FFA500;">{player_data['Days_Active']}</td>
                        </tr>
    """

html_content += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="top-hitters">
            <div class="top-hitters-title">Today's Top Hitters</div>
            <p class="top-hitters-subtitle">Individual hits from today's games (Exit Velo >95 mph & Distance >200 ft)</p>
            <div class="top-hitters-table">
                <table>
                    <thead>
                        <tr>
                            <th>♥</th>
                            <th>Player</th>
                            <th>Exit Velo</th>
                            <th>Distance</th>
                            <th>Event</th>
                        </tr>
                    </thead>
                    <tbody>
"""

# Group by player and sort by count, but show all individual hits
# Create a custom sorting approach to group players together
# First get unique players sorted by their count
player_order = elite_leaderboard.groupby('Batter')['Count'].first().sort_values(ascending=False).index.tolist()

# Now reconstruct the dataframe with players grouped together
grouped_rows = []
for player in player_order:
    player_hits = elite_leaderboard[elite_leaderboard['Batter'] == player].sort_values('Exit Velo', ascending=False)
    grouped_rows.extend(player_hits.to_dict('records'))

# Add today's top hitters rows (all individual hits, but grouped by player)
for row in grouped_rows[:50]:  # Show top 50 individual hits
    # Extract player info
    batter_with_logo = str(row['Batter'])
    player_name = batter_with_logo.split('> ')[-1] if '> ' in batter_with_logo else batter_with_logo
    
    # Extract team logo
    team_logo = ""
    if 'src="' in batter_with_logo:
        start = batter_with_logo.find('src="') + 5
        end = batter_with_logo.find('"', start)
        logo_url = batter_with_logo[start:end]
        team_logo = f'<img src="{logo_url}" width="20" style="vertical-align:middle; margin-right: 8px;">'
    
    event_text = str(row['Event']).replace('_', ' ').title() if str(row['Event']) != 'nan' else 'In Play'
    
    # Determine event styling
    row_class = ""
    star_prefix = ""
    if row['Event'] == 'triple':
        row_class = 'style="background-color: rgba(0, 255, 0, 0.2); border-left: 3px solid #00FF00;"'
        star_prefix = "⭐ "
    elif row['Event'] == 'double':
        row_class = 'style="background-color: rgba(0, 200, 0, 0.2); border-left: 3px solid #00AA00;"'
        star_prefix = "⭐ "
    elif row['Event'] == 'single':
        row_class = 'style="background-color: rgba(255, 255, 0, 0.2); border-left: 3px solid #FFFF00;"'
    
    # Style the player name
    styled_player_name = f'<span class="leaderboard-player-name">{player_name}</span>'
    
    html_content += f"""
                        <tr {row_class}>
                            <td data-label="♥" style="text-align: center;"><button class="heart-btn" data-player="{player_name}" data-logo="{team_logo.replace('"', '&quot;')}" onclick="toggleFavoriteBtn(this)">♡</button></td>
                            <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                            <td data-label="Exit Velo" style="text-align: center; {get_exit_velo_color(row['Exit Velo'])}">{row['Exit Velo']} mph</td>
                            <td data-label="Distance" style="text-align: center;">{int(row['Distance (ft)'])} ft</td>
                            <td data-label="Event" style="text-align: center;">{star_prefix}{event_text}</td>
                        </tr>
    """

html_content += """
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="top-hitters">
            <div class="top-hitters-title">Yesterday's Top Hitters</div>
            <p class="top-hitters-subtitle">Individual hits from """ + yesterday + """ (Exit Velo >95 mph & Distance >200 ft)</p>
            <div class="top-hitters-table">
                <table>
                    <thead>
                        <tr>
                            <th>♥</th>
                            <th>Player</th>
                            <th>Exit Velo</th>
                            <th>Distance</th>
                            <th>Event</th>
                        </tr>
                    </thead>
                    <tbody>
"""

# Add yesterday's top hitters if data exists
if len(elite_leaderboard_day_before) > 0:
    # Group by player and sort by count, but show all individual hits for day before
    player_order_day_before = elite_leaderboard_day_before.groupby('Batter')['Count'].first().sort_values(ascending=False).index.tolist()

    # Reconstruct the dataframe with players grouped together for day before
    grouped_rows_day_before = []
    for player in player_order_day_before:
        player_hits = elite_leaderboard_day_before[elite_leaderboard_day_before['Batter'] == player].sort_values('Exit Velo', ascending=False)
        grouped_rows_day_before.extend(player_hits.to_dict('records'))

    # Add yesterday's top hitters rows (all individual hits, but grouped by player)
    for row in grouped_rows_day_before[:50]:  # Show top 50 individual hits from day before
        # Extract player info
        batter_with_logo = str(row['Batter'])
        player_name = batter_with_logo.split('> ')[-1] if '> ' in batter_with_logo else batter_with_logo
        
        # Extract team logo
        team_logo = ""
        if 'src="' in batter_with_logo:
            start = batter_with_logo.find('src="') + 5
            end = batter_with_logo.find('"', start)
            logo_url = batter_with_logo[start:end]
            team_logo = f'<img src="{logo_url}" width="20" style="vertical-align:middle; margin-right: 8px;">'
        
        event_text = str(row['Event']).replace('_', ' ').title() if str(row['Event']) != 'nan' else 'In Play'
        
        # Determine event styling
        row_class = ""
        star_prefix = ""
        if row['Event'] == 'triple':
            row_class = 'style="background-color: rgba(0, 255, 0, 0.2); border-left: 3px solid #00FF00;"'
            star_prefix = "⭐ "
        elif row['Event'] == 'double':
            row_class = 'style="background-color: rgba(0, 200, 0, 0.2); border-left: 3px solid #00AA00;"'
            star_prefix = "⭐ "
        elif row['Event'] == 'single':
            row_class = 'style="background-color: rgba(255, 255, 0, 0.2); border-left: 3px solid #FFFF00;"'
        
        # Style the player name
        styled_player_name = f'<span class="leaderboard-player-name">{player_name}</span>'
        
        html_content += f"""
                            <tr {row_class}>
                                <td data-label="♥" style="text-align: center;"><button class="heart-btn" data-player="{player_name}" data-logo="{team_logo.replace('"', '&quot;')}" onclick="toggleFavoriteBtn(this)">♡</button></td>
                                <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                                <td data-label="Exit Velo" style="text-align: center; {get_exit_velo_color(row['Exit Velo'])}">{row['Exit Velo']} mph</td>
                                <td data-label="Distance" style="text-align: center;">{int(row['Distance (ft)'])} ft</td>
                                <td data-label="Event" style="text-align: center;">{star_prefix}{event_text}</td>
                            </tr>
        """
else:
    html_content += """
                            <tr>
                                <td colspan="4" style="text-align: center; color: #7f8c8d; font-style: italic; padding: 20px;">
                                    No elite contact hits found for this date
                                </td>
                            </tr>
    """

html_content += """
                    </tbody>
                </table>
            </div>
        </div>
        <div class="team-tables">
"""

# Use today's data if available, otherwise use yesterday's data for team tables
team_data_source = final if len(final) > 0 else final_day_before
team_stats_source = team_stats if len(final) > 0 else team_stats_day_before  
teams_source = teams if len(final) > 0 else teams_day_before

for team in sorted(teams_source):
    team_data = team_data_source[team_data_source['Team'] == team].copy()
    if len(team_data) > 0:
        stats = team_stats_source[team]
        html_content += f"""
        <div class="team-section" data-team="{team}">
            <div class="team-header">
                <div class="team-name">{team}</div>
                <div class="team-stats">
                    <div class="stat-item">
                        <div class="stat-value">{stats['count']}</div>
                        <div class="stat-label">Almost HRs</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats['avg_distance']:.0f} ft</div>
                        <div class="stat-label">Avg Distance</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats['max_distance']:.0f} ft</div>
                        <div class="stat-label">Longest</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{stats['avg_exit_velo']:.1f}</div>
                        <div class="stat-label">Avg Exit Velo</div>
                    </div>
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Batter</th>
                        <th>Exit Velo</th>
                        <th>Launch Angle</th>
                        <th>Bat Speed</th>
                        <th>Barrel</th>
                        <th>HR/Park</th>
                        <th>Distance</th>
                        <th>Event</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for _, row in team_data.sort_values('Exit Velo', ascending=False).iterrows():
            exit_velo_style = get_exit_velo_color(row['Exit Velo'])
            launch_angle_style = get_launch_angle_color(row['Launch Angle'], row['Exit Velo'])
            bat_speed_display = format_bat_speed(row['Bat Speed'])
            barrel_indicator = format_barrel(row['Is_Barrel'])
            hr_parks_display = format_hr_parks(row['HR_Parks'])
            event_text = str(row['Event']).replace('_', ' ').title() if str(row['Event']) != 'nan' else 'In Play'
            
            # Extract player name for styling
            batter_html = str(row['Batter'])
            if '> ' in batter_html:
                logo_part = batter_html.split('> ')[0] + '> '
                name_part = batter_html.split('> ')[1]
                styled_batter = f'{logo_part}<span class="player-name">{name_part}</span>'
            else:
                styled_batter = f'<span class="player-name">{batter_html}</span>'
            
            html_content += f"""
                    <tr>
                        <td data-label="Batter"><div class="batter-cell">{styled_batter}</div></td>
                        <td data-label="Exit Velo"><div class="exit-velo" style="{exit_velo_style}">{row['Exit Velo']}</div></td>
                        <td data-label="Launch Angle"><div class="launch-angle" style="{launch_angle_style}">{row['Launch Angle']}°</div></td>
                        <td data-label="Bat Speed"><div class="bat-speed-cell">{bat_speed_display}</div></td>
                        <td data-label="Barrel"><div class="barrel-cell">{barrel_indicator}</div></td>
                        <td data-label="HR/Park"><div class="hr-prob-cell">{hr_parks_display}</div></td>
                        <td data-label="Distance"><div class="distance-cell">{row['Distance (ft)']} ft</div></td>
                        <td data-label="Event"><div class="event-cell">{event_text}</div></td>
                    </tr>
            """
        
        html_content += """
                </tbody>
            </table>
        </div>
        """

if not any(len(team_data_source[team_data_source['Team'] == team]) > 0 for team in teams_source):
    html_content += '<div class="no-data">No almost homers found for yesterday.</div>'

html_content += """
        </div>
    </div>
    <script>
        function filterTeams() {
            const selectedTeam = document.getElementById('teamFilter').value;
            const teamSections = document.querySelectorAll('.team-section');
            
            teamSections.forEach(section => {
                if (selectedTeam === '' || section.getAttribute('data-team') === selectedTeam) {
                    section.style.display = 'block';
                } else {
                    section.style.display = 'none';
                }
            });
        }

        // Favorites functionality
        let favorites = JSON.parse(localStorage.getItem('baseballFavorites') || '[]');

        function saveFavorites() {
            localStorage.setItem('baseballFavorites', JSON.stringify(favorites));
        }

        function toggleFavoriteBtn(button) {
            const playerName = button.getAttribute('data-player');
            const teamLogo = button.getAttribute('data-logo').replace(/&quot;/g, '"');
            
            const existingIndex = favorites.findIndex(fav => fav.name === playerName);
            
            if (existingIndex > -1) {
                // Remove from favorites
                favorites.splice(existingIndex, 1);
                updateHeartButtons(playerName, false);
            } else {
                // Add to favorites
                favorites.push({
                    name: playerName,
                    logo: teamLogo,
                    dateAdded: new Date().toISOString()
                });
                updateHeartButtons(playerName, true);
            }
            
            saveFavorites();
            renderFavorites();
        }

        function updateHeartButtons(playerName, isFavorited) {
            const buttons = document.querySelectorAll('.heart-btn');
            buttons.forEach(btn => {
                const btnPlayerName = btn.getAttribute('data-player');
                if (btnPlayerName === playerName) {
                    btn.textContent = isFavorited ? '♥' : '♡';
                    btn.classList.toggle('favorited', isFavorited);
                }
            });
        }

        function removeFavorite(playerName) {
            const index = favorites.findIndex(fav => fav.name === playerName);
            if (index > -1) {
                favorites.splice(index, 1);
                saveFavorites();
                renderFavorites();
                updateHeartButtons(playerName, false);
            }
        }

        function clearAllFavorites() {
            if (confirm('Are you sure you want to clear all favorites?')) {
                favorites = [];
                saveFavorites();
                renderFavorites();
                // Update all heart buttons
                document.querySelectorAll('.heart-btn').forEach(btn => {
                    btn.textContent = '♡';
                    btn.classList.remove('favorited');
                });
            }
        }

        function renderFavorites() {
            const favoritesList = document.getElementById('favorites-list');
            
            if (favorites.length === 0) {
                favoritesList.innerHTML = '<p class="no-favorites">Click the ♡ button next to any player to add them to your favorites!</p>';
                return;
            }
            
            favoritesList.innerHTML = favorites.map(fav => `
                <div class="favorite-item">
                    <div class="favorite-player">
                        ${fav.logo}
                        <span class="leaderboard-player-name">${fav.name}</span>
                    </div>
                    <button class="remove-favorite" onclick="removeFavorite('${fav.name}')">×</button>
                </div>
            `).join('');
        }

        // Initialize favorites on page load
        document.addEventListener('DOMContentLoaded', function() {
            renderFavorites();
            
            // Update heart buttons based on saved favorites
            favorites.forEach(fav => {
                updateHeartButtons(fav.name, true);
            });
        });
    </script>
</body>
</html>
"""

# Write HTML file
with open("../almosthomers/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML saved as almosthomers/index.html - open it in your browser.")
