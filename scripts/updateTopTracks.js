import fs from 'fs/promises';
import axios from 'axios';

const {
  SPOTIFY_CLIENT_ID,
  SPOTIFY_CLIENT_SECRET,
  SPOTIFY_REFRESH_TOKEN
} = process.env;

async function getAccessToken() {
  const res = await axios.post(
    'https://accounts.spotify.com/api/token',
    new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: SPOTIFY_REFRESH_TOKEN
    }),
    {
      headers: {
        Authorization:
          'Basic ' +
          Buffer.from(`${SPOTIFY_CLIENT_ID}:${SPOTIFY_CLIENT_SECRET}`).toString('base64'),
        'Content-Type': 'application/x-www-form-urlencoded'
      }
    }
  );
  return res.data.access_token;
}

async function fetchTracks(url, token, isRecent = false) {
  const res = await axios.get(url, {
    headers: { Authorization: `Bearer ${token}` }
  });

  return res.data.items.map(item => {
    const track = isRecent ? item.track : item;
    return {
      name: track.name,
      artist: track.artists.map(a => a.name).join(', '),
      url: track.external_urls.spotify,
      image: track.album.images[0]?.url || '',
      preview_url: track.preview_url || null
    };
  });
}

async function main() {
  const token = await getAccessToken();

  await fs.mkdir('data', { recursive: true });

  // Recently played
  const recentTracks = await fetchTracks(
    'https://api.spotify.com/v1/me/player/recently-played?limit=5',
    token,
    true
  );
  await fs.writeFile('data/recent.json', JSON.stringify(recentTracks, null, 2));

  // Top played (long-term)
  const topTracks = await fetchTracks(
    'https://api.spotify.com/v1/me/top/tracks?limit=5&time_range=long_term',
    token
  );
  await fs.writeFile('data/top.json', JSON.stringify(topTracks, null, 2));

  console.log('✅ Data updated successfully.');
}

main().catch(err => {
  console.error('❌ Error updating Spotify data:', err.message);
  process.exit(1);
});
