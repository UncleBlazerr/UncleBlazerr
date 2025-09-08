# Project Structure

This document explains the organized structure of the UncleBlazerr project.

## Directory Structure

```
UncleBlazerr/
├── assets/                    # Reusable assets for the entire project
│   ├── css/
│   │   └── styles.css        # Main stylesheet (can be used across projects)
│   └── js/
│       └── favorites.js      # JavaScript functionality
├── components/               # HTML components/partials
│   ├── base.html            # Main page layout template
│   ├── elite_players.html   # Elite players section component
│   ├── rolling_leaderboard.html # Rolling leaderboard component
│   ├── team_section.html    # Individual team section component
│   ├── today_hitters.html   # Today's hitters component
│   └── yesterday_hitters.html # Yesterday's hitters component
├── scripts/                 # Python scripts
│   └── almosthomers.py     # Main data processing and HTML generation script
├── almosthomers/           # Generated output directory
│   ├── index.html          # Generated HTML page
│   ├── styles.css          # Copied from assets/css/
│   ├── favorites.js        # Copied from assets/js/
│   └── elite_contact_history.json # Historical data
└── data/                   # Other data files
```

## File Types and Their Purpose

### Assets (`/assets/`)
- **Reusable across projects**: These files can be used by other parts of the project
- **CSS**: Styling that could be applied to other pages/projects
- **JS**: JavaScript functionality that could be reused

### Components (`/components/`)
- **HTML partials**: Reusable pieces of HTML structure
- **Template-like**: Use `{{ variable }}` placeholders for dynamic content
- **Modular**: Each component handles a specific part of the page

### Scripts (`/scripts/`)
- **Data processing**: Contains the Python logic for fetching and processing baseball data
- **HTML generation**: Uses components to build the final HTML page
- **Asset management**: Copies CSS/JS from assets to output directory

### Output (`/almosthomers/`)
- **Generated files**: Created by the Python script
- **Self-contained**: Has all necessary files (HTML, CSS, JS) to run standalone
- **Deployment ready**: Can be served directly from a web server

## How It Works

1. **Python script** (`scripts/almosthomers.py`) processes baseball data
2. **Components** are loaded and populated with data
3. **Assets** (CSS/JS) are copied to the output directory
4. **Final HTML** is generated in the `almosthomers/` directory

## Benefits of This Structure

1. **Separation of Concerns**: Logic (Python) separate from presentation (HTML/CSS)
2. **Reusability**: Assets can be used across different parts of the project
3. **Maintainability**: Easy to modify styling without touching Python code
4. **Clarity**: Clear distinction between templates, assets, and generated output
5. **Modularity**: Components can be easily modified or reused

## Making Changes

- **Styling**: Edit `assets/css/styles.css`
- **JavaScript**: Edit `assets/js/favorites.js`  
- **HTML Layout**: Edit files in `components/`
- **Data Processing**: Edit `scripts/almosthomers.py`

The script will automatically copy updated assets to the output directory when run.