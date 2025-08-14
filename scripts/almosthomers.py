from pybaseball import statcast, playerid_reverse_lookup
from datetime import datetime, timedelta
import pandas as pd
import os

#make os dir
os.makedirs("almosthomers", exist_ok=True)

# Use yesterday's date
yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

# Pull Statcast data
data = statcast(start_dt=yesterday, end_dt=yesterday)

# Filter valid batted-ball data, exclude home runs
filtered = data[
    (data['launch_speed'].notna()) &
    (data['launch_angle'].notna()) &
    (data['hit_distance_sc'].notna()) &
    (data['events'] != 'home_run')
]

# Select useful columns
subset = filtered[[
    'batter', 'launch_speed', 'launch_angle', 'hit_distance_sc',
    'events', 'inning_topbot', 'home_team', 'away_team'
]].copy()

# Lookup batter names
batter_ids = subset['batter'].unique()
batter_names = playerid_reverse_lookup(batter_ids, key_type='mlbam')[['key_mlbam', 'name_first', 'name_last']]
batter_names['batter_name'] = batter_names['name_first'] + ' ' + batter_names['name_last']

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
    'batter_with_logo', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'events', 'team_abbr'
]].sort_values(by='hit_distance_sc', ascending=False).reset_index(drop=True)

# Rename for clarity
final.columns = ['Batter', 'Exit Velo', 'Launch Angle', 'Distance (ft)', 'Event', 'Team']

# Function to get exit velocity color
def get_exit_velo_color(velo):
    if velo > 98:
        return 'background-color: #8B0000'  # Dark red
    elif velo > 94:
        return 'background-color: #FF0000'  # Red
    elif velo > 85:
        return 'background-color: #FFB6C1'  # Light red
    else:
        return 'background-color: #FFFFFF'  # White

# Apply exit velocity coloring
final['Exit Velo Style'] = final['Exit Velo'].apply(lambda x: get_exit_velo_color(x))

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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            padding: 40px;
            backdrop-filter: blur(10px);
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 3px solid #667eea;
        }
        
        h1 {
            font-size: 2.5rem;
            color: #2c3e50;
            margin-bottom: 10px;
            font-weight: 700;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        .subtitle {
            font-size: 1.1rem;
            color: #7f8c8d;
            font-weight: 300;
        }
        
        .team-section {
            margin-bottom: 50px;
            background: #fff;
            border-radius: 15px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
            overflow: hidden;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .team-section:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.15);
        }
        
        .team-header {
            background: linear-gradient(135deg, #3498db, #2980b9);
            color: white;
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
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
            background: white;
        }
        
        th {
            background: linear-gradient(135deg, #f8f9fa, #e9ecef);
            padding: 15px 20px;
            text-align: left;
            font-weight: 600;
            color: #2c3e50;
            border-bottom: 2px solid #dee2e6;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        td {
            padding: 15px 20px;
            border-bottom: 1px solid #f1f3f4;
            transition: background-color 0.2s ease;
        }
        
        tr:hover td {
            background-color: #f8f9fa;
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
            color: #2c3e50;
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
        </div>
"""

for team in sorted(teams):
    team_data = final[final['Team'] == team].copy()
    if len(team_data) > 0:
        stats = team_stats[team]
        html_content += f"""
        <div class="team-section">
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
                        <th>Distance</th>
                        <th>Event</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for _, row in team_data.iterrows():
            exit_velo_style = get_exit_velo_color(row['Exit Velo'])
            event_text = str(row['Event']).replace('_', ' ').title() if str(row['Event']) != 'nan' else 'In Play'
            
            html_content += f"""
                    <tr>
                        <td><div class="batter-cell">{row['Batter']}</div></td>
                        <td><div class="exit-velo" style="{exit_velo_style}">{row['Exit Velo']}</div></td>
                        <td>{row['Launch Angle']}°</td>
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
</body>
</html>
"""

# Write HTML file
with open("almosthomers/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("HTML saved as almosthomers/index.html - open it in your browser.")
