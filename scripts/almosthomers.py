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
    'batter_with_logo', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'events'
]].sort_values(by='hit_distance_sc', ascending=False).reset_index(drop=True)

# Rename for clarity
final.columns = ['Batter', 'Exit Velo', 'Launch Angle', 'Distance (ft)', 'Event']

# Export to HTML
final.to_html("almosthomers/index.html", escape=False, index=False)
print("✅ HTML saved as output.html — open it in your browser.")
