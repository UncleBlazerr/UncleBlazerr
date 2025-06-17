const fs = require('fs');
const axios = require('axios');

const clientId = process.env.SPOTIFY_CLIENT_ID;
const clientSecret = process.env.SPOTIFY_CLIENT_SECRET;
const refreshToken = process.env.SPOTIFY_REFRESH_TOKEN;

async function getAccessToken() {
  const response = await axios.post(
    'https://accounts.spotify.com/api/token',
    new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
    }),
    {
      headers: {
        Authorization:
          'Basic ' +
          Buffer.from(`${clientId}:${clientSecret}`).toString('base64'),
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    }
  );

  return response.data.access_token;
}

async function getRecentTracks(accessToken) {
  const response = await axios.get(
    'https://api.spotify.com/v1/me/player/recently-played?limit=5',
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    }
  );

  return response.data.items.map(item => ({
    name: item.track.name,
    artist: item.track.artists.map(a => a.name).join(', '),
    url: item.track.external_urls.spotify,
    image: item.track.album.images[0]?.url || '',
  }));
}

(async () => {
  const accessToken = await getAccessToken();
  const tracks = await getRecentTracks(accessToken);

  fs.mkdirSync('data', { recursive: true });
  fs.writeFileSync('data/tracks.json', JSON.stringify(tracks, null, 2));

  console.log('✅ Updated data/tracks.json');
})();
