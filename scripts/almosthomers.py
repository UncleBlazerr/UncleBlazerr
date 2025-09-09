from pybaseball import statcast, playerid_reverse_lookup
from datetime import datetime, timedelta
import pandas as pd
import os
import requests
import time
import json

# Create directories
os.makedirs("../almosthomers", exist_ok=True)
os.makedirs("../assets/css", exist_ok=True)
os.makedirs("../assets/js", exist_ok=True)
os.makedirs("../components", exist_ok=True)

# Component rendering functionz
def load_component(component_name):
    """Load an HTML component file"""
    component_path = os.path.join("../components", component_name)
    with open(component_path, 'r', encoding='utf-8') as f:
        return f.read()

def render_template(template_content, **kwargs):
    """Simple template rendering with {{ variable }} replacement"""
    for key, value in kwargs.items():
        template_content = template_content.replace('{{ ' + key + ' }}', str(value))
    return template_content

# Copy all the functions from the original script (keeping the same logic)
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
    date_str = current_date
    
    if date_str not in historical_data:
        historical_data[date_str] = {}
    
    historical_data[date_str] = {}
    
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
        
        historical_data[date_str][player_name]['count'] += 1
        historical_data[date_str][player_name]['best_exit_velo'] = max(
            historical_data[date_str][player_name]['best_exit_velo'], 
            row['Exit Velo']
        )
        historical_data[date_str][player_name]['best_distance'] = max(
            historical_data[date_str][player_name]['best_distance'], 
            row['Distance (ft)']
        )
        
        current_event = historical_data[date_str][player_name]['best_event']
        new_event = row['Event']
        event_priority = {'triple': 3, 'double': 2, 'single': 1}
        if event_priority.get(new_event, 0) > event_priority.get(current_event, 0):
            historical_data[date_str][player_name]['best_event'] = new_event
        
        historical_data[date_str][player_name]['hits'].append({
            'exit_velo': row['Exit Velo'],
            'distance': row['Distance (ft)'],
            'event': row['Event']
        })
    
    all_dates = sorted(historical_data.keys())
    if len(all_dates) > 4:
        for old_date in all_dates[:-4]:
            del historical_data[old_date]
    
    return historical_data

def create_rolling_leaderboard(historical_data):
    """Create 4-day rolling leaderboard from historical data"""
    player_totals = {}
    
    for date_str, daily_data in historical_data.items():
        for player_name, player_data in daily_data.items():
            if player_name not in player_totals:
                player_totals[player_name] = {
                    'total_count': 0,
                    'best_exit_velo': 0,
                    'best_distance': 0,
                    'best_event': 'field_out',
                    'days_active': 0,
                    'batter_info': player_name
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
            
            current_event = player_totals[player_name]['best_event']
            new_event = player_data['best_event']
            event_priority = {'triple': 3, 'double': 2, 'single': 1}
            if event_priority.get(new_event, 0) > event_priority.get(current_event, 0):
                player_totals[player_name]['best_event'] = new_event
    
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
    
    leaderboard.sort(key=lambda x: (x['Total_Count'], x['Best_Exit_Velo']), reverse=True)
    return leaderboard

# Get data (simplified version of original logic)
today = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')
yesterday = (datetime.today() - timedelta(days=2)).strftime('%Y-%m-%d')

print(f"Pulling Statcast data for: {today}")
data = statcast(start_dt=today, end_dt=today)

print(f"Pulling Statcast data for day before: {yesterday}")
data_day_before = statcast(start_dt=yesterday, end_dt=yesterday)

# Process data (keeping original logic but simplified)
def process_statcast_data(data):
    """Process statcast data and return formatted dataframe"""
    if len(data) == 0:
        return pd.DataFrame()
    
    # Filter data
    filtered = data[
        (data['launch_speed'].notna()) &
        (data['launch_angle'].notna()) &
        (data['hit_distance_sc'].notna()) &
        (data['events'].notna()) &
        (data['events'] != 'home_run') &
        (data['launch_speed'] >= 93)
    ]
    
    if len(filtered) == 0:
        return pd.DataFrame()
    
    # Select columns
    columns_to_select = [
        'batter', 'launch_speed', 'launch_angle', 'hit_distance_sc', 'game_pk',
        'events', 'inning_topbot', 'home_team', 'away_team'
    ]
    
    if 'bat_speed' in filtered.columns:
        columns_to_select.insert(4, 'bat_speed')
    
    subset = filtered[columns_to_select].copy()
    
    if 'bat_speed' not in subset.columns:
        subset['bat_speed'] = float('nan')
    
    # Lookup batter names
    batter_ids = subset['batter'].unique()
    batter_names = playerid_reverse_lookup(batter_ids, key_type='mlbam')[['key_mlbam', 'name_first', 'name_last']]
    batter_names['name_first'] = batter_names['name_first'].str.title()
    batter_names['name_last'] = batter_names['name_last'].str.title()
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
    
    # Map logos
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
    
    # Rename columns
    final.columns = ['Batter', 'Exit Velo', 'Launch Angle', 'Distance (ft)', 'Bat Speed', 'Game PK', 'Event', 'Team']
    
    return final

# Process both days
final = process_statcast_data(data)
final_day_before = process_statcast_data(data_day_before)

print(f"Processed {len(final)} hits for today, {len(final_day_before)} hits for yesterday")

# Create elite leaderboards
elite_criteria = final[(final['Exit Velo'] > 95) & (final['Distance (ft)'] > 200)].copy() if len(final) > 0 else pd.DataFrame()

# Create elite leaderboard for today (needed for individual hitters section)
if len(elite_criteria) > 0:
    # Count occurrences per player to determine sort order
    player_counts = elite_criteria.groupby('Batter').size().reset_index(name='Count')
    # Add count to each row for sorting
    elite_criteria = elite_criteria.merge(player_counts, on='Batter', how='left')
    # Sort by count (descending), then by exit velocity (descending)
    elite_leaderboard = elite_criteria.sort_values(['Count', 'Exit Velo'], ascending=[False, False]).reset_index(drop=True)
else:
    elite_leaderboard = pd.DataFrame()

# Create elite leaderboard for yesterday
if len(final_day_before) > 0:
    elite_criteria_day_before = final_day_before[(final_day_before['Exit Velo'] > 95) & (final_day_before['Distance (ft)'] > 200)].copy()
    if len(elite_criteria_day_before) > 0:
        # Count occurrences per player to determine sort order
        player_counts_day_before = elite_criteria_day_before.groupby('Batter').size().reset_index(name='Count')
        # Add count to each row for sorting
        elite_criteria_day_before = elite_criteria_day_before.merge(player_counts_day_before, on='Batter', how='left')
        # Sort by count (descending), then by exit velocity (descending)
        elite_leaderboard_day_before = elite_criteria_day_before.sort_values(['Count', 'Exit Velo'], ascending=[False, False]).reset_index(drop=True)
    else:
        elite_leaderboard_day_before = pd.DataFrame()
else:
    elite_leaderboard_day_before = pd.DataFrame()

# Multi-day tracking
historical_data = load_historical_data()
if len(elite_criteria) > 0:
    historical_data = update_rolling_data(historical_data, elite_criteria, today)
save_historical_data(historical_data)

# Create rolling leaderboard
rolling_leaderboard = create_rolling_leaderboard(historical_data)

# Get date range for display
date_keys = sorted(historical_data.keys())
if date_keys:
    start_date = datetime.strptime(date_keys[0], '%Y-%m-%d').strftime('%B %d')
    end_date = datetime.strptime(date_keys[-1], '%Y-%m-%d').strftime('%B %d, %Y')
    date_range = f"{start_date} - {end_date}" if len(date_keys) > 1 else end_date
else:
    date_range = "No data available"

# Generate timestamp
timestamp = datetime.now().strftime('%B %d, %Y at %I:%M %p')

# Helper functions for HTML generation
def get_exit_velo_color(velo):
    if velo > 98:
        return 'background-color: #8B0000; color: #FFD700; font-weight: bold; box-shadow: 0 0 10px #FFD700; border: 2px solid #FFD700'
    elif velo > 94:
        return 'background-color: #FF0000'
    else:
        return 'background-color: #FFB6C1'

def is_barrel(exit_velo, launch_angle):
    """Check if a ball qualifies as a barrel"""
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

def get_launch_angle_color(angle, exit_velo):
    """Get launch angle color based on angle and exit velocity"""
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
    else:  # Below 8 or above 35
        return 'background-color: #FF0000'  # Red

def format_player_row(player_data, is_elite=False):
    """Format a player row for HTML tables"""
    batter_with_logo = str(player_data.get('Batter', ''))
    player_name = batter_with_logo.split('> ')[-1] if '> ' in batter_with_logo else batter_with_logo
    
    # Extract team logo
    team_logo = ""
    if 'src="' in batter_with_logo:
        start = batter_with_logo.find('src="') + 5
        end = batter_with_logo.find('"', start)
        logo_url = batter_with_logo[start:end]
        team_logo = f'<img src="{logo_url}" width="20" style="vertical-align:middle; margin-right: 8px;">'
    
    styled_player_name = f'<span class="leaderboard-player-name">{player_name}</span>'
    
    return {
        'player_name': player_name,
        'team_logo': team_logo,
        'styled_player_name': styled_player_name,
        'batter_with_logo': batter_with_logo
    }

# Generate sections
def generate_elite_players_section():
    """Generate elite players section (placeholder - would implement full logic)"""
    return '<p>No elite players found with current criteria</p>'

def generate_rolling_leaderboard_section():
    """Generate rolling leaderboard section"""
    rows = ''
    for player_data in rolling_leaderboard[:25]:
        player_info = format_player_row(player_data)
        
        event_text = str(player_data['Best_Event']).replace('_', ' ').title()
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
        
        rows += f"""
                        <tr {row_class}>
                            <td data-label="♥" style="text-align: center;"><button class="heart-btn" data-player="{player_info['player_name']}" data-logo="{player_info['team_logo'].replace('"', '&quot;')}" onclick="toggleFavoriteBtn(this)">♡</button></td>
                            <td data-label="Player"><div class="batter-cell">{player_info['team_logo']}{player_info['styled_player_name']}</div></td>
                            <td data-label="# Times Elite Contact" style="text-align: center; font-weight: bold; color: #4CAF50;">{player_data['Total_Count']}</td>
                            <td data-label="Best Exit Velo" style="text-align: center; {get_exit_velo_color(player_data['Best_Exit_Velo'])}">{player_data['Best_Exit_Velo']} mph</td>
                            <td data-label="Best Distance" style="text-align: center;">{int(player_data['Best_Distance'])} ft</td>
                            <td data-label="Best Event" style="text-align: center;">{star_prefix}{event_text}</td>
                            <td data-label="Days Active" style="text-align: center; color: #FFA500;">{player_data['Days_Active']}</td>
                        </tr>
        """
    
    return rows

def generate_individual_hitters_section(elite_data, title_suffix=""):
    """Generate individual hitters section for today/yesterday"""
    if len(elite_data) == 0:
        return '<tr><td colspan="5" style="text-align: center; color: #7f8c8d; font-style: italic; padding: 20px;">No elite contact hits found for this date</td></tr>'
    
    # Group by player and sort by count, but show all individual hits
    player_order = elite_data.groupby('Batter')['Count'].first().sort_values(ascending=False).index.tolist()
    
    # Reconstruct the dataframe with players grouped together
    grouped_rows = []
    for player in player_order:
        player_hits = elite_data[elite_data['Batter'] == player].sort_values('Exit Velo', ascending=False)
        grouped_rows.extend(player_hits.to_dict('records'))
    
    rows = ''
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
        
        rows += f"""
                        <tr {row_class}>
                            <td data-label="♥" style="text-align: center;"><button class="heart-btn" data-player="{player_name}" data-logo="{team_logo.replace('"', '&quot;')}" onclick="toggleFavoriteBtn(this)">♡</button></td>
                            <td data-label="Player"><div class="batter-cell">{team_logo}{styled_player_name}</div></td>
                            <td data-label="Exit Velo" style="text-align: center; {get_exit_velo_color(row['Exit Velo'])}">{row['Exit Velo']} mph</td>
                            <td data-label="Distance" style="text-align: center;">{int(row['Distance (ft)'])} ft</td>
                            <td data-label="Event" style="text-align: center;">{star_prefix}{event_text}</td>
                        </tr>
        """
    
    return rows

def generate_team_tables():
    """Generate team tables section"""
    teams = final['Team'].unique() if len(final) > 0 else []
    team_tables = ""
    
    for team in sorted(teams):
        team_data = final[final['Team'] == team].copy()
        if len(team_data) > 0:
            stats = {
                'count': len(team_data),
                'avg_distance': team_data['Distance (ft)'].mean(),
                'max_distance': team_data['Distance (ft)'].max(),
                'avg_exit_velo': team_data['Exit Velo'].mean()
            }
            
            team_template = load_component('team_section.html')
            team_rows = ""
            
            for _, row in team_data.sort_values('Exit Velo', ascending=False).iterrows():
                event_text = str(row['Event']).replace('_', ' ').title() if str(row['Event']) != 'nan' else 'In Play'
                
                # Extract player name for styling
                batter_html = str(row['Batter'])
                if '> ' in batter_html:
                    logo_part = batter_html.split('> ')[0] + '> '
                    name_part = batter_html.split('> ')[1]
                    styled_batter = f'{logo_part}<span class="player-name">{name_part}</span>'
                else:
                    styled_batter = f'<span class="player-name">{batter_html}</span>'
                
                # Calculate proper coloring
                exit_velo_style = get_exit_velo_color(row['Exit Velo'])
                launch_angle_style = get_launch_angle_color(row['Launch Angle'], row['Exit Velo'])
                is_barrel_hit = is_barrel(row['Exit Velo'], row['Launch Angle'])
                barrel_indicator = '🛢️' if is_barrel_hit else ''
                
                team_rows += f"""
                        <tr>
                            <td data-label="Batter"><div class="batter-cell">{styled_batter}</div></td>
                            <td data-label="Exit Velo"><div class="exit-velo" style="{exit_velo_style}">{row['Exit Velo']}</div></td>
                            <td data-label="Launch Angle"><div class="launch-angle" style="{launch_angle_style}">{row['Launch Angle']}°</div></td>
                            <td data-label="Bat Speed"><div class="bat-speed-cell">{row['Bat Speed'] if pd.notna(row['Bat Speed']) else 'N/A'}</div></td>
                            <td data-label="Barrel"><div class="barrel-cell">{barrel_indicator}</div></td>
                            <td data-label="HR/Park"><div class="hr-prob-cell">0/30</div></td>
                            <td data-label="Distance"><div class="distance-cell">{row['Distance (ft)']} ft</div></td>
                            <td data-label="Event"><div class="event-cell">{event_text}</div></td>
                        </tr>
                """
            
            team_tables += render_template(team_template,
                team=team,
                count=stats['count'],
                avg_distance=f"{stats['avg_distance']:.0f}",
                max_distance=f"{stats['max_distance']:.0f}",
                avg_exit_velo=f"{stats['avg_exit_velo']:.1f}",
                team_rows=team_rows
            )
    
    return team_tables

# Copy CSS and JS from assets to output directory
import shutil
if os.path.exists('../assets/css/styles.css'):
    shutil.copy('../assets/css/styles.css', '../almosthomers/styles.css')
if os.path.exists('../assets/js/favorites.js'):
    shutil.copy('../assets/js/favorites.js', '../almosthomers/favorites.js')

# Generate HTML
try:
    base_template = load_component('base.html')
    rolling_template = load_component('rolling_leaderboard.html')
    
    # Generate team options
    teams = final['Team'].unique() if len(final) > 0 else []
    team_options = ''
    for team in sorted(teams):
        team_options += f'                <option value="{team}">{team}</option>\n'
    
    # Generate rolling leaderboard
    rolling_rows = generate_rolling_leaderboard_section()
    rolling_section = render_template(rolling_template,
        date_range=date_range,
        rolling_leaderboard_rows=rolling_rows
    )
    
    # Generate team tables
    team_tables = generate_team_tables()
    
    # Generate today's and yesterday's hitters sections
    today_template = load_component('today_hitters.html')
    yesterday_template = load_component('yesterday_hitters.html')
    
    today_rows = generate_individual_hitters_section(elite_leaderboard)
    today_section = render_template(today_template,
        today_hitters_rows=today_rows
    )
    
    yesterday_rows = generate_individual_hitters_section(elite_leaderboard_day_before)
    yesterday_section = render_template(yesterday_template,
        yesterday=yesterday,
        yesterday_hitters_rows=yesterday_rows
    )
    
    # Render final HTML
    html_content = render_template(base_template,
        timestamp=timestamp,
        team_options=team_options,
        elite_players_section=generate_elite_players_section(),
        rolling_leaderboard_section=rolling_section,
        today_hitters_section=today_section,
        yesterday_hitters_section=yesterday_section,
        team_tables=team_tables
    )
    
    # Write HTML file
    with open("../almosthomers/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print("HTML saved as almosthomers/index.html - open it in your browser.")

except Exception as e:
    print(f"Error generating HTML: {e}")
    # Fallback to simple HTML
    simple_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Almost Homers by Team</title>
        <link rel="stylesheet" href="styles.css">
    </head>
    <body>
        <h1>Almost Homers by Team</h1>
        <p>Generated at {timestamp}</p>
        <p>Found {len(final)} hits today and {len(final_day_before)} hits yesterday</p>
        <p>Rolling leaderboard has {len(rolling_leaderboard)} players</p>
    </body>
    </html>
    """
    
    with open("../almosthomers/index.html", "w", encoding="utf-8") as f:
        f.write(simple_html)
    
    print("Fallback HTML saved due to error.")

# Start Flask web server to serve the HTML
from flask import Flask, send_from_directory
import threading

app = Flask(__name__)

@app.route('/')
def serve_html():
    return send_from_directory('../almosthomers', 'index.html')

@app.route('/styles.css')
def serve_css():
    return send_from_directory('../almosthomers', 'styles.css')

@app.route('/favorites.js')
def serve_js():
    return send_from_directory('../almosthomers', 'favorites.js')

if __name__ == "__main__":
    print("Starting web server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)