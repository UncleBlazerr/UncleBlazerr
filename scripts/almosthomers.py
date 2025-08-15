from pybaseball import statcast, playerid_reverse_lookup
from datetime import datetime, timedelta
import pandas as pd
import os
import requests
import time

#make os dir
os.makedirs("../almosthomers", exist_ok=True)

# Use yesterday's date (when games actually occurred)
yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

print(f"Pulling Statcast data for: {yesterday}")

# Pull Statcast data
data = statcast(start_dt=yesterday, end_dt=yesterday)

print(f"Total batted balls found: {len(data)}")

# Filter valid batted-ball data, exclude home runs, require exit velo >= 93, exclude null events
filtered = data[
    (data['launch_speed'].notna()) &
    (data['launch_angle'].notna()) &
    (data['hit_distance_sc'].notna()) &
    (data['events'].notna()) &
    (data['events'] != 'home_run') &
    (data['launch_speed'] >= 93)
]

print(f"Bat speed column available: {'bat_speed' in data.columns}")
print(f"Available columns: {list(data.columns)}")
print(f"HR/Park columns: {[col for col in data.columns if 'park' in col.lower() or 'hr' in col.lower()]}")
print(f"Estimated probability columns: {[col for col in data.columns if 'estimated' in col.lower() or 'prob' in col.lower() or 'exp' in col.lower()]}")

print(f"Filtered batted balls (no HRs): {len(filtered)}")


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

# Create elite contact leaderboard
print("Creating elite contact leaderboard...")
elite_criteria = final[(final['Exit Velo'] > 98) & (final['Distance (ft)'] > 200)].copy()

# Count occurrences per player to determine sort order
player_counts = elite_criteria.groupby('Batter').size().reset_index(name='Count')

# Add count to each row for sorting
elite_criteria = elite_criteria.merge(player_counts, on='Batter', how='left')

# Sort by count (descending), then by exit velocity (descending)
elite_leaderboard = elite_criteria.sort_values(['Count', 'Exit Velo'], ascending=[False, False]).reset_index(drop=True)

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
final['Exit Velo Style'] = final['Exit Velo'].apply(lambda x: get_exit_velo_color(x))
final['Is_Barrel'] = final.apply(lambda row: is_barrel(row['Exit Velo'], row['Launch Angle']), axis=1)

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
            <div class="top-hitters-title">Top Hitters</div>
            <p class="top-hitters-subtitle">Exit Velo >98 mph & Distance >200 ft</p>
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
# Create a custom sort key that groups players by their count
def get_player_sort_key(row):
    return (row['Count'], row['Exit Velo'])

# Sort the elite leaderboard by count (descending), then by exit velocity (descending)
# But this will keep all individual hits - they'll just be grouped by player
elite_leaderboard_grouped = elite_leaderboard.copy()

# Create a custom sorting approach to group players together
# First get unique players sorted by their count
player_order = elite_leaderboard_grouped.groupby('Batter')['Count'].first().sort_values(ascending=False).index.tolist()

# Now reconstruct the dataframe with players grouped together
grouped_rows = []
for player in player_order:
    player_hits = elite_leaderboard_grouped[elite_leaderboard_grouped['Batter'] == player].sort_values('Exit Velo', ascending=False)
    grouped_rows.extend(player_hits.to_dict('records'))

# Add top hitters rows (all individual hits, but grouped by player)
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
