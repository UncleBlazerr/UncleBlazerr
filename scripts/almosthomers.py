from pybaseball import statcast, playerid_reverse_lookup
from datetime import datetime, timedelta
import pandas as pd

# Use yesterday to ensure data is available
yesterday = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')

# Get Statcast data
data = statcast(start_dt=yesterday, end_dt=yesterday)

# Filter for valid batted ball data and exclude home runs
filtered = data[
    (data['launch_speed'].notna()) &
    (data['launch_angle'].notna()) &
    (data['hit_distance_sc'].notna()) &
    (data['events'] != 'home_run')
]

# Select relevant fields (batter ID instead of player_name)
subset = filtered[['batter', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'events']].copy()

# Get unique batter IDs and map them to names
batter_ids = subset['batter'].unique()
batter_names = playerid_reverse_lookup(batter_ids, key_type='mlbam')[['key_mlbam', 'name_first', 'name_last']]

# Merge batter names into the dataset
batter_names['batter_name'] = batter_names['name_first'] + ' ' + batter_names['name_last']
merged = subset.merge(batter_names[['key_mlbam', 'batter_name']], left_on='batter', right_on='key_mlbam', how='left')

# Final formatting
final = merged[['batter_name', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'events']]
final = final.sort_values(by='hit_distance_sc', ascending=False).reset_index(drop=True)

# Display top 15
print(final.head(15))
