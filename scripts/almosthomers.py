from pybaseball import statcast, playerid_reverse_lookup
from datetime import datetime, timedelta
import pandas as pd
import os
import requests
import time

#make os dir
os.makedirs("../almosthomers", exist_ok=True)

# Use yesterday's date
yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

print(f"Pulling Statcast data for: {yesterday}")

# Pull Statcast data
data = statcast(start_dt=yesterday, end_dt=yesterday)

print(f"Total batted balls found: {len(data)}")

# Filter valid batted-ball data, exclude home runs, require exit velo >= 93
filtered = data[
    (data['launch_speed'].notna()) &
    (data['launch_angle'].notna()) &
    (data['hit_distance_sc'].notna()) &
    (data['events'] != 'home_run') &
    (data['launch_speed'] >= 93)
]

print(f"Bat speed column available: {'bat_speed' in data.columns}")
print(f"Available columns: {list(data.columns)}")
print(f"HR/Park columns: {[col for col in data.columns if 'park' in col.lower() or 'hr' in col.lower()]}")
print(f"Estimated probability columns: {[col for col in data.columns if 'estimated' in col.lower() or 'prob' in col.lower() or 'exp' in col.lower()]}")

print(f"Filtered batted balls (no HRs): {len(filtered)}")

# Debug: Check for Vidal Brujan specifically
if len(data) > 0:
    brujan_data = data[data['player_name'].str.contains('brujan', case=False, na=False)]
    if len(brujan_data) > 0:
        print(f"\nVidal Bruján data found:")
        for _, row in brujan_data.iterrows():
            print(f"  Game: {row.get('game_pk', 'N/A')}, Distance: {row.get('hit_distance_sc', 'N/A')}, Exit Velo: {row.get('launch_speed', 'N/A')}, Event: {row.get('events', 'N/A')}")
    else:
        print("\nNo Vidal Bruján data found in raw data")

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
batter_names['batter_name'] = batter_names['name_first'] + ' ' + batter_names['name_last']

print(f"Found names for {len(batter_names)} batters")

# Check if Vidal Bruján is in the lookup results
brujan_in_lookup = batter_names[batter_names['batter_name'].str.contains('brujan', case=False, na=False)]
if len(brujan_in_lookup) > 0:
    print(f"Vidal Bruján found in lookup with ID: {brujan_in_lookup['key_mlbam'].iloc[0]}")
    # Check what data exists for this ID in our subset
    brujan_subset = subset[subset['batter'] == brujan_in_lookup['key_mlbam'].iloc[0]]
    print(f"Data rows for Bruján: {len(brujan_subset)}")
    if len(brujan_subset) > 0:
        print(brujan_subset[['batter', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'events']].head())

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
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(40, 40, 40, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            padding: 40px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
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
                padding: 20px;
                margin: 10px;
            }
            
            h1 {
                font-size: 2rem;
            }
            
            .team-header {
                flex-direction: column;
                gap: 15px;
                text-align: center;
            }
            
            .team-stats {
                flex-wrap: wrap;
                justify-content: center;
            }
            
            th, td {
                padding: 10px 15px;
                font-size: 0.9rem;
            }
            
            .batter-cell {
                flex-direction: column;
                text-align: center;
                gap: 5px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Almost Homers by Team</h1>
            <p class="subtitle">Yesterday's closest calls that didn't leave the yard</p>
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
            
            html_content += f"""
                    <tr>
                        <td><div class="batter-cell">{row['Batter']}</div></td>
                        <td><div class="exit-velo" style="{exit_velo_style}">{row['Exit Velo']}</div></td>
                        <td><div class="launch-angle" style="{launch_angle_style}">{row['Launch Angle']}°</div></td>
                        <td><div class="bat-speed-cell">{bat_speed_display}</div></td>
                        <td><div class="barrel-cell">{barrel_indicator}</div></td>
                        <td><div class="hr-prob-cell">{hr_parks_display}</div></td>
                        <td><div class="distance-cell">{row['Distance (ft)']} ft</div></td>
                        <td><div class="event-cell">{event_text}</div></td>
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
