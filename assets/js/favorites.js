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
            dateAdded: new Date().toISOString(),
            rating: 0  // Default rating of 0 stars
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