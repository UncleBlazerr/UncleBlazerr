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

# Use today's date for current games
today = datetime.today().strftime('%Y-%m-%d')
yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

print(f"Pulling Statcast data for: {today}")

# Pull Statcast data for today
data = statcast(start_dt=today, end_dt=today)

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


# Merge names
merged = subset.merge(
    batter_names[['key_mlbam', 'batter_name']],
    left_on='batter',
    right_on='key_mlbam',
    how='left'
)

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
elite_criteria = final[(final['Exit Velo'] > 98) & (final['Distance (ft)'] > 200)].copy()

# Count occurrences per player to determine sort order
player_counts = elite_criteria.groupby('Batter').size().reset_index(name='Count')

# Add count to each row for sorting
elite_criteria = elite_criteria.merge(player_counts, on='Batter', how='left')

# Sort by count (descending), then by exit velocity (descending)
elite_leaderboard = elite_criteria.sort_values(['Count', 'Exit Velo'], ascending=[False, False]).reset_index(drop=True)

# Create elite contact leaderboard for day before
print("Creating day-before elite contact leaderboard...")
if len(final_day_before) > 0:
    elite_criteria_day_before = final_day_before[(final_day_before['Exit Velo'] > 98) & (final_day_before['Distance (ft)'] > 200)].copy()
    
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

# Get date range for display
date_keys = sorted(historical_data.keys())
if date_keys:
    start_date = datetime.strptime(date_keys[0], '%Y-%m-%d').strftime('%B %d')
    end_date = datetime.strptime(date_keys[-1], '%Y-%m-%d').strftime('%B %d, %Y')
    date_range = f"{start_date} - {end_date}" if len(date_keys) > 1 else end_date
else:
    date_range = "No data available"

# Function to get exit velocity color
def get_exit_velo_color(velo):
    if velo > 98:
        return 'background-color: #8B0000'  # Dark red
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
        <div class="filters">
            <select id="teamFilter" class="filter-dropdown" onchange="filterTeams()">
                <option value="">All Teams</option>
"""

# Add team options to dropdown
for team in sorted(teams):
    html_content += f'                <option value="{team}">{team}</option>\n'

html_content += """            </select>
        </div>
        <div class="top-hitters">
            <div class="top-hitters-title">4-Day Rolling Leaders</div>
            <p class="top-hitters-subtitle">Exit Velo >98 mph & Distance >200 ft (""" + date_range + """)</p>
            <div class="top-hitters-table">
                <table>
                    <thead>
                        <tr>
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
                            <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                            <td data-label="# Times Elite Contact" style="text-align: center; font-weight: bold; color: #4CAF50;">{player_data['Total_Count']}</td>
                            <td data-label="Best Exit Velo" style="text-align: center; font-weight: bold;">{player_data['Best_Exit_Velo']} mph</td>
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
            <p class="top-hitters-subtitle">Individual hits from today's games</p>
            <div class="top-hitters-table">
                <table>
                    <thead>
                        <tr>
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
                            <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                            <td data-label="Exit Velo" style="text-align: center; font-weight: bold;">{row['Exit Velo']} mph</td>
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
            <p class="top-hitters-subtitle">Individual hits from """ + yesterday + """</p>
            <div class="top-hitters-table">
                <table>
                    <thead>
                        <tr>
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
                                <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                                <td data-label="Exit Velo" style="text-align: center; font-weight: bold;">{row['Exit Velo']} mph</td>
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

for team in sorted(teams):
    team_data = final[final['Team'] == team].copy()
    if len(team_data) > 0:
        stats = team_stats[team]
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

if not any(len(final[final['Team'] == team]) > 0 for team in teams):
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
    </script>
</body>
</html>
"""

# Write HTML file
with open("../almosthomers/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML saved as almosthomers/index.html - open it in your browser.")
